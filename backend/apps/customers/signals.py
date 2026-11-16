from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Customer
from apps.network.services.network_automation import network_automation
from apps.billing.models import Subscription
import logging

logger = logging.getLogger(__name__)

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
            # Best-effort: this fires on ANY Customer save (e.g. a self-
            # service profile edit, an admin changing an email address),
            # most of which have nothing to do with network state. Raising
            # here would fail an unrelated save just because the router
            # happened to be unreachable at that moment.
            try:
                network_automation.activate_customer(instance, sub.plan)
            except Exception as e:
                logger.error(f"Failed to re-sync {instance.username} to router on customer save: {e}")



@receiver(post_save, sender=Customer)
def email_superadmins_on_new_pppoe_customer(sender, instance, created, **kwargs):
    """
    Superadmins get an email for every new PPPoE customer, however they were
    created (self-registration, manual add, a PPPoE voucher). The bulk import
    suppresses these and sends one summary instead.
    """
    if not created or instance.is_staff or instance.service_type not in ('pppoe', 'both'):
        return
    from django.db import transaction
    from apps.notifications.admin_emails import email_new_pppoe_customer, new_customer_emails_suppressed
    if new_customer_emails_suppressed():
        return
    transaction.on_commit(lambda: email_new_pppoe_customer.delay(instance.id), robust=True)
