from celery import shared_task
from django.utils import timezone


@shared_task
def scheduled_archive():
    """Hourly beat entry; archives once a day, in the hour set in settings."""
    from apps.archive.models import ArchiveSettings
    from apps.archive.service import run_all
    cfg = ArchiveSettings.load()
    now = timezone.localtime()
    if not cfg.enabled or now.hour != cfg.hour:
        return 0
    if cfg.last_run_at and timezone.localtime(cfg.last_run_at).date() == now.date():
        return 0
    return sum(r.rows for r in run_all('schedule'))


@shared_task
def archive_now(triggered_by=''):
    from apps.archive.service import run_all
    return sum(r.rows for r in run_all(triggered_by or 'manual', force=True))
