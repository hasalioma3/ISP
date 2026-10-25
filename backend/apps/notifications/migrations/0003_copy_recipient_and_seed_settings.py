from django.conf import settings
from django.db import migrations
from django.db.models import F


def copy_recipient_phone(apps, schema_editor):
    NotificationLog = apps.get_model('notifications', 'NotificationLog')
    NotificationLog.objects.filter(recipient_phone__gt='').update(recipient=F('recipient_phone'))


def seed_settings_from_env(apps, schema_editor):
    """
    Carries the already-working SMS flow's credentials from env vars into
    the new DB-backed settings, so it doesn't go dark on this deploy --
    the AFRICASTALKING_* env vars stay in settings.py as a rollback escape
    hatch for one release after this is confirmed working.
    """
    NotificationSettings = apps.get_model('notifications', 'NotificationSettings')
    ns, _ = NotificationSettings.objects.get_or_create(pk=1)
    ns.at_username = getattr(settings, 'AFRICASTALKING_USERNAME', '') or ''
    ns.at_sender_id = getattr(settings, 'AFRICASTALKING_SENDER_ID', '') or ''
    ns.at_environment = getattr(settings, 'AFRICASTALKING_ENVIRONMENT', 'sandbox') or 'sandbox'

    api_key = getattr(settings, 'AFRICASTALKING_API_KEY', '') or ''
    if api_key:
        # The historical model uses EncryptedCharField, which encrypts once
        # on save; assigning ciphertext here would encrypt it a second time.
        ns.at_api_key = api_key

    ns.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_notificationsettings_and_more'),
    ]

    operations = [
        migrations.RunPython(copy_recipient_phone, noop_reverse),
        migrations.RunPython(seed_settings_from_env, noop_reverse),
    ]
