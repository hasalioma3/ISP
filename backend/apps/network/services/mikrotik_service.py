"""
MikroTik RouterOS API Service
Handles PPPoE and Hotspot user management via MikroTik API
"""

import logging
from routeros_api import RouterOsApiPool
from django.conf import settings

logger = logging.getLogger('mikrotik')

# --- MONKEY PATCH FOR ROUTEROS v7 ---
# Checks for !empty response and converts to !re to prevent library crash
import routeros_api.sentence

# Save original functionality
_original_parse = routeros_api.sentence.ResponseSentence.parse

def patched_parse(cls, serialized):
    if isinstance(serialized, list):
        clean_serialized = []
        tag_value = None
        
        for item in serialized:
            if item == b'!empty':
                # Convert !empty to !re so the parser receives a valid 'Result' frame
                # This will create an empty dict {} in the results, which we must handle downstream.
                clean_serialized.append(b'!re')
                continue
            
            if item.startswith(b'.tag='):
                # Extract tag manually to bypass parser validation
                try:
                    tag_value = item.split(b'=', 1)[1]
                except:
                    pass
            else:
                clean_serialized.append(item)
                
        # Parse the clean list using original method
        try:
            parsed = _original_parse(clean_serialized)
        except IndexError:
             # If clean_serialized is empty (shouldn't happen if !empty->!re), fallback
             return _original_parse([b'!re'])

        # Inject tag back if found
        if tag_value is not None:
             # Set both attribute and the tag property usually used by the library
            if hasattr(parsed, 'attributes') and isinstance(parsed.attributes, dict):
                # Library expects keys to be bytes (it decodes them later)
                # Value should also be bytes
                try:
                    parsed.attributes[b'.tag'] = tag_value
                except:
                    pass
            
            # Critical: Update the tag property.
            parsed.tag = tag_value
            
        return parsed
        
    return _original_parse(serialized)

# Apply patch
routeros_api.sentence.ResponseSentence.parse = classmethod(patched_parse)
# --- END MONKEY PATCH ---

