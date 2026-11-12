"""
Router reachability, kept on the Router row (is_online, last_seen_at,
last_health, ...) so pages can render the last known state instantly
instead of contacting each router inside the request.

Writers: the usage poll (every USAGE_POLL_SECONDS, which also re-checks
offline routers so they flip back online by themselves) and every live
health read. Readers: the health endpoint, the MikroTik page, Online Users
and the customer's own session widget.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('apps.network')

HEALTH_FIELDS = (
    'cpu_load', 'memory_used_pct', 'disk_used_pct', 'uptime', 'board_name',
    'version', 'wan_interface', 'wan_rx_bytes', 'wan_tx_bytes',
)


def mark_online(router, health=None):
    from apps.network.models import Router

    now = timezone.now()
    fields = {'is_online': True, 'status_checked_at': now, 'last_seen_at': now, 'last_error': ''}
    if health:
        fields['last_health'] = {k: health.get(k) for k in HEALTH_FIELDS}
    if router.is_online is False:
        logger.warning("Router %s (%s) is reachable again", router.name, router.ip_address)
    Router.objects.filter(pk=router.pk).update(**fields)
    for k, v in fields.items():
        setattr(router, k, v)


def mark_offline(router, error):
    from apps.network.models import Router

    fields = {
        'is_online': False,
        'status_checked_at': timezone.now(),
        'last_error': str(error or 'Unreachable')[:255],
    }
    if router.is_online is not False:
        logger.warning("Router %s (%s) is unreachable: %s", router.name, router.ip_address, error)
    Router.objects.filter(pk=router.pk).update(**fields)
    for k, v in fields.items():
        setattr(router, k, v)


def known_offline(router):
    """
    True when the router was found unreachable recently enough to skip a
    live attempt. Once the recheck window passes a request may try it again,
    so a router still comes back even with the Celery workers stopped.
    """
    if router.is_online is not False or not router.status_checked_at:
        return False
    window = timedelta(seconds=settings.MIKROTIK_OFFLINE_RECHECK_SECONDS)
    return timezone.now() - router.status_checked_at < window


def cached_health(router):
    """The health payload built from the stored state, without contacting the router."""
    return {
        'success': False,
        'online': False,
        'cached': True,
        'error': router.last_error or 'Unreachable',
        'last_seen_at': router.last_seen_at.isoformat() if router.last_seen_at else None,
        'checked_at': router.status_checked_at.isoformat() if router.status_checked_at else None,
        'last_health': router.last_health,
    }
