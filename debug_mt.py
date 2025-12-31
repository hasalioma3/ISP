
import os
import django
import sys
from django.conf import settings

# Setup Django
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

# --- MONKEY PATCH START ---
import routeros_api.sentence

# Save original functionality
_original_parse = routeros_api.sentence.ResponseSentence.parse

@classmethod
def patched_parse(cls, serialized):
    # Fix for RouterOS v7 returning !empty
    # serialized is a list of bytes, e.g. [b'!empty', b'.tag=2']
    # If we treat !empty as !done, we close too early and the real !done crashes us later.
    # Treat !empty as !re (intermediate result) so we consume the full sequence.
    if isinstance(serialized, list):
        new_serialized = []
        for item in serialized:
            if item == b'!empty':
                new_serialized.append(b'!re')
            else:
                new_serialized.append(item)
        serialized = new_serialized
        
    return _original_parse(serialized)

# Apply patch
routeros_api.sentence.ResponseSentence.parse = patched_parse
print("🔧 Applied !empty -> !re monkey patch to routeros_api")
# --- MONKEY PATCH END ---

from apps.network.models import Router
from apps.network.services.mikrotik_service import mikrotik_service
import logging

# Configure logging to stdout
logging.basicConfig(level=logging.DEBUG)

def debug_mikrotik_update():
    print("--- Starting Debug (Patched v4 - !re) ---")
    
    # 1. Test Connection
    print("1. Testing Connection...")
    try:
        connection = mikrotik_service._get_connection()
        print("   Connection Successful!")
    except Exception as e:
        print(f"   Connection Failed: {e}")
        return

    api = connection.get_api()
    hotspot_user = api.get_resource('/ip/hotspot/user')

    # 2. Search for User
    username = "ali"
    password = "ali" # Temporary password
    profile = "default" # Fallback profile
    mac = "C2:A7:CE:CA:00:98"
    
    print(f"2. Searching for user '{username}'...")
    try:
        users = hotspot_user.get(name=username)
        # Filter out "empty" results caused by the patch
        # Valid user has 'name' and 'id'
        users = [u for u in users if 'name' in u and u['name'] == username]
    except Exception as e:
        print(f"   User Search FAILED: {e}")
        return
    
    if not users:
        print("   User NOT FOUND! Attempting Creation...")
        try:
            # We must pass Strings for arguments
            hotspot_user.add(name=username, password=password, profile=profile, **{'mac-address': mac})
            print("   Creation SUCCESS!")
            return
        except Exception as e:
             print(f"   Creation FAILED: {e}")
             return
    else:
        print(f"   User FOUND: {users[0]['id']}")

    # 3. Attempt Update
    print(f"3. Attempting Update (MAC: {mac})...")
    try:
        hotspot_user.set(id=users[0]['id'], **{'mac-address': mac})
        print("   Update MAC SUCCESS!")
    except Exception as e:
        print(f"   Update MAC FAILED: {e}")

    connection.disconnect()
    print("--- End Debug ---")

if __name__ == "__main__":
    debug_mikrotik_update()
