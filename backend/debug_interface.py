import os
import django
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from apps.network.models import Router
from apps.network.services.mikrotik_service import MikroTikService

routers = Router.objects.filter(is_active=True)
for router in routers:
    print(f"\n--- Router: {router.name} ---")
    try:
        service = MikroTikService(
            host=router.ip_address,
            username=router.username,
            password=router.password,
            port=router.port,
            use_ssl=router.use_ssl
        )
        conn = service._get_connection()
        api = conn.get_api()
        
        # 1. List Interfaces
        print("\nListing Interfaces:")
        interfaces = api.get_resource('/interface').get()
        bridge_name = None
        for i in interfaces:
            print(f"Name: {i.get('name')} | Type: {i.get('type')}")
            if i.get('type') == 'bridge' and not bridge_name:
                bridge_name = i.get('name')
            if i.get('name') == 'hotspot-bridge':
                bridge_name = 'hotspot-bridge'
                
        print(f"\nTargeting Bridge: {bridge_name}")
        
        targets = ['ether1', 'bridge', 'hotspot-bridge']
        
        for t in targets:
            print(f"\nMonitoring {t}...")
            try:
                stats = api.get_resource('/interface').call('monitor-traffic', {
                    'interface': t, 
                    'once': 'true'
                })
                print(f"{t} Stats: {stats}")
            except Exception as e:
                print(f"Could not monitor {t}: {e}")
            
        conn.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
