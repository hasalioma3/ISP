import os
import django
import sys
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
        
        # 1. Hotspot Active to get User -> IP
        print("Fetching Active Users...")
        active = api.get_resource('/ip/hotspot/active').get()
        for u in active:
            print(f"User: {u.get('user')} | Server: {u.get('server')} | Uptime: {u.get('uptime')}")
        
        # 2. Simple Queues
        print("\nFetching Queues...")
        # Note: Dynamic queues often have name=<hotspot-user>
        queues = api.get_resource('/queue/simple').get()
        for q in queues:
            name = q.get('name')
            target = q.get('target')
            rate = q.get('rate') # Max Limit usually
            
            # Print ALL keys for the first queue to find 'current rate'
            print(f"Queue: {name} | Keys: {q.keys()}")
            print(f"Rate Field: {rate}")
            
            # Try to get stats? 'print stats' equivalent?
            # routeros_api doesn't support 'print stats' easily unless via command.
            # But sometimes it's included?
            
        conn.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
