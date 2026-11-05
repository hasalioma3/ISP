from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('network', '0006_router_uplink_mbps'),
    ]

    operations = [
        migrations.AlterField(
            model_name='activesession',
            name='session_type',
            field=models.CharField(
                choices=[('pppoe', 'PPPoE'), ('hotspot', 'Hotspot'), ('static', 'Static IP')],
                max_length=10,
            ),
        ),
    ]
