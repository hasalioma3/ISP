import logging

from celery import shared_task

from cloud.tenants.models import Tenant

logger = logging.getLogger('cloud.tenants')


@shared_task(soft_time_limit=3600)
def provision_tenant(tenant_id):
    from cloud.tenants.services import provision
    return provision(tenant_id).status


@shared_task
def tenant_action(tenant_id, action, actor_id=None, **kwargs):
    """Instance actions run here (the worker holds the Docker socket)."""
    from django.contrib.auth import get_user_model
    from cloud.tenants import services
    tenant = Tenant.objects.get(pk=tenant_id)
    actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
    try:
        if action == 'suspend':
            services.suspend(tenant, kwargs.get('reason') or 'suspended by the platform', actor=actor)
        elif action == 'resume':
            services.resume(tenant, actor=actor)
        elif action == 'cancel':
            services.cancel(tenant, actor=actor)
        elif action == 'destroy':
            services.destroy(tenant, actor=actor)
        elif action == 'resync':
            services.resync(tenant, actor=actor)
        elif action == 'restart':
            from cloud.tenants.orchestrator import get_orchestrator
            orch = get_orchestrator()
            orch.stop(tenant)
            orch.start(tenant)
            services.log(tenant, 'instance', 'Instance restarted', actor=actor)
        elif action == 'extend_trial':
            services.extend_trial(tenant, int(kwargs.get('days') or 1), actor=actor)
        elif action == 'metrics':
            services.refresh_metrics(tenant)
        elif action == 'health':
            services.check_health(tenant)
    except Exception as e:
        logger.exception('Tenant %s action %s failed', tenant.slug, action)
        tenant.last_error = str(e)[:4000]
        tenant.save(update_fields=['last_error'])
        services.log(tenant, 'error', f'{action} failed: {str(e)[:500]}', actor=actor)
        return 'failed'
    return 'ok'


@shared_task
def resync_all():
    from cloud.tenants.services import resync
    for t in Tenant.objects.filter(status__in=Tenant.LIVE):
        try:
            resync(t)
        except Exception:
            logger.exception('Resync of %s failed', t.slug)


@shared_task
def run_lifecycle():
    from cloud.tenants.services import run_lifecycle as run
    return run()


@shared_task
def refresh_all_metrics():
    from cloud.tenants.services import refresh_metrics
    n = 0
    for t in Tenant.objects.filter(status__in=Tenant.LIVE):
        try:
            refresh_metrics(t)
            n += 1
        except Exception:
            logger.exception('Metrics for %s failed', t.slug)
    return n


@shared_task
def check_all_health():
    from cloud.tenants.services import check_health
    for t in Tenant.objects.filter(status__in=Tenant.LIVE):
        try:
            check_health(t)
        except Exception:
            logger.exception('Health check of %s failed', t.slug)
