"""
Emails to the superadmins (every superuser with an email address): the
11 pm daily sales report, and event emails -- vouchers generated, a new
PPPoE customer, a manual top-up / cash credit.

Tasks take record ids and build the content inside the worker, so nothing
non-JSON (attachments) crosses the Celery queue. Each send goes through
EmailService and is written to the notification log. Both kinds can be
switched off in Settings -> Notifications -> Superadmin emails.
"""
import csv
import io
import logging
from datetime import timedelta
from html import escape

from celery import shared_task
from django.db.models import Count, Sum
from django.utils import timezone

logger = logging.getLogger('notifications')

GREEN = '#0B4D33'

_local = __import__('threading').local()


class suppress_new_customer_emails:
    """
    Within this block, new PPPoE customers don't each trigger an email --
    the bulk import sends one summary (email_new_pppoe_import) instead.
    """
    def __enter__(self):
        _local.suppressed = True

    def __exit__(self, *exc):
        _local.suppressed = False


def new_customer_emails_suppressed():
    return getattr(_local, 'suppressed', False)


def superadmin_emails():
    """Superadmins' own profile email addresses."""
    from apps.customers.models import Customer
    return list(
        Customer.objects.filter(is_superuser=True, is_active=True).exclude(email='')
        .values_list('email', flat=True).distinct()
    )


def admin_email_recipients():
    """Admin contact emails (Settings -> Notifications) plus superadmin profile emails, deduplicated."""
    from apps.notifications.models import NotificationSettings
    seen = {}
    for e in NotificationSettings.load().email_list() + [x.lower() for x in superadmin_emails()]:
        seen.setdefault(e, None)
    return list(seen)


def notify_admins(event_type, subject, text, html=None, attachments=None, sms_text=None,
                  customer=None, subscription=None):
    """
    Send one admin notification to every admin contact: the full email to
    each admin email (only when Email is set up), and `sms_text` (default:
    the subject) to each admin phone on each chosen channel (SMS/WhatsApp).
    Every attempt is logged. Returns how many were delivered.
    """
    from apps.notifications.dispatch import send_and_log
    from apps.notifications.models import NotificationLog, NotificationSettings
    from apps.notifications.services.email_service import EmailService

    settings_obj = NotificationSettings.load()
    delivered = 0
    emails = admin_email_recipients() if settings_obj.email_enabled else []
    if emails:
        service = EmailService()
        for recipient in emails:
            result = service.send_email(recipient, text, subject=subject, html=html, attachments=attachments)
            NotificationLog.objects.create(
                customer=customer, subscription=subscription, channel='email', event_type=event_type,
                recipient=recipient, message=f'{subject}\n\n{text}'[:5000],
                status='sent' if result['success'] else 'failed',
                error='' if result['success'] else str(result.get('error', '')),
            )
            delivered += bool(result['success'])
    short = sms_text or subject
    for phone in settings_obj.phone_list():
        for channel in settings_obj.phone_channels():
            result = send_and_log(channel=channel, recipient=phone, message=short, event_type=event_type,
                                  customer=customer, subscription=subscription)
            delivered += bool(result['success'])
    if not emails and not settings_obj.phone_list():
        logger.warning("No admin contacts (emails/phones) set up; %s notification not sent", event_type)
    return delivered


# Older name kept for the call sites below.
def _send_to_superadmins(event_type, subject, text, html=None, attachments=None, sms_text=None):
    return notify_admins(event_type, subject, text, html, attachments, sms_text=sms_text)


def _company():
    from apps.sitesettings.models import SiteSettings
    return SiteSettings.load().company_name


