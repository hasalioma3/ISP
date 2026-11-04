from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0009_alter_transaction_payment_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='billingplan',
            name='is_promo',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='voucher',
            name='used_mac',
            field=models.CharField(blank=True, db_index=True, max_length=17),
        ),
    ]
