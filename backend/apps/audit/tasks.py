import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('audit')


@shared_task
def purge_old_audit_logs():
    """
    Delete audit rows older than AUDIT_RETENTION_DAYS (default 365) -- the
    only way rows ever leave the log. In batches so one big purge doesn't
    hold a long lock on the Pi's Postgres.
    """
    from apps.audit.models import AuditLog
    days = getattr(settings, 'AUDIT_RETENTION_DAYS', 365)
    if not days:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    total = 0
    while True:
        ids = list(AuditLog.objects.filter(created_at__lt=cutoff).values_list('id', flat=True)[:5000])
        if not ids:
            break
        total += AuditLog.objects.filter(id__in=ids)._raw_delete(AuditLog.objects.db)
    logger.info('purge_old_audit_logs: removed %d rows older than %d days', total, days)
    return total
