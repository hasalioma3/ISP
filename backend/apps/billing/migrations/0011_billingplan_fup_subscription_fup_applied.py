from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0010_billingplan_is_promo_voucher_used_mac'),
    ]

    operations = [
        migrations.AddField(
            model_name='billingplan',
            name='fup_limit_gb',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='billingplan',
            name='fup_download_speed',
            field=models.PositiveIntegerField(blank=True, help_text='FUP download speed in Mbps', null=True),
        ),
        migrations.AddField(
            model_name='billingplan',
            name='fup_upload_speed',
            field=models.PositiveIntegerField(blank=True, help_text='FUP upload speed in Mbps', null=True),
        ),
        migrations.AddField(
            model_name='subscription',
            name='fup_applied',
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name='billingplan',
            constraint=models.CheckConstraint(
                check=(
                    Q(fup_limit_gb__isnull=True, fup_download_speed__isnull=True, fup_upload_speed__isnull=True)
                    | (
                        Q(fup_limit_gb__gt=0, fup_download_speed__gt=0, fup_upload_speed__gt=0)
                        & Q(fup_download_speed__lte=F('download_speed'))
                        & Q(fup_upload_speed__lte=F('upload_speed'))
                        & (Q(data_limit_gb__isnull=True) | Q(fup_limit_gb__lt=F('data_limit_gb')))
                    )
                ),
                name='billing_plan_fup_valid',
            ),
        ),
    ]