from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_copy_recipient_and_seed_settings'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notificationlog',
            name='recipient_phone',
        ),
    ]
