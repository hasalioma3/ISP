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
    'send-expiry-reminders': {
        'task': 'apps.notifications.tasks.send_expiry_reminders',
        'schedule': crontab(hour=8, minute=0),  # Once daily -- covers both the 3-day and day-of stages
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
