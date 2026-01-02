"""
Celery tasks for billing automation
"""
from celery import shared_task
from django.utils import timezone
from apps.billing.models import Subscription
from apps.network.services.network_automation import network_automation
import logging

logger = logging.getLogger('apps.billing')


@shared_task
def check_expired_subscriptions():
    """
    Check for expired subscriptions and suspend network access
    Runs every hour via Celery Beat
    """
    logger.info("Checking for expired subscriptions...")
    
    # Find expired subscriptions that are still marked as active
    expired_subscriptions = Subscription.objects.filter(
        status='active',
        expiry_date__lte=timezone.now()
    )
    
    count = 0
    for subscription in expired_subscriptions:
        try:
            # Update subscription status
            subscription.status = 'expired'
            subscription.save()
            
            # Suspend network access
            result = network_automation.suspend_customer(subscription.customer)
            
            # Update Customer status to 'expired'
            customer = subscription.customer
            customer.status = 'expired'
            customer.save()
            
            if result['success']:
                logger.info(f"Suspended customer: {customer.username}")
                count += 1
            else:
                logger.error(f"Failed to suspend {customer.username} (Network): {result.get('error')}")
        
        except Exception as e:
            logger.error(f"Error processing subscription {subscription.id}: {str(e)}", exc_info=True)
    
    logger.info(f"Suspended {count} expired subscriptions")
    return count
