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

    # System Configuration

    def configure_radius_client(self, address, secret, comment='ISP Billing'):
        """
        Configure Radius Client for Hotspot and PPP
        """
        try:
            connection = self._get_connection()
            api = connection.get_api()
            radius = api.get_resource('/radius')
            
            # Check for existing config for this server
            existing = radius.get(address=address)
            
            # Prepare params
            params = {
                'address': address,
                'secret': secret,
                'service': 'hotspot,ppp',
                'timeout': '3000ms',
                'comment': comment
            }
            
            if existing:
                # Update existing
                radius.set(id=existing[0]['id'], **params)
            else:
                # Create new
                radius.add(**params)
                
            # Enable incoming Radius if needed (for CoA)
            radius_incoming = api.get_resource('/radius/incoming')
            radius_incoming.set(accept='yes', port='3799')
            
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to configure Radius: {str(e)}")
            return {'success': False, 'error': str(e)}

    def enable_service_radius(self):
        """
        Enable use-radius for Hotspot and PPPoE Server Profiles
        """
        try:
            connection = self._get_connection()
            api = connection.get_api()
            
            # 1. Update Hotspot Server Profiles
            hs_profile = api.get_resource('/ip/hotspot/profile') 
            profiles = hs_profile.get()
            for profile in profiles:
                try:
                    hs_profile.set(id=profile['id'], **{'use-radius': 'yes', 'login-by': 'http-chap,cookie'})
                except Exception as e:
                    logger.warning(f"Failed to update HS profile {profile.get('name')}: {e}")

            # 2. Update PPP Secrets/Profiles? 
            # Actually PPP usage of Radius is enabled in PPP Secrets -> PPP Authentication / PPP Server
            # Usually for PPPoE Servers, we set 'authentication=pap,chap,mschap1,mschap2' and 'one-session-per-host=yes'
            # And crucially, checking "Use Radius" in PPP -> Secrets -> PPP Authentication is not a thing on RouterOS v6/v7 directly
            # It's usually the PPPoE Server service that is told to use Radius.
            
            pppoe_server = api.get_resource('/interface/pppoe-server/server')
            servers = pppoe_server.get()
            for server in servers:
                try:
                    pppoe_server.set(id=server['id'], **{'authentication': 'pap,chap,mschap1,mschap2', 'one-session-per-host': 'yes', 'use-radius': 'yes'})
                except Exception as e:
                    logger.warning(f"Failed to update PPPoE server {server.get('service-name')}: {e}")

            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to enable service Radius: {str(e)}")
            return {'success': False, 'error': str(e)}

    # Network Setup Helpers

    def create_bridge(self, name):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            bridge = api.get_resource('/interface/bridge')
            existing = bridge.get(name=name)
            if not existing:
                bridge.add(name=name)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_port_to_bridge(self, bridge, interface):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            port = api.get_resource('/interface/bridge/port')
            # Check if port is already in ANY bridge (might be in a different one)
            # Or specifically in this one.
            # Best effort: remove from others? No, that's dangerous.
            # Just check if 'interface' exists in port list.
            existing = port.get(interface=interface)
            if existing:
                # Already a port, check if bridge matches
                if existing[0].get('bridge') != bridge:
                    # Move it? Or error? Let's move it for auto-fix.
                    port.set(id=existing[0]['id'], bridge=bridge)
            else:
                port.add(bridge=bridge, interface=interface)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_ip_address(self, address, interface, comment=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ip_addr = api.get_resource('/ip/address')
            # Check overlap generally?
            # Or just check if exact address exists on interface
            # 'address' is like '10.5.50.1/24'
            # API returns 'address' like '10.5.50.1/24'
            
            # Search by interface first to reduce load
            existing = ip_addr.get(interface=interface)
            
            # Simple check: is this subnet already there?
            # If we try to add 10.5.50.1/24 but 10.5.50.2/24 exists, RouterOS usually allows multiple IPs.
            # But for gateway, we usually want one.
            
            # Let's just try to add if exact match not found.
            found = False
            for entry in existing:
                if entry.get('address') == address:
                    found = True
                    break
            
            if not found:
                ip_addr.add(address=address, interface=interface, comment=comment)

            connection.disconnect()
            return {'success': True}
        except Exception as e:
             return {'success': False, 'error': str(e)}

    def add_ip_pool(self, name, ranges):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            pool = api.get_resource('/ip/pool')
            existing = pool.get(name=name)
            if existing:
                if existing[0].get('ranges') != ranges:
                    pool.set(id=existing[0]['id'], ranges=ranges)
            else:
                pool.add(name=name, ranges=ranges)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_hotspot_server_profile(self, name, dns_name, html_directory='hotspot'):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hs_profile = api.get_resource('/ip/hotspot/profile')
            existing = hs_profile.get(name=name)
            params = {
                'name': name,
                'dns-name': dns_name,
                'html-directory': html_directory,
                'use-radius': 'yes',
                'login-by': 'http-chap,cookie,mac-cookie'
            }
            if existing:
                hs_profile.set(id=existing[0]['id'], **params)
            else:
                hs_profile.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_hotspot_server(self, name, interface, profile, address_pool):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hs_server = api.get_resource('/ip/hotspot')
            existing = hs_server.get(name=name)
            params = {
                'name': name,
                'interface': interface,
                'profile': profile,
                'address-pool': address_pool,
                'disabled': 'no'
            }
            if existing:
                hs_server.set(id=existing[0]['id'], **params)
            else:
                hs_server.add(**params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def upload_file(self, filename, content):
        """
        Upload (create/overwrite) a file on the router with specific content
        """
        try:
            connection = self._get_connection()
            api = connection.get_api()
            file_resource = api.get_resource('/file')
            
            # Check if file exists to update, or create new
            # Note: Creating a file via API is usually done by 'print' to file or just setting contents if it exists.
            # But the proper way for 'new' file via API is tricky. 
            # Often assumes file exists. 
            # However, we can try to 'set' contents on existing, or if not exists, we might need a workaround.
            # Workaround: Use /tool/fetch if possible? No.
            # Correct API way: 
            # 1. find file
            # 2. set contents
            
            existing = file_resource.get(name=filename)
            if existing:
                 file_resource.set(id=existing[0]['id'], contents=content)
            else:
                # To create a file, we can't just .add() easily in all versions.
                # But 'add' with name/contents is supported in later ROS or via skins.
                # Standard workaround: just try .add
                try:
                    file_resource.add(name=filename, contents=content)
                except Exception as add_err:
                    # Fallback: Can't create file directly?
                    logger.warning(f"Could not add file directly: {add_err}")
                    pass
            
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # DHCP Server Management

    def add_dhcp_server(self, name, interface, address_pool, disabled='no', lease_time='1h'):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            dhcp_server = api.get_resource('/ip/dhcp-server')
            
            existing = dhcp_server.get(name=name)
            params = {
                'name': name,
                'interface': interface,
                'address-pool': address_pool,
                'disabled': disabled,
                'lease-time': lease_time,
                'add-arp': 'yes'
            }
            
            if existing:
                dhcp_server.set(id=existing[0]['id'], **params)
            else:
                dhcp_server.add(**params)
                
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_dhcp_network(self, address, gateway, dns_server='8.8.8.8,8.8.4.4', comment=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            dhcp_network = api.get_resource('/ip/dhcp-server/network')
            
            # Check existing by address
            existing = dhcp_network.get(address=address)
            params = {
                'address': address,
                'gateway': gateway,
                'dns-server': dns_server,
                'comment': comment
            }
            
            if existing:
                dhcp_network.set(id=existing[0]['id'], **params)
            else:
                dhcp_network.add(**params)
                
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Default instance
mikrotik_service = MikroTikService()
