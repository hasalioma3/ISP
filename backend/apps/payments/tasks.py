"""
Celery tasks for payment processing
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from apps.payments.models import PaymentRequest
import logging

logger = logging.getLogger('mpesa')


@shared_task
def cleanup_pending_payments():
    """
    Clean up pending payment requests that have timed out
    Runs every 30 minutes via Celery Beat
    """
    logger.info("Cleaning up pending payments...")
    
    # Find payment requests that have been pending for more than 5 minutes
    timeout_threshold = timezone.now() - timedelta(minutes=5)
    
    timed_out_payments = PaymentRequest.objects.filter(
        status='pending',
        created_at__lte=timeout_threshold
    )
    
    timed_out = list(timed_out_payments.select_related('customer'))
    count = timed_out_payments.update(status='timeout')

    # A till payment held back as 'awaiting_stk' for one of these requests
    # never got its STK callback -- the money arrived via C2B all the same,
    # so apply it now the normal C2B way (plan by amount, else balance).
    from apps.payments.models import C2BPayment
    from apps.payments.services.payment_processor import payment_processor
    for request in timed_out:
        for c2b in C2BPayment.objects.filter(
            status='awaiting_stk', matched_customer=request.customer, amount=request.amount,
        ):
            try:
                payment_processor.apply_c2b_payment(c2b, request.customer)
            except Exception as e:
                logger.error(f"Could not apply awaiting C2B payment {c2b.transaction_id}: {e}")

    logger.info(f"Marked {count} payments as timed out")
    return count
