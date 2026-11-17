import logging

from celery import shared_task

logger = logging.getLogger('apps.invoicing')


@shared_task
def invoice_transaction(transaction_id):
    from apps.billing.models import Transaction
    from apps.invoicing.models import InvoiceSettings
    from apps.invoicing.services import InvoiceError, invoice_for_transaction, send
    txn = Transaction.objects.select_related('customer', 'subscription__plan').filter(pk=transaction_id).first()
    if not txn:
        return
    try:
        inv, created = invoice_for_transaction(txn)
    except InvoiceError as e:
        logger.info('No invoice for transaction %s: %s', transaction_id, e)
        return
    if created and InvoiceSettings.load().auto_send:
        send(inv)
    return inv.number


@shared_task
def retry_failed_signing():
    """Invoices that eTIMS rejected or couldn't be reached for: try again (daily)."""
    from apps.invoicing import etims
    from apps.invoicing.models import Invoice, InvoiceSettings
    if not InvoiceSettings.load().etims_enabled:
        return 0
    ok = 0
    for inv in Invoice.objects.filter(etims_status__in=['failed', 'pending']).exclude(status='void')[:200]:
        try:
            etims.sign(inv)
            ok += 1
        except etims.EtimsError:
            continue
    return ok
