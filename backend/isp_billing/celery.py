"""
Celery configuration for ISP Billing System
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')

app = Celery('isp_billing')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

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
    'collect-usage-stats': {
        'task': 'apps.network.tasks.collect_usage_statistics',
        'schedule': 1.0,  # Run every 1 second (Ultra High frequency)
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
