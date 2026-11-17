"""
Celery configuration for ISP Billing System
"""
import os
from datetime import timedelta
from celery import Celery
from celery.schedules import crontab
from celery.signals import beat_init

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')

app = Celery('isp_billing')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# Cap/FUP overshoot is roughly (poll interval x line speed), so keep this short.
USAGE_POLL_SECONDS = max(int(os.environ.get('USAGE_POLL_SECONDS', '15')), 5)

# Celery Beat Schedule
app.conf.beat_schedule = {
    'check-expired-subscriptions': {
        'task': 'apps.network.tasks.check_expired_subscriptions',
        'schedule': crontab(minute='*'),  # Run every minute
    },
    'cleanup-pending-payments': {
        'task': 'apps.payments.tasks.cleanup_pending_payments',
        'schedule': crontab(minute='*/30'),  # Run every 30 minutes
    },
    'collect-usage-statistics': {
        'task': 'apps.network.tasks.collect_usage_statistics',
        'schedule': timedelta(seconds=USAGE_POLL_SECONDS),
    },
    'enforce-subscription-data-limits': {
        'task': 'apps.network.tasks.enforce_subscription_data_limits',
        'schedule': crontab(minute='*'),
    },
    'enforce-subscription-fup': {
        'task': 'apps.network.tasks.enforce_subscription_fup',
        'schedule': crontab(minute='*'),
    },
    'send-daily-sales-report': {
        'task': 'apps.notifications.admin_emails.send_daily_report',
        'schedule': crontab(hour=23, minute=0),  # 11 pm EAT (CELERY_TIMEZONE)
    },
    'send-expiry-reminders': {
        'task': 'apps.notifications.tasks.send_expiry_reminders',
        # Hourly; the task itself only sends in the hour chosen under
        # Settings -> Notifications -> Renewal reminders.
        'schedule': crontab(minute=0),
    },
    'scheduled-backup': {
        'task': 'apps.backups.tasks.scheduled_backup',
        'schedule': crontab(minute=10),  # hourly; runs in the hour set under Settings -> Backups
    },
    'purge-old-audit-logs': {
        'task': 'apps.audit.tasks.purge_old_audit_logs',
        'schedule': crontab(hour=3, minute=30),
    },
    'send-expired-followup': {
        'task': 'apps.notifications.tasks.send_expired_followup',
        'schedule': crontab(minute=5),  # hourly; sends at expired_followup_hour
    },
    'scheduled-archive': {
        'task': 'apps.archive.tasks.scheduled_archive',
        'schedule': crontab(minute=40),  # hourly; archives in the hour set under Settings -> Archive
    },
    'expire-loyalty-points': {
        'task': 'apps.loyalty.tasks.expire_points',
        'schedule': crontab(hour=1, minute=15),
    },
    'retry-etims-signing': {
        'task': 'apps.invoicing.tasks.retry_failed_signing',
        'schedule': crontab(hour='*/6', minute=25),
    },
}

@beat_init.connect
def sync_usage_poll_schedule(**kwargs):
    # DatabaseScheduler never rewrites an existing row's schedule type, so force it.
    try:
        from django_celery_beat.models import IntervalSchedule, PeriodicTask
        interval, _ = IntervalSchedule.objects.get_or_create(
            every=USAGE_POLL_SECONDS, period=IntervalSchedule.SECONDS
        )
        PeriodicTask.objects.filter(name='collect-usage-statistics').update(
            interval=interval, crontab=None, solar=None, clocked=None
        )
    except Exception as e:
        print(f'Could not sync usage poll schedule: {e}')


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
