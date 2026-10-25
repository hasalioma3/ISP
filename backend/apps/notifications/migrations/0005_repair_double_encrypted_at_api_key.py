from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import migrations


def repair_double_encrypted_api_key(apps, schema_editor):
    NotificationSettings = apps.get_model('notifications', 'NotificationSettings')
    settings_row = NotificationSettings.objects.filter(pk=1).first()
    if not settings_row or not settings_row.at_api_key:
        return

    fernet = Fernet(settings.NOTIFICATIONS_ENCRYPTION_KEY.encode())
    try:
        plaintext = fernet.decrypt(settings_row.at_api_key.encode()).decode()
    except InvalidToken:
        return

    # A successful second decrypt means the key was stored as encrypted
    # ciphertext rather than plaintext by migration 0003.
    settings_row.at_api_key = plaintext
    settings_row.save(update_fields=['at_api_key'])


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0004_remove_recipient_phone'),
    ]

    operations = [
        migrations.RunPython(repair_double_encrypted_api_key, migrations.RunPython.noop),
    ]
