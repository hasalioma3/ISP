import os
import django
from django.conf import settings
import routeros_api

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

def test_connection():
    host = settings.MIKROTIK_HOST
    username = settings.MIKROTIK_USERNAME
    password = settings.MIKROTIK_PASSWORD
    port = settings.MIKROTIK_PORT
    
    print(f"Testing connection to {host}:{port} as {username}...")
    
    try:
        connection = routeros_api.RouterOsApiPool(
            host,
            username=username,
            password=password,
            port=port,
            plaintext_login=True,
            use_ssl=False
        )
        api = connection.get_api()
        print("Connection successful!")
        
        print("Attempting to get /system/resource...")
        resource = api.get_resource('/system/resource')
        data = resource.get()
        print(f"System Resource: {data}")
        
        print("Attempting to get /ip/hotspot/user/profile...")
        profiles = api.get_resource('/ip/hotspot/user/profile')
        p_data = profiles.get()
        print(f"Hotspot Profiles Found: {len(p_data)}")
        for p in p_data:
            print(f" - {p.get('name')}")

        print("\n--- TEST 1: ADD Profile with SPACE ---")
        test_name = "Hotspot Test"
        rate_limit = "5M/5M"
        
        try:
            print(f"Adding profile '{test_name}' with rate-limit='{rate_limit}'...")
            profiles.add(name=test_name, **{'rate-limit': rate_limit, 'shared-users': '1'})
            print("ADD SUCCESS!")
        except Exception as e:
            print(f"ADD FAILED: {e}")
        
        # Simulate Service Behavior: Disconnect and Reconnect
        print("Disconnecting to mimic service behavior...")
        connection.disconnect()
        
        print("Reconnecting...")
        connection = routeros_api.RouterOsApiPool(
            host, username=username, password=password, port=port,
            plaintext_login=True, use_ssl=False
        )
        api = connection.get_api()
        profiles = api.get_resource('/ip/hotspot/user/profile')

        print("\n--- TEST 2: UPDATE Profile with SPACE ---")
        try:
            print(f"Updating profile '{test_name}'...")
            # Query by name with space
            existing = profiles.get(name=test_name)
            if existing:
                prof_id = existing[0]['id']
                print(f"Found ID: {prof_id}")
                profiles.set(id=prof_id, **{'rate-limit': '10M/10M'})
                print("UPDATE SUCCESS!")
            else:
                print("Profile not found for update test!")
        except Exception as e:
            print(f"UPDATE FAILED: {e}")

        print("\n--- TEST 3: CLEANUP ---")
        try:
            existing = profiles.get(name=test_name)
            for p in existing:
                profiles.remove(id=p['id'])
            print("CLEANUP SUCCESS!")
        except Exception as e:
            print(f"CLEANUP FAILED: {e}")

        connection.disconnect()
        print("\nTest Complete")
        
    except Exception as e:
        print(f"Test FAILED: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_connection()
