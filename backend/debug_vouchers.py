import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from apps.billing.models import Voucher

print("Checking last 10 vouchers:")
for v in Voucher.objects.order_by('-created_at')[:10]:
    print(f"ID: {v.id}, Code: '{v.code}', Batch: {v.batch_id}")