def _html_page(title, intro, sections):
    """Simple, email-client-safe HTML: inline styles, tables. sections: [(heading, [cols], [[cells]])]."""
    parts = [
        f'<div style="font-family:Arial,Helvetica,sans-serif;color:#14231B;max-width:680px">',
        f'<div style="background:{GREEN};color:#fff;padding:16px 20px;border-radius:12px 12px 0 0">'
        f'<div style="font-size:12px;opacity:.8">{escape(_company())}</div>'
        f'<div style="font-size:20px;font-weight:bold">{escape(title)}</div></div>',
        f'<div style="padding:16px 20px;border:1px solid #E9E3D6;border-top:0;border-radius:0 0 12px 12px">',
        f'<p style="margin:0 0 12px">{intro}</p>',
    ]
    for heading, cols, rows in sections:
        if heading:
            parts.append(f'<h3 style="font-size:15px;margin:18px 0 6px">{escape(heading)}</h3>')
        if not rows:
            parts.append('<p style="color:#5E6B62;margin:0">None.</p>')
            continue
        parts.append('<table style="border-collapse:collapse;width:100%;font-size:13px">')
        parts.append('<tr>' + ''.join(
            f'<th style="text-align:left;background:#E7F1EB;padding:6px 8px;border-bottom:1px solid {GREEN}">{escape(str(c))}</th>'
            for c in cols) + '</tr>')
        for r in rows:
            parts.append('<tr>' + ''.join(
                f'<td style="padding:6px 8px;border-bottom:1px solid #F1ECE2">{escape(str(c))}</td>' for c in r) + '</tr>')
        parts.append('</table>')
    parts.append('</div></div>')
    return ''.join(parts)


def _text_sections(sections):
    lines = []
    for heading, cols, rows in sections:
        if heading:
            lines += ['', heading, '-' * len(heading)]
        if not rows:
            lines.append('None.')
        for r in rows:
            lines.append(' | '.join(str(c) for c in r))
    return '\n'.join(lines)


def _enabled(flag):
    # The on/off switch only; email vs phone availability is notify_admins' job.
    from apps.notifications.models import NotificationSettings
    return getattr(NotificationSettings.load(), flag)


# --------------------------------------------------------------- daily report

def daily_report(day):
    """Figures for one Nairobi day: (summary [(label, value)], sections [(heading, cols, rows)])."""
    from apps.billing.models import Subscription, Transaction, Voucher
    from apps.customers.models import Customer

    completed = Transaction.objects.filter(status='completed', created_at__date=day)
    # 'balance' transactions spend money already counted when it came in.
    money_in = completed.exclude(payment_method='balance')
    totals = money_in.aggregate(total=Sum('amount'), n=Count('id'))
    revenue = float(totals['total'] or 0)

    methods = dict(Transaction.PAYMENT_METHOD_CHOICES)
    by_method = [
        [methods.get(r['payment_method'], r['payment_method']), r['n'], f"KES {float(r['amount'] or 0):,.2f}"]
        for r in money_in.values('payment_method').annotate(n=Count('id'), amount=Sum('amount')).order_by('-amount')
    ]
    by_plan = [
        [r['subscription__plan__name'] or 'Credited to balance (no plan)', r['n'], f"KES {float(r['amount'] or 0):,.2f}"]
        for r in money_in.values('subscription__plan__name').annotate(n=Count('id'), amount=Sum('amount')).order_by('-amount')
    ]
    from_balance = completed.filter(payment_method='balance').aggregate(n=Count('id'), amount=Sum('amount'))
    vouchers = Voucher.objects.filter(status='used', used_at__date=day).aggregate(n=Count('id'), amount=Sum('amount'))
    now = timezone.now()

    summary = [
        ('Revenue', f"KES {revenue:,.2f}"),
        ('Payments', totals['n']),
        ('Average payment', f"KES {revenue / totals['n']:,.2f}" if totals['n'] else '—'),
        ('Plans paid from balance', f"{from_balance['n']} (KES {float(from_balance['amount'] or 0):,.2f})"),
        ('Vouchers redeemed', f"{vouchers['n']} (KES {float(vouchers['amount'] or 0):,.2f})"),
        ('New customers', Customer.objects.filter(is_staff=False, created_at__date=day).count()),
        ('Active subscriptions', Subscription.objects.filter(status='active', expiry_date__gt=now).count()),
        ('Expiring in the next 24h', Subscription.objects.filter(
            status='active', expiry_date__gt=now, expiry_date__lte=now + timedelta(days=1)).count()),
    ]
    sections = [
        ('Sales by plan', ['Plan', 'Payments', 'Amount'], by_plan),
        ('By payment method', ['Method', 'Payments', 'Amount'], by_method),
    ]
    return summary, sections


