"""
Monthly platform invoices, from the daily subscriber snapshots.

The period is the previous calendar month (or, for an ISP that started
paying part-way through it, from its activation date). The counted number
of subscribers comes from that period's snapshots using the plan's rules
(service types, active vs all, peak/average/latest), the plan prices it,
and the first period is prorated by days if the plan says so.

With auto-deduction on, an invoice is paid straight away from the money
held for the ISP when the balance covers it; otherwise it stays open for
the ISP to pay by STK from its account page.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from cloud.billing.ledger import balance, post
from cloud.billing.models import Invoice
from cloud.core.models import PlatformSettings
from cloud.pricing.models import money
from cloud.tenants.models import Tenant, UsageSnapshot


def previous_month(today=None):
    today = today or timezone.localdate()
    end = today.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


def counted(plan, counts, basis=None):
    basis = basis or plan.count_basis
    by_type = (counts or {}).get(basis, {})
    return sum(int(by_type.get(t, 0)) for t in plan.service_type_list())


def billable_count(tenant, plan, start, end):
    snaps = list(UsageSnapshot.objects.filter(tenant=tenant, date__gte=start, date__lte=end).order_by('date'))
    if not snaps:
        return 0, {'days_measured': 0}
    if plan.count_method == 'latest':
        value = counted(plan, snaps[-1].latest)
    elif plan.count_method == 'average':
        value = round(sum(counted(plan, s.peak) for s in snaps) / len(snaps))
    else:
        value = max(counted(plan, s.peak) for s in snaps)
    return value, {'days_measured': len(snaps), 'method': plan.count_method, 'basis': plan.count_basis,
                   'service_types': plan.service_type_list()}


def _number():
    year = timezone.localdate().year
    n = Invoice.objects.filter(number__startswith=f'INV-{year}-').count() + 1
    while Invoice.objects.filter(number=f'INV-{year}-{n:05d}').exists():
        n += 1
    return f'INV-{year}-{n:05d}'


def build(tenant, start, end):
    """The invoice that would be issued (not saved) -> dict."""
    plan = tenant.effective_plan()
    if not plan:
        raise ValueError('No pricing plan is set up')
    count, detail = billable_count(tenant, plan, start, end)
    quote = plan.quote(count)
    subtotal = Decimal(quote['amount'])
    lines = list(quote['lines'])
    activated = timezone.localdate(tenant.activated_at) if tenant.activated_at else start
    period_start = max(start, activated)
    days = (end - start).days + 1
    active_days = (end - period_start).days + 1
    if plan.prorate_first_period and active_days < days:
        factor = Decimal(active_days) / Decimal(days)
        prorated = money(subtotal * factor)
        lines.append({'label': f'Prorated: {active_days} of {days} days', 'quantity': 1,
                      'unit_price': str(prorated - subtotal), 'amount': str(prorated - subtotal)})
        subtotal = prorated
    discount = money(subtotal * tenant.discount_percent / 100) if tenant.discount_percent else Decimal('0')
    if discount:
        lines.append({'label': f'Discount {tenant.discount_percent}%', 'quantity': 1, 'unit_price': str(-discount),
                      'amount': str(-discount)})
    return {'plan': plan, 'period_start': period_start, 'period_end': end, 'count': count, 'detail': detail,
            'lines': lines, 'subtotal': subtotal, 'discount': discount, 'amount': max(Decimal('0'), subtotal - discount)}


def issue(tenant, start, end):
    """Create the invoice for the period (once) and try to pay it from the balance."""
    cfg = PlatformSettings.load()
    existing = Invoice.objects.filter(tenant=tenant, period_start__lte=end, period_end__gte=start).exclude(status='void').first()
    if existing:
        return existing, False
    data = build(tenant, start, end)
    with transaction.atomic():
        inv = Invoice.objects.create(
            number=_number(), tenant=tenant, period_start=data['period_start'], period_end=data['period_end'],
            plan_name=data['plan'].name, subscriber_count=data['count'], count_detail=data['detail'],
            lines=data['lines'], subtotal=data['subtotal'], discount=data['discount'], amount=data['amount'],
            due_at=timezone.now() + timedelta(days=cfg.invoice_due_days))
        if inv.amount == 0:
            mark_paid(inv, 'balance', 'zero')
    from cloud.tenants.services import log, notify_owner
    log(tenant, 'billing', f'Invoice {inv.number}: KES {inv.amount:,.2f} for {data["count"]} subscribers')
    if inv.status == 'open' and cfg.auto_deduct_invoices:
        pay_from_balance(inv)
    inv.refresh_from_db()
    notify_owner(tenant, f'invoice {inv.number}', (
        f'Invoice {inv.number} for {inv.period_start:%d %b} - {inv.period_end:%d %b %Y}: '
        f'KES {inv.amount:,.2f} ({inv.subscriber_count} subscribers on {inv.plan_name}).\n'
        + ('It has been paid from your M-Pesa collections.' if inv.status == 'paid'
           else f'Please pay it by {timezone.localtime(inv.due_at):%d %b} from your account page.')))
    return inv, True


def pay_from_balance(invoice):
    if invoice.status != 'open':
        return False
    if balance(invoice.tenant) < invoice.amount:
        return False
    post(invoice.tenant, 'invoice', -invoice.amount, invoice.number, f'Platform invoice {invoice.number}', invoice=invoice)
    mark_paid(invoice, 'balance', invoice.number)
    return True


def mark_paid(invoice, via, ref=''):
    invoice.status, invoice.paid_at, invoice.paid_via, invoice.payment_ref = 'paid', timezone.now(), via, ref
    invoice.save(update_fields=['status', 'paid_at', 'paid_via', 'payment_ref'])
    tenant = invoice.tenant
    if tenant.status in ('past_due', 'suspended') and not tenant.invoices.filter(status='open').exists():
        if tenant.status == 'past_due':
            tenant.status = 'active'
            tenant.save(update_fields=['status'])
        elif tenant.suspend_reason.startswith('invoice'):
            from cloud.tenants.tasks import tenant_action
            transaction.on_commit(lambda: tenant_action.delay(tenant.pk, 'resume'))


def retry_open_invoices():
    """Money keeps arriving: pay open invoices from it, oldest first."""
    paid = 0
    for inv in Invoice.objects.filter(status='open').order_by('issued_at').select_related('tenant'):
        if pay_from_balance(inv):
            paid += 1
    return paid


def run_monthly(today=None, force=False):
    today = today or timezone.localdate()
    cfg = PlatformSettings.load()
    if not force and today.day != min(max(cfg.invoice_day, 1), 28):
        return 0
    start, end = previous_month(today)
    n = 0
    for tenant in Tenant.objects.filter(status__in=['active', 'past_due', 'suspended', 'cancelled'], activated_at__isnull=False,
                                        activated_at__date__lte=end):
        _, created = issue(tenant, start, end)
        n += created
    return n


def month_bounds(year, month):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
