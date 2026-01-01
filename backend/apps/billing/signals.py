
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from apps.billing.models import BillingPlan
from apps.network.tasks import sync_plan_to_routers
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=BillingPlan)
def sync_plan_on_save(sender, instance, created, **kwargs):
    """
    Trigger sync when plan details change
    """
    # We defer the actual sync to allow M2M relations to be set if this is a new object
    # But for M2M updates, m2m_changed covers it.
    # For simple field updates (price, speed), we need to sync to all associated routers.
    if not created:
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
    Trigger network automation when a Subscription is created or updated
    """
    if instance.status == 'active' and not instance.is_expired:
        network_automation.activate_customer(instance.customer, instance.plan)
    elif instance.status in ['expired', 'cancelled', 'suspended']:
        network_automation.suspend_customer(instance.customer)