@shared_task
def send_daily_report(day=None, force=False):
    """11 pm EAT (beat) -- or on demand from Settings with force=True."""
    if not force and not _enabled('daily_report_enabled'):
        return 0
    from apps.analytics.exports import Section, export_response

    day = timezone.datetime.fromisoformat(day).date() if day else timezone.localdate()
    summary, sections = daily_report(day)
    title = f"Daily sales report · {day:%a %d %b %Y}"
    intro = '<br>'.join(f'<b>{escape(label)}:</b> {escape(str(value))}' for label, value in summary)
    html = _html_page(title, intro, sections)
    text = '\n'.join(f'{label}: {value}' for label, value in summary) + '\n' + _text_sections(sections)

    pdf = export_response(
        'pdf', filename=f'daily_report_{day}', title=title, summary=summary,
        sections=[Section(cols, rows, heading=heading, numeric=(1,)) for heading, cols, rows in sections],
    ).content
    figures = dict(summary)
    top = sections[0][2][0] if sections[0][2] else None
    sms = (f"{_company()} {day:%d %b}: revenue {figures['Revenue']} from {figures['Payments']} payments"
           + (f"; top plan {top[0]} ({top[1]})" if top else '')
           + f"; new customers {figures['New customers']}; active {figures['Active subscriptions']}.")
    return _send_to_superadmins('daily_report', title, text, html,
                                attachments=[(f'daily_report_{day}.pdf', pdf, 'application/pdf')], sms_text=sms)


# --------------------------------------------------------------- event emails

@shared_task
def email_vouchers_generated(batch_id):
    if not _enabled('admin_event_emails'):
        return 0
    from apps.billing.models import VoucherBatch

    batch = VoucherBatch.objects.select_related('plan', 'generated_by').filter(id=batch_id).first()
    if not batch:
        return 0
    vouchers = list(batch.vouchers.order_by('code'))
    plan = batch.plan.name if batch.plan else 'No plan'
    by = batch.generated_by.username if batch.generated_by else 'unknown'
    title = f"{len(vouchers)} voucher{'s' if len(vouchers) != 1 else ''} generated · {plan}"
    rows = [[v.code, plan, f'KES {float(v.amount):,.2f}'] for v in vouchers]
    intro = (f"<b>{escape(by)}</b> generated {len(vouchers)} voucher(s) for <b>{escape(plan)}</b> "
             f"at {timezone.localtime(batch.created_at):%d %b %Y %H:%M}."
             + (f"<br>Note: {escape(batch.note)}" if batch.note else ''))
    shown = rows[:100]
    sections = [('Voucher codes' + (' (first 100; all in the attached CSV)' if len(rows) > 100 else ''),
                 ['Code', 'Plan', 'Value'], shown)]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['Code', 'Plan', 'Value'])
    writer.writerows([[v.code, plan, v.amount] for v in vouchers])
    text = (f"{by} generated {len(vouchers)} voucher(s) for {plan}." + _text_sections(sections))
    codes = ', '.join(v.code for v in vouchers[:10]) + (' ...' if len(vouchers) > 10 else '')
    sms = f"{by} generated {len(vouchers)} voucher(s) for {plan}: {codes}"
    return _send_to_superadmins('admin_event', title, text, _html_page(title, intro, sections),
                                attachments=[(f'vouchers_batch_{batch.id}.csv', out.getvalue().encode(), 'text/csv')],
                                sms_text=sms)


@shared_task
def send_voucher_batch(batch_id, phones, emails, channels, sent_by=''):
    """
    Deliver a batch's unused codes to sales people (from the Vouchers page).
    Phones: one text per channel listing every code -- a long batch is
    several SMS parts, which is the price of having the codes on the phone.
    Emails: table plus CSV. Every attempt is in the notification log.
    """
    from apps.billing.models import VoucherBatch
    from apps.notifications.dispatch import send_and_log
    from apps.notifications.models import NotificationLog, NotificationSettings
    from apps.notifications.services.email_service import EmailService

    batch = VoucherBatch.objects.select_related('plan').filter(id=batch_id).first()
    if not batch:
        return 0
    vouchers = list(batch.vouchers.filter(status='active').order_by('code'))
    if not vouchers:
        return 0
    plan = batch.plan.name if batch.plan else f'KES {float(batch.value or 0):,.0f}'
    value = f'KES {float(vouchers[0].amount):,.0f}'
    head = f"{_company()} vouchers - {plan} ({value}), batch #{batch.id}, {len(vouchers)} code{'s' if len(vouchers) != 1 else ''}"
    short = head + ':\n' + '\n'.join(v.code for v in vouchers)

    delivered = 0
    for phone in dict.fromkeys(phones):
        for channel in channels:
            delivered += bool(send_and_log(channel=channel, recipient=phone, message=short,
                                           event_type='voucher_batch_sent')['success'])

    if emails and NotificationSettings.load().email_enabled:
        cols = ['Code', 'Plan', 'Value', 'Expires']
        rows = [[v.code, plan, value, f'{timezone.localtime(v.expiry_date):%d %b %Y}' if v.expiry_date else 'No expiry']
                for v in vouchers]
        intro = (f"{escape(sent_by or 'An admin')} sent you {len(vouchers)} unused voucher(s) for <b>{escape(plan)}</b> "
                 f"(batch #{batch.id}). Each code works once.")
        html = _html_page(f'Vouchers - {plan}', intro, [(None, cols, rows)])
        out = io.StringIO()
        csv.writer(out).writerows([cols] + rows)
        service = EmailService()
        for recipient in dict.fromkeys(emails):
            result = service.send_email(recipient, short, subject=head, html=html,
                                        attachments=[(f'vouchers_batch_{batch.id}.csv', out.getvalue().encode(), 'text/csv')])
            NotificationLog.objects.create(
                channel='email', event_type='voucher_batch_sent', recipient=recipient, message=short[:5000],
                status='sent' if result['success'] else 'failed',
                error='' if result['success'] else str(result.get('error', '')),
            )
            delivered += bool(result['success'])
    elif emails:
        logger.warning("Voucher batch %s: email not set up, %d email recipient(s) skipped", batch_id, len(emails))
    return delivered


