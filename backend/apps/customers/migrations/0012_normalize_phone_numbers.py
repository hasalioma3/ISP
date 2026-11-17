"""
Repair phone numbers stored in the bare nine-digit form ("725316559") --
which SMS and STK rejected as invalid -- by adding the 254 country code, and
recompute phone_hash so C2B matching (which hashes the 254... form) finds
these customers. Numbers already in 07... or 254... form are left alone, and
usernames are never touched (they're logins and router secrets).
"""
import hashlib

from django.db import migrations


def forwards(apps, schema_editor):
    Customer = apps.get_model('customers', 'Customer')
    for c in Customer.objects.exclude(phone_number='').only('id', 'phone_number').iterator():
        raw = (c.phone_number or '').strip()
        digits = ''.join(ch for ch in raw if ch.isdigit())
        if len(digits) == 9 and digits[0] in '17' and not raw.startswith('+'):
            full = '254' + digits
            Customer.objects.filter(pk=c.pk).update(phone_number=full, phone_hash=hashlib.sha256(full.encode()).hexdigest())


class Migration(migrations.Migration):
    dependencies = [('customers', '0011_dedupe_hotspot_mac_addresses')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
