
import os
import django
import sys
from django.conf import settings

# Setup Django
# Setup Django
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

# --- MONKEY PATCH START (Required for v7) ---
import routeros_api.sentence
_original_parse = routeros_api.sentence.ResponseSentence.parse

@classmethod
def patched_parse(cls, serialized):
    if isinstance(serialized, list):
        new_serialized = []
        for item in serialized:
            if item == b'!empty':
                new_serialized.append(b'!re')
            else:
                new_serialized.append(item)
        serialized = new_serialized
    return _original_parse(serialized)

routeros_api.sentence.ResponseSentence.parse = patched_parse
# --- MONKEY PATCH END ---

from apps.network.services.mikrotik_service import MikroTikService

def update_walled_garden():
    print("--- Checking Walled Garden ---")
    mt = MikroTikService()
    
    laptop_ip = "192.168.88.10"
    
    print(f"1. Checking IP: {laptop_ip}")
    try:
        conn = mt._get_connection()
        api = conn.get_api()
        
        # Check /ip/hotspot/walled-garden/ip
        wg_ip = api.get_resource('/ip/hotspot/walled-garden/ip')
        existing = wg_ip.get(**{'dst-address': laptop_ip})
        
        # Filter out empty results from patch
        existing = [e for e in existing if 'dst-address' in e and e['dst-address'] == laptop_ip]
        
        if not existing:
            print(f"   Adding {laptop_ip} to Walled Garden IP List...")
            wg_ip.add(**{'dst-address': laptop_ip, 'action': 'accept', 'comment': 'Laptop Local Portal'})
            print("   SUCCESS: Added IP.")
        else:
            print("   ALREADY EXISTS: IP is whitelisted.")
            
        conn.disconnect()
        
    except Exception as e:
        print(f"   ERROR: {e}")

if __name__ == "__main__":
    update_walled_garden()