class MikroTikService:
    """
    MikroTik RouterOS API integration
    """
    
    def __init__(self, host=None, username=None, password=None, port=None, use_ssl=False):
        self.host = host or settings.MIKROTIK_HOST
        self.username = username or settings.MIKROTIK_USERNAME
        self.password = password or settings.MIKROTIK_PASSWORD
        self.port = port or settings.MIKROTIK_PORT
        self.use_ssl = use_ssl or settings.MIKROTIK_USE_SSL
        
    def _get_connection(self):
        """
        Get connection to MikroTik router
        """
        try:
            connection = RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                plaintext_login=True
            )
            return connection
        except Exception as e:
            logger.error(f"Failed to connect to MikroTik {self.host}: {str(e)}")
            raise
    
    # PPPoE Secret Management
    
    def add_pppoe_secret(self, username, password, profile, service='any', local_address='', remote_address=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ppp_secret = api.get_resource('/ppp/secret')
            ppp_secret.add(
                name=username,
                password=password,
                profile=profile,
                service=service,
                **({'local-address': local_address} if local_address else {}),
                **({'remote-address': remote_address} if remote_address else {})
            )
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to add PPPoE secret {username}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def update_pppoe_secret(self, username, **kwargs):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ppp_secret = api.get_resource('/ppp/secret')
            secrets = ppp_secret.get(name=username)
            if not secrets or (secrets and not secrets[0].get('id')):
                connection.disconnect()
                return {'success': False, 'error': 'Secret not found'}
            ppp_secret.set(id=secrets[0]['id'], **kwargs)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to update PPPoE secret {username}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def disable_pppoe_secret(self, username):
        return self.update_pppoe_secret(username, disabled='yes')
    
    def disconnect_pppoe_session(self, username):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ppp_active = api.get_resource('/ppp/active')
            sessions = ppp_active.get(name=username)
            # Filter out empty results (ghost records)
            sessions = [s for s in sessions if s.get('id')]
            for session in sessions:
                ppp_active.remove(id=session['id'])
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to disconnect PPPoE session {username}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    # Hotspot User Management
    
    def add_hotspot_user(self, username, password, profile, mac_address='', limit_uptime='', limit_bytes_total=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_user = api.get_resource('/ip/hotspot/user')
            params = {'name': username, 'password': password, 'profile': profile}
            if mac_address: params['mac-address'] = mac_address
            if limit_uptime: params['limit-uptime'] = limit_uptime
            if limit_bytes_total: params['limit-bytes-total'] = str(limit_bytes_total)
            hotspot_user.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to add Hotspot user {username}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def update_hotspot_user(self, username, **kwargs):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_user = api.get_resource('/ip/hotspot/user')
            users = hotspot_user.get(name=username)
            if not users or (users and not users[0].get('id')):
                connection.disconnect()
                return {'success': False, 'error': 'User not found'}
            
            # Handle potential param mapping
            if 'mac_address' in kwargs:
                kwargs['mac-address'] = kwargs.pop('mac_address')
                
            hotspot_user.set(id=users[0]['id'], **kwargs)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to update Hotspot user {username}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def disable_hotspot_user(self, username):
        return self.update_hotspot_user(username, disabled='yes')
    
    def disconnect_hotspot_session(self, username):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_active = api.get_resource('/ip/hotspot/active')
            sessions = hotspot_active.get(user=username)
            logger.info(f"Disconnect Hotspot: Found {len(sessions)} sessions for {username}")
            # Filter out empty results
            sessions = [s for s in sessions if s.get('id')]
            for session in sessions:
                logger.info(f"Removing Hotspot session: {session['id']}")
                hotspot_active.remove(id=session['id'])
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to disconnect Hotspot session {username}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def remove_hotspot_cookie(self, username):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_cookie = api.get_resource('/ip/hotspot/cookie')
            cookies = hotspot_cookie.get(user=username)
            logger.info(f"Suspend Cookie: Found {len(cookies)} cookies for {username}")
            # Filter out empty results
            cookies = [c for c in cookies if c.get('id')]
            for cookie in cookies:
                hotspot_cookie.remove(id=cookie['id'])
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to remove Hotspot cookie {username}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def disconnect_hotspot_by_mac(self, mac_address):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_active = api.get_resource('/ip/hotspot/active')
            sessions = hotspot_active.get(**{'mac-address': mac_address})
            # Filter out empty results
            sessions = [s for s in sessions if s.get('id')]
            for session in sessions:
                hotspot_active.remove(id=session['id'])
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to disconnect Hotspot session for MAC {mac_address}: {str(e)}")
            return {'success': False, 'error': str(e)}

    # Profile Management
    
    def add_pppoe_profile(self, name, rate_limit=None, on_up=None, on_down=None):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ppp_profile = api.get_resource('/ppp/profile')
            params = {'name': name, 'local-address': '10.0.0.1', 'dns-server': '8.8.8.8,8.8.4.4'}
            if rate_limit: params['rate-limit'] = rate_limit
            if on_up: params['on-up'] = on_up
            if on_down: params['on-down'] = on_down
            ppp_profile.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_pppoe_profile(self, name, rate_limit=None, on_up=None, on_down=None):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ppp_profile = api.get_resource('/ppp/profile')
            profiles = ppp_profile.get()
            profile = next((p for p in profiles if p.get('name') == name), None)
            if not profile:
                connection.disconnect()
                return {'success': False, 'error': 'Profile not found'}
            params = {}
            if rate_limit: params['rate-limit'] = rate_limit
            if on_up: params['on-up'] = on_up
            if on_down: params['on-down'] = on_down
            if params: ppp_profile.set(id=profile['id'], **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_hotspot_profile(self, name, rate_limit=None):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_profile = api.get_resource('/ip/hotspot/user/profile')
            params = {'name': name, 'shared-users': '1'}
            if rate_limit: params['rate-limit'] = rate_limit
            hotspot_profile.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_hotspot_profile(self, name, rate_limit=None):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_profile = api.get_resource('/ip/hotspot/user/profile')
            profiles = hotspot_profile.get()
            profile = next((p for p in profiles if p.get('name') == name), None)
            if not profile:
                connection.disconnect()
                return {'success': False, 'error': 'Profile not found'}
            params = {}
            if rate_limit: params['rate-limit'] = rate_limit
            if params: hotspot_profile.set(id=profile['id'], **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # Address List Management
    
    def add_to_address_list(self, list_name, address, comment=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            address_list = api.get_resource('/ip/firewall/address-list')
            address_list.add(list=list_name, address=address, comment=comment)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def remove_from_address_list(self, list_name, address):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            address_list = api.get_resource('/ip/firewall/address-list')
            entries = address_list.get(list=list_name, address=address)
            # Filter out empty results
            entries = [e for e in entries if e.get('id')]
            for entry in entries:
                address_list.remove(id=entry['id'])
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # Walled Garden Management

    def add_walled_garden_ip(self, dst_address, comment='', action='accept'):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            walled_garden = api.get_resource('/ip/hotspot/walled-garden/ip')
            # Check if exists
            params = {'dst-address': dst_address, 'action': action}
            existing = walled_garden.get(**params)
            # Check if truly exists (ignore ghost records)
            exists = existing and existing[0].get('id')
            if not exists:
                params['comment'] = comment
                walled_garden.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def remove_walled_garden_ip(self, dst_address):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            walled_garden = api.get_resource('/ip/hotspot/walled-garden/ip')
            entries = walled_garden.get(**{'dst-address': dst_address})
            # Filter out empty results
            entries = [e for e in entries if e.get('id')]
            for entry in entries:
                walled_garden.remove(id=entry['id'])
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_walled_garden_host(self, dst_host, comment=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            walled_garden = api.get_resource('/ip/hotspot/walled-garden')
            params = {'dst-host': dst_host}
            existing = walled_garden.get(**params)
            # Check if truly exists
            exists = existing and existing[0].get('id')
            if not exists:
                params['comment'] = comment
                walled_garden.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_dns_static(self, name, address, comment=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            dns_static = api.get_resource('/ip/dns/static')
            params = {'name': name, 'address': address}
            existing = dns_static.get(**params)
            # Check if truly exists
            exists = existing and existing[0].get('id')
            if not exists:
                params['comment'] = comment
                dns_static.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Default instance
mikrotik_service = MikroTikService()
