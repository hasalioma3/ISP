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
    
    count = timed_out_payments.update(status='timeout')
    
    logger.info(f"Marked {count} payments as timed out")
    return count
