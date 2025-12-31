from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Customer
from apps.network.services.network_automation import network_automation
from apps.billing.models import Subscription

@receiver(post_save, sender=Customer)
def sync_customer_to_router_on_save(sender, instance, **kwargs):
    """
    Trigger network automation when a Customer is saved.
    This handles updates to service_type, MAC address, etc.
    """
    # Only sync if we have an active subscription or if status is active
    # We check if there's an active subscription for this customer
    has_active_sub = Subscription.objects.filter(
        customer=instance, 
        status='active'
    ).exists()

    if has_active_sub or instance.status == 'active':
        # Get the latest active plan if exists
        sub = Subscription.objects.filter(customer=instance, status='active').order_by('-created_at').first()
        if sub:
            network_automation.activate_customer(instance, sub.plan)
