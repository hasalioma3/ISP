"""
One-off repair: customers who hold a live (active, unexpired) subscription
but are marked expired/suspended/pending -- e.g. an old subscription's
expiry overwrote the status after they had already renewed. From now on
apps.billing.services.reconcile_customer_statuses keeps this in step after
every expiry check; this fixes the rows already wrong. DB update only, no
router calls (the routers already follow the live subscription).
"""
from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    Subscription = apps.get_model('billing', 'Subscription')
    Customer = apps.get_model('customers', 'Customer')
    live = Subscription.objects.filter(status='active', expiry_date__gt=timezone.now()).values('customer_id')
    Customer.objects.filter(id__in=live, is_staff=False).exclude(status='active').update(status='active')


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0013_unique_billingplan_name'),
        ('customers', '0001_initial'),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
