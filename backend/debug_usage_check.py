import os
import django
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from apps.billing.models import UsageRecord
from apps.network.tasks import collect_usage_statistics

from apps.network.models import Router
from apps.network.services.mikrotik_service import MikroTikService

from apps.network.models import Router
from apps.network.services.mikrotik_service import MikroTikService
from apps.customers.models import Customer
from apps.billing.models import Subscription

routers = Router.objects.filter(is_active=True)
if not routers.exists():
    print("No active routers.")
    exit()

for router in routers:
    print(f"\n--- Checking Router: {router.name} ({router.ip_address}) ---")
    try:
        service = MikroTikService(
            host=router.ip_address,
            username=router.username,
            password=router.password,
            port=router.port,
            use_ssl=router.use_ssl
        )
        conn = service._get_connection() # Use _get_connection like tasks.py
        api = conn.get_api()
        
        # 1. Hotspot Users
        print("Fetching /ip/hotspot/active ...")
        hotspot_active = api.get_resource('/ip/hotspot/active').get()
        print(f"Count: {len(hotspot_active)}")
        for i, session in enumerate(hotspot_active):
            user = session.get('user')
            bytes_in = session.get('bytes-in')
            bytes_out = session.get('bytes-out')
            print(f"[{i}] User: '{user}' | In: {bytes_in} | Out: {bytes_out}")
            
            # Check DB Match
            cust = Customer.objects.filter(username=user).first()
            if cust:
                print(f"    -> MATCH DB Customer: {cust.username}")
                sub = Subscription.objects.filter(customer=cust, status='active').last()
                if sub:
                    print(f"    -> MATCH Active Subscription: {sub.plan.name}")
                else:
                    print("    -> NO Active Subscription found!")
            else:
                print("    -> NO DB Customer match!")

        # 2. PPPoE Interfaces
        print("\nFetching /interface (pppoe-in) ...")
        interfaces = api.get_resource('/interface').get()
        pppoe_interfaces = [i for i in interfaces if i.get('type') == 'pppoe-in']
        print(f"Count: {len(pppoe_interfaces)}")
        for i, iface in enumerate(pppoe_interfaces):
            name = iface.get('name')
            rx = iface.get('rx-byte')
            tx = iface.get('tx-byte')
            print(f"[{i}] Name: '{name}' | RX: {rx} | TX: {tx}")
            
        conn.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

