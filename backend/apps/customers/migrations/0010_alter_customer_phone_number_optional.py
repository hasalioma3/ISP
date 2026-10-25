from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0009_customer_telegram_chat_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='phone_number',
            field=models.CharField(blank=True, db_index=True, default='', max_length=15),
        ),
    ]
