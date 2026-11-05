from django.db import migrations


def remove_cpe_sync_schedule(apps, schema_editor):
    # TR-069/GenieACS was removed. DatabaseScheduler never deletes rows for
    # entries dropped from celery.py's beat_schedule, so without this beat
    # keeps firing the now-unregistered apps.tr069.tasks.sync_cpe_devices.
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name='sync-cpe-devices').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('network', '0008_static_queue_counter'),
        ('django_celery_beat', '0018_improve_crontab_helptext'),
    ]

    operations = [
        migrations.RunPython(remove_cpe_sync_schedule, migrations.RunPython.noop),
    ]
