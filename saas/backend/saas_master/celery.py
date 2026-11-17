import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'saas_master.settings')

app = Celery('saas_master')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
