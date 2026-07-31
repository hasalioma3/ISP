
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from apps.billing.models import BillingPlan
from apps.network.tasks import sync_plan_to_routers
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=BillingPlan)
def sync_plan_on_save(sender, instance, created, **kwargs):
    """
    Trigger sync when plan details change -- including on creation. This
    runs async (.delay()), so by the time a worker actually picks it up,
    any M2M `routers` set via the same request's serializer.save() is
    already committed; there's no real timing hazard to defer for. Skipping
    this on creation used to mean a brand-new plan's PPP/Hotspot profile
    never got pushed to any router until it was edited at least once --
    silently breaking activation for every customer assigned to it in the
    meantime (see sync_plan_to_routers' router-selection fallback for the
    other half of this: a plan with no routers explicitly assigned needs
    the same "fall back to all active routers" treatment activate_customer
    already has).
    """
    sync_plan_to_routers.delay(instance.id)

@receiver(m2m_changed, sender=BillingPlan.routers.through)
def sync_plan_on_routers_change(sender, instance, action, **kwargs):
    """
    Trigger sync when routers are added/removed
    """
    if action in ["post_add", "post_remove", "post_clear"]:
        sync_plan_to_routers.delay(instance.id)

from apps.billing.models import Subscription
from apps.network.services.network_automation import network_automation

@receiver(post_save, sender=Subscription)
def sync_subscription_on_save(sender, instance, created, **kwargs):
    """
    Trigger network automation when a Subscription is created or updated,
    and keep Customer.status in sync with it -- Customer has no expiry of
    its own, so this is the only place that status reflects reality. Only
    applied when this is the customer's most recent subscription, so an
    older one expiring can't clobber a newer active one's status.
    """
    is_latest = not Subscription.objects.filter(
        customer=instance.customer, created_at__gt=instance.created_at
    ).exists()

    if instance.status == 'active' and not instance.is_expired:
        network_automation.activate_customer(instance.customer, instance.plan)
        if is_latest and instance.customer.status != 'active':
            instance.customer.status = 'active'
            instance.customer.save(update_fields=['status'])
    elif instance.status in ['expired', 'cancelled', 'suspended']:
        # Best-effort: the subscription is genuinely expired/cancelled
        # regardless of whether the router happens to be reachable right
        # now, so a suspend failure is logged, not raised -- letting it
        # raise here would roll back this very save() and leave the
        # subscription stuck 'active' forever, retried every minute by
        # check_expired_subscriptions with no way to ever succeed.
        result = network_automation.suspend_customer(instance.customer)
        if not result.get('success'):
            logger.error(f"Failed to suspend {instance.customer.username} on expiry: {result.get('error')}")
        if is_latest:
            new_status = 'suspended' if instance.status == 'cancelled' else instance.status
            if instance.customer.status != new_status:
                instance.customer.status = new_status
                instance.customer.save(update_fields=['status'])
