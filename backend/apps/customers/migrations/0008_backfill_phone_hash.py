from django.db import migrations

from apps.payments.services.phone_hash import hash_phone


def backfill_phone_hash(apps, schema_editor):
    Customer = apps.get_model('customers', 'Customer')
    for customer in Customer.objects.exclude(phone_number='').iterator():
        Customer.objects.filter(pk=customer.pk).update(
            phone_hash=hash_phone(customer.phone_number)
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0007_customer_phone_hash'),
    ]

    operations = [
        migrations.RunPython(backfill_phone_hash, noop),
    ]
