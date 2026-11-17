import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('cloud.billing')


@shared_task(bind=True, max_retries=8, default_retry_delay=30)
def verify_collection(self, collection_id):
    from cloud.billing.collections import verify
    from cloud.billing.models import Collection
    c = Collection.objects.filter(pk=collection_id).first()
    if not c or (c.verified and c.forwarded):
        return 'paid'
    state = verify(c)
    # Only "pending" is worth retrying (Safaricom still processing, or a
    # network error); "failed" means Safaricom has no such payment.
    if state == 'pending' and self.request.retries < self.max_retries:
        raise self.retry()
    if state == 'paid':
        from cloud.billing.invoicing import retry_open_invoices
        retry_open_invoices()
    return state


@shared_task
def verify_pending_collections():
    from cloud.billing.models import Collection
    for c in Collection.objects.filter(verified=False, source='stk', verify_attempts__lt=20,
                                       created_at__gte=timezone.now() - timedelta(days=3)):
        verify_collection.delay(c.pk)


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def forward_stk(self, tenant_id, body, collection_id=None):
    from cloud.billing.collections import ForwardError, forward_stk as forward
    from cloud.billing.models import Collection
    from cloud.tenants.models import Tenant
    tenant = Tenant.objects.get(pk=tenant_id)
    collection = Collection.objects.filter(pk=collection_id).first() if collection_id else None
    try:
        forward(tenant, body, collection)
    except ForwardError as e:
        logger.warning('Forwarding STK callback to %s failed: %s', tenant.slug, e)
        raise self.retry(countdown=min(3600, 60 * 2 ** self.request.retries))


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def forward_c2b(self, collection_id, account):
    from cloud.billing.collections import ForwardError, forward_c2b as forward
    from cloud.billing.models import Collection
    c = Collection.objects.select_related('tenant').get(pk=collection_id)
    try:
        forward(c, account)
    except ForwardError as e:
        logger.warning('Forwarding C2B %s to %s failed: %s', c.receipt, c.tenant.slug, e)
        raise self.retry(countdown=min(3600, 60 * 2 ** self.request.retries))


@shared_task
def submit_settlement(settlement_id):
    from cloud.billing.models import Settlement
    from cloud.billing.settlement import submit
    s = Settlement.objects.filter(pk=settlement_id).first()
    if s:
        submit(s)
        return s.status


@shared_task
def run_invoicing(force=False):
    from cloud.billing.invoicing import retry_open_invoices, run_monthly
    n = run_monthly(force=force)
    retry_open_invoices()
    return n


@shared_task
def run_scheduled_settlements(force=False):
    from cloud.billing.settlement import run_scheduled
    return run_scheduled(force=force)
