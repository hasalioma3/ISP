from django.db import transaction as db_transaction
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='billing.Transaction')
def auto_invoice(sender, instance, **kwargs):
    """With auto-invoicing on, invoice each completed PPPoE/static payment.
    Delayed a little: the payment processor links the subscription to the
    transaction just after creating it, and the invoice line names the plan."""
    if instance.status != 'completed' or instance.payment_method == 'balance':
        return
    from apps.invoicing.models import InvoiceSettings
    from apps.invoicing.services import INVOICE_SERVICE_TYPES
    if not InvoiceSettings.load().auto_invoice:
        return
    if getattr(instance.customer, 'service_type', None) not in INVOICE_SERVICE_TYPES:
        return
    pk = instance.pk
    from apps.invoicing.tasks import invoice_transaction
    db_transaction.on_commit(lambda: invoice_transaction.apply_async(args=[pk], countdown=20))
