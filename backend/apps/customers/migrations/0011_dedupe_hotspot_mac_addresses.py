from collections import defaultdict

from django.db import migrations
from django.utils import timezone


def detach_duplicate_macs(apps, schema_editor):
    Customer = apps.get_model('customers', 'Customer')
    Subscription = apps.get_model('billing', 'Subscription')
    now = timezone.now()

    by_mac = defaultdict(list)
    for customer in Customer.objects.exclude(hotspot_mac_address__isnull=True).exclude(hotspot_mac_address=''):
        by_mac[customer.hotspot_mac_address.strip().upper()].append(customer)

    for customers in by_mac.values():
        if len(customers) < 2:
            continue
        live_ids = set(
            Subscription.objects.filter(
                customer__in=customers, status='active', expiry_date__gt=now
            ).values_list('customer_id', flat=True)
        )
        # Keep the MAC on the customer with a live subscription, else the newest account.
        keep = next((c for c in customers if c.pk in live_ids), None) or max(customers, key=lambda c: c.pk)
        for customer in customers:
            if customer.pk != keep.pk and customer.pk not in live_ids:
                Customer.objects.filter(pk=customer.pk).update(hotspot_mac_address=None)


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0010_alter_customer_phone_number_optional'),
        ('billing', '0013_unique_billingplan_name'),
    ]

    operations = [
        migrations.RunPython(detach_duplicate_macs, migrations.RunPython.noop),
    ]
