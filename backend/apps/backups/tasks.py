import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.backups.models import Backup, BackupSettings

logger = logging.getLogger('backups')


def start_backup(kind='manual', user=None):
    """Create the Backup row and queue the work. Returns (backup, error)."""
    running = Backup.objects.filter(status='running', created_at__gte=timezone.now() - timedelta(hours=6)).first()
    if running:
        return None, f'A backup is already running (started {timezone.localtime(running.created_at):%H:%M}).'
    backup = Backup.objects.create(kind=kind, created_by=user)
    run_backup.delay(backup.pk)
    return backup, None


@shared_task(soft_time_limit=3 * 3600)
def run_backup(backup_id):
    from apps.backups import runner
    backup = Backup.objects.filter(pk=backup_id).first()
    if not backup:
        return
    runner.run(backup)
    cfg = BackupSettings.load()
    if backup.status != 'failed' and cfg.gdrive_enabled and cfg.gdrive_refresh_token:
        runner.upload(backup)
    from apps.backups.nas import is_configured
    if backup.status != 'failed' and cfg.nas_enabled and is_configured(cfg):
        runner.upload_nas(backup)
    runner.prune()
    if 'failed' in (backup.status, backup.remote_status, backup.nas_status):
        try:
            from apps.notifications.admin_emails import notify_admins
            if backup.status == 'failed':
                what = backup.error
            else:
                what = '\n'.join(msg for bad, msg in (
                    (backup.remote_status == 'failed', f'Google Drive upload failed: {backup.remote_error}'),
                    (backup.nas_status == 'failed', f'NAS upload failed: {backup.nas_error}'),
                ) if bad)
            notify_admins('admin_event', f'Backup problem: {backup.filename or backup.pk}',
                          f'The {backup.kind} backup at {timezone.localtime(backup.created_at):%d %b %H:%M} '
                          f'had a problem:\n\n{what}\n\nSee Settings -> Backups.',
                          sms_text=f'Backup problem: {what[:120]}')
        except Exception:
            logger.exception('Could not notify admins about backup %s', backup_id)
    return backup.status


@shared_task
def upload_backup(backup_id, target='gdrive'):
    from apps.backups import runner
    backup = Backup.objects.filter(pk=backup_id).first()
    if backup:
        (runner.upload_nas if target == 'nas' else runner.upload)(backup)
        runner.prune()


@shared_task
def scheduled_backup(force=False):
    """Hourly from beat; starts the scheduled backup in the configured hour (and weekday)."""
    cfg = BackupSettings.load()
    if not cfg.schedule_enabled:
        return None
    now = timezone.localtime()
    if not force:
        if now.hour != cfg.hour:
            return None
        if cfg.frequency == 'weekly' and now.weekday() != cfg.weekday:
            return None
    since = now - timedelta(hours=20 if cfg.frequency == 'daily' else 24 * 6)
    if not force and Backup.objects.filter(kind='scheduled', created_at__gte=since).exclude(status='failed').exists():
        return None
    backup, error = start_backup('scheduled')
    if error:
        logger.warning('Scheduled backup skipped: %s', error)
        return None
    return backup.pk
