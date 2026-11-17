"""Earn points when a payment Transaction is saved as completed. Runs after
the surrounding DB transaction commits so a rolled-back payment earns
nothing, and never breaks the payment flow if something goes wrong."""
import logging

from django.db import transaction as db_transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger('apps.loyalty')


@receiver(post_save, sender='billing.Transaction')
def earn_on_payment(sender, instance, **kwargs):
    if instance.status != 'completed':
        return
    pk = instance.pk

    def award():
        from apps.billing.models import Transaction
        from apps.loyalty.services import award_for_transaction
        try:
            txn = Transaction.objects.select_related('customer').filter(pk=pk).first()
            if txn:
                award_for_transaction(txn)
        except Exception:
            logger.exception('Loyalty: awarding points for transaction %s failed', pk)

    db_transaction.on_commit(award)