@shared_task
def email_new_pppoe_customer(customer_id, source=''):
    if not _enabled('admin_event_emails'):
        return 0
    from apps.customers.models import Customer

    c = Customer.objects.filter(id=customer_id).first()
    if not c:
        return 0
    title = f"New PPPoE customer · {c.get_full_name() or c.username}"
    rows = [
        ['Username', c.username], ['Name', c.get_full_name() or '—'], ['Phone', c.phone_number or '—'],
        ['Email', c.email or '—'], ['PPPoE username', c.pppoe_username or '—'],
        ['Registered', f"{timezone.localtime(c.created_at):%d %b %Y %H:%M}"], ['How', source or '—'],
    ]
    sections = [('', ['Field', 'Value'], rows)]
    sms = f"New PPPoE customer: {c.get_full_name() or c.username} ({c.username}), {c.phone_number or 'no phone'}"
    return _send_to_superadmins('admin_event', title, _text_sections(sections),
                                _html_page(title, 'A new PPPoE customer was added.', sections), sms_text=sms)


@shared_task
def email_new_pppoe_import(customer_ids):
    """One summary for a bulk PPPoE import instead of an email per row."""
    if not _enabled('admin_event_emails') or not customer_ids:
        return 0
    from apps.customers.models import Customer

    customers = Customer.objects.filter(id__in=customer_ids).order_by('username')
    title = f"{customers.count()} PPPoE customers imported"
    rows = [[c.username, c.get_full_name() or '—', c.phone_number or '—'] for c in customers]
    sections = [('', ['Username', 'Name', 'Phone'], rows)]
    return _send_to_superadmins('admin_event', title, _text_sections(sections),
                                _html_page(title, 'New PPPoE customers from a bulk import.', sections),
                                sms_text=f"{title}.")


@shared_task
def email_manual_topup(transaction_id):
    if not _enabled('admin_event_emails'):
        return 0
    from apps.billing.models import Transaction

    t = Transaction.objects.select_related('customer', 'subscription__plan').filter(id=transaction_id).first()
    if not t:
        return 0
    c = t.customer
    kind = 'Manual top-up' if t.subscription_id else 'Cash added to balance'
    title = f"{kind} · {c.get_full_name() or c.username} · KES {float(t.amount):,.2f}"
    rows = [
        ['Customer', f"{c.get_full_name() or c.username} ({c.username})"],
        ['Amount', f"KES {float(t.amount):,.2f}"],
        ['Plan', t.subscription.plan.name if t.subscription_id else '— (balance)'],
        ['Expires', f"{timezone.localtime(t.subscription.expiry_date):%d %b %Y %H:%M}" if t.subscription_id else '—'],
        ['New balance', f"KES {float(c.account_balance):,.2f}"],
        ['Reference', t.transaction_id], ['Recorded by', t.notes or '—'],
        ['When', f"{timezone.localtime(t.created_at):%d %b %Y %H:%M}"],
    ]
    sections = [('', ['Field', 'Value'], rows)]
    return _send_to_superadmins('admin_event', title, _text_sections(sections),
                                _html_page(title, f'{kind} recorded by staff.', sections))
