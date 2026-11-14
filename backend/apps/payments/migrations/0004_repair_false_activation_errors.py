"""
One-off repair: till (C2B) payments marked 'error' ("Activation failed")
although a completed Transaction with the same M-Pesa code exists -- almost
always a portal STK payment, whose STK callback activated the plan before
the till's C2B confirmation for the same code hit "duplicate key" (see
process_c2b_confirmation). Re-links them and sets the real status.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    C2BPayment = apps.get_model('payments', 'C2BPayment')
    Transaction = apps.get_model('billing', 'Transaction')
    for payment in C2BPayment.objects.filter(status='error'):
        # Mostly portal (STK) payments: the STK callback created the
        # Transaction, then the till's C2B confirmation for the same code hit
        # "duplicate key" and was stamped 'error'.
        twin = Transaction.objects.filter(transaction_id=payment.transaction_id, status='completed').first()
        if not twin:
            continue
        payment.matched_customer_id = twin.customer_id
        payment.status = 'activated' if twin.subscription_id else 'matched_no_plan'
        payment.linked_transaction_id = twin.id
        payment.subscription_id = twin.subscription_id
        payment.notes = (payment.notes + ' | ' if payment.notes else '') + 'Status repaired: activation had succeeded.'
        payment.save(update_fields=['status', 'matched_customer', 'linked_transaction', 'subscription', 'notes'])


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0003_alter_c2bpayment_msisdn'),
        ('billing', '0014_reconcile_customer_status'),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
