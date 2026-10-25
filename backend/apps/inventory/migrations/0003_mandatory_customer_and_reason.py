from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_backfill_customer_before_required'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inventoryusage',
            name='customer',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_used_on', to='customers.customer',
            ),
        ),
        migrations.RemoveField(
            model_name='inventoryusage',
            name='used_for',
        ),
        migrations.AddField(
            model_name='inventoryusage',
            name='reason',
            field=models.CharField(
                choices=[
                    ('new_install', 'New Install'),
                    ('repair', 'Repair'),
                    ('migration', 'Migration'),
                    ('office_setup', 'Office Setup'),
                    ('other', 'Other'),
                ],
                default='other', max_length=20,
            ),
            preserve_default=False,
        ),
    ]
