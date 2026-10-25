from django.contrib.auth.hashers import make_password
from django.db import migrations


def migrate_used_for_and_backfill_customer(apps, schema_editor):
    """
    Runs in its OWN migration/transaction, separate from the schema changes
    in 0003 -- Postgres refuses an ALTER TABLE on a table that still has
    pending trigger events (e.g. from an UPDATE that touched a FK column)
    within the same transaction. Splitting into two migrations means this
    one's UPDATE fully commits before 0003's ALTER TABLE ever runs.
    """
    InventoryUsage = apps.get_model('inventory', 'InventoryUsage')
    Customer = apps.get_model('customers', 'Customer')

    # Fold any freeform "used for" text into notes before the column is
    # dropped, so nothing already recorded there is silently lost.
    for usage in InventoryUsage.objects.exclude(used_for=''):
        prefix = f"Used for: {usage.used_for}"
        usage.notes = f"{prefix}\n{usage.notes}" if usage.notes else prefix
        usage.save(update_fields=['notes'])

    # Any usage not yet tied to a customer (the old used_for-only path)
    # needs a real one now -- route it to a dedicated internal-use account
    # rather than blocking the next migration or losing the history.
    if InventoryUsage.objects.filter(customer__isnull=True).exists():
        internal_customer, created = Customer.objects.get_or_create(
            username='internal-use',
            defaults={
                'first_name': 'Internal',
                'last_name': 'Use',
                'phone_number': '',
                'status': 'active',
                'is_verified': True,
            }
        )
        if created:
            # Historical models (from apps.get_model) don't carry methods
            # inherited from AbstractUser like set_unusable_password() --
            # only make_password(None)'s actual field value is available here.
            internal_customer.password = make_password(None)
            internal_customer.save()
        InventoryUsage.objects.filter(customer__isnull=True).update(customer_id=internal_customer.id)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
        ('customers', '0008_backfill_phone_hash'),
    ]

    operations = [
        migrations.RunPython(migrate_used_for_and_backfill_customer, noop),
    ]
