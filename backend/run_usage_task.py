import os
import django
import sys
# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from apps.network.tasks import collect_usage_statistics
from apps.billing.models import UsageRecord

print(f"UsageRecords BEFORE: {UsageRecord.objects.count()}")

print("Running Task...")
collect_usage_statistics()

print(f"UsageRecords AFTER: {UsageRecord.objects.count()}")
latest = UsageRecord.objects.order_by('-created_at').first()
if latest:
    print(f"Latest: {latest} | Bytes: {latest.total_bytes}")
