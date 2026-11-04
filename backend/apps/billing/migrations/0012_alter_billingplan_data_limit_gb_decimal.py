import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_billingplan_fup_subscription_fup_applied'),
    ]

    operations = [
        migrations.AlterField(
            model_name='billingplan',
            name='data_limit_gb',
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text='Data limit in GB (null for unlimited)',
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]