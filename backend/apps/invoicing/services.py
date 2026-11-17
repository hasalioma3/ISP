import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.invoicing.models import Invoice, InvoiceSettings

logger = logging.getLogger('apps.invoicing')

# Fixed-line customers get invoices; hotspot buyers are walk-up guests.
INVOICE_SERVICE_TYPES = ('pppoe', 'static', 'both')


class InvoiceError(Exception):
    pass


def _q(v):
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def next_number():
    with db_transaction.atomic():
        cfg = InvoiceSettings.objects.select_for_update().get_or_create(pk=1)[0]
        while True:
            number = f'{cfg.number_prefix}{cfg.next_number:05d}'
            cfg.next_number += 1
            if not Invoice.objects.filter(number=number).exists():
                break
        cfg.save(update_fields=['next_number'])
        return number


def compute_totals(lines, cfg=None):
    """-> (clean lines, subtotal, vat_rate, tax, total). Line amounts are as
    entered; with VAT-inclusive prices the tax is carved out of the total,
    otherwise it's added on top."""
    cfg = cfg or InvoiceSettings.load()
    clean, gross = [], Decimal('0')
    for line in lines or []:
        desc = str(line.get('description') or '').strip()
        try:
            qty = Decimal(str(line.get('quantity') or 1))
            price = Decimal(str(line.get('unit_price') if line.get('unit_price') not in (None, '') else line.get('amount') or 0))
        except Exception:
            raise InvoiceError('Quantities and prices must be numbers.')
        if not desc:
            raise InvoiceError('Every line needs a description.')
        if qty <= 0 or price < 0:
            raise InvoiceError('Quantity must be above 0 and price 0 or more.')
        amount = _q(qty * price)
        clean.append({'description': desc[:300], 'quantity': str(qty.normalize()), 'unit_price': str(_q(price)),
                      'amount': str(amount)})
        gross += amount
    if not clean:
        raise InvoiceError('Add at least one line.')
    rate = cfg.vat_rate if cfg.vat_registered else Decimal('0')
    if not rate:
        return clean, gross, Decimal('0'), Decimal('0'), gross
    if cfg.prices_include_vat:
        tax = _q(gross * rate / (100 + rate))
        return clean, gross - tax, rate, tax, gross
    tax = _q(gross * rate / 100)
    return clean, gross, rate, tax, gross + tax


def _bill_to(customer):
    previous = Invoice.objects.filter(customer=customer).exclude(customer_pin='').order_by('-id').first()
    return {
        'customer_name': customer.get_full_name() or customer.username,
        'customer_phone': customer.phone_number or '',
        'customer_email': customer.email or '',
        'customer_pin': previous.customer_pin if previous else '',
        'customer_address': previous.customer_address if previous else '',
    }


def create_invoice(customer, lines, actor=None, transaction=None, template=None, status='issued',
                   issue_date=None, notes='', overrides=None, sign=None):
    cfg = InvoiceSettings.load()
    clean, subtotal, rate, tax, total = compute_totals(lines, cfg)
    issue_date = issue_date or timezone.localdate()
    data = {**_bill_to(customer), **{k: v for k, v in (overrides or {}).items() if v is not None}}
    paid = total if status == 'paid' else Decimal('0')
    inv = Invoice.objects.create(
        number=next_number(), customer=customer, transaction=transaction,
        template=template or cfg.default_template, status=status, issue_date=issue_date,
        due_date=issue_date + timedelta(days=cfg.due_days), lines=clean, subtotal=subtotal, vat_rate=rate,
        tax=tax, total=total, amount_paid=paid,
        payment_ref=(transaction.mpesa_receipt_number or transaction.transaction_id) if transaction else '',
        notes=notes, created_by=actor, **data,
    )
    should_sign = cfg.etims_enabled and (cfg.etims_auto_sign if sign is None else sign)
    if should_sign:
        from apps.invoicing import etims
        try:
            etims.sign(inv)
        except etims.EtimsError as e:
            logger.warning('Invoice %s created but not signed by eTIMS: %s', inv.number, e)
    return inv


def lines_for_transaction(txn):
    sub = txn.subscription
    if sub:
        plan = sub.plan
        start = timezone.localtime(txn.created_at).date()
        end = timezone.localtime(sub.expiry_date).date()
        desc = f'{plan.name} internet ({plan.download_speed}/{plan.upload_speed} Mbps), {start:%d %b %Y} - {end:%d %b %Y}'
    else:
        desc = 'Internet service - payment on account'
    return [{'description': desc, 'quantity': 1, 'unit_price': str(txn.amount)}]


def invoice_for_transaction(txn, actor=None, template=None, overrides=None, sign=None):
    """The (paid) invoice for a completed payment; returns the existing one
    if the payment already has an invoice."""
    existing = Invoice.objects.filter(transaction=txn).first()
    if existing:
        return existing, False
    if txn.status != 'completed':
        raise InvoiceError('Only completed payments can be invoiced.')
    if txn.customer.service_type not in INVOICE_SERVICE_TYPES:
        raise InvoiceError('Invoices are for PPPoE and static IP customers.')
    if Decimal(str(txn.amount or 0)) <= 0:
        raise InvoiceError('This payment has no amount to invoice.')
    if txn.payment_method == 'balance':
        raise InvoiceError('This purchase was paid from account balance; invoice the payment that funded it.')
    inv = create_invoice(txn.customer, lines_for_transaction(txn), actor=actor, transaction=txn, template=template,
                         status='paid', issue_date=timezone.localtime(txn.created_at).date(), overrides=overrides,
                         sign=sign)
    return inv, True


def void(invoice, actor=None):
    if invoice.status == 'void':
        return invoice
    if invoice.etims_status == 'signed':
        from apps.invoicing import etims
        etims.credit_note(invoice)
    invoice.status = 'void'
    invoice.save(update_fields=['status', 'updated_at'])
    return invoice


def send(invoice):
    """Email the PDF to the customer. -> (ok, error)."""
    from apps.invoicing.pdf import render_pdf
    from apps.notifications.dispatch import send_and_log
    from apps.notifications.services.email_service import EmailService
    from apps.notifications.templates import render

    email = invoice.customer_email or invoice.customer.email
    if not email:
        return False, 'The customer has no email address.'
    message = render('invoice_sent', {'number': invoice.number, 'total': f'{invoice.total:,.2f}',
                                      'date': f'{invoice.issue_date:%d %b %Y}'}, invoice.customer)
    pdf = render_pdf(invoice)
    result = EmailService().send_email(email, message, subject=f'Invoice {invoice.number}',
                                       attachments=[(f'{invoice.number}.pdf', pdf, 'application/pdf')])
    from apps.notifications.models import NotificationLog
    NotificationLog.objects.create(customer=invoice.customer, channel='email', event_type='invoice', recipient=email,
                                   message=message, status='sent' if result['success'] else 'failed',
                                   error='' if result['success'] else str(result.get('error', '')))
    if result['success']:
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=['sent_at'])
    return result['success'], result.get('error', '')
