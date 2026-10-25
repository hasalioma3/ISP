import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_mandatory_customer_and_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventorypurchase',
            name='attachment',
            field=models.FileField(blank=True, null=True, upload_to='inventory/purchases/%Y/%m/', validators=[django.core.validators.FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png', 'heic'])]),
        ),
    ]
