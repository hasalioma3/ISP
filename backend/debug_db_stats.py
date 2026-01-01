import os
import django
import sys
from django.db.models import Sum

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from apps.network.models import RouterInterfaceStat
from apps.billing.models import UsageRecord

print("\n--- Router Interface Stats ---")
stats = RouterInterfaceStat.objects.all()
for s in stats:
    print(f"Router: {s.router.name} | Iface: {s.interface_name} | RX: {s.rx_bps} | TX: {s.tx_bps} | Updated: {s.updated_at}")

agg = RouterInterfaceStat.objects.aggregate(
    total_rx=Sum('rx_bps'),
    total_tx=Sum('tx_bps')
)
print(f"Aggregation: {agg}")

print("\n--- Latest Usage Record ---")
rec = UsageRecord.objects.last()
if rec:
    print(f"User: {rec.customer.username} | Up: {rec.upload_speed_mbps} | Down: {rec.download_speed_mbps} | Time: {rec.updated_at}")
else:
    print("No usage records.")
