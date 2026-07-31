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
            
            # Handle potential param mapping. An empty mac-address isn't "no
            # change" to RouterOS -- it's rejected outright ("invalid value
            # of mac-address, mac address required"), so a customer with no
            # MAC on file (very common -- it's often only learned once they
            # actually connect) must have the key omitted entirely, not sent
            # as ''.
            mac_address = kwargs.pop('mac_address', None)
            if mac_address:
                kwargs['mac-address'] = mac_address

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
    
    def add_pppoe_profile(self, name, rate_limit=None, remote_address=None, local_address=None, on_up=None, on_down=None):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ppp_profile = api.get_resource('/ppp/profile')
            params = {'dns-server': '8.8.8.8,8.8.4.4'}
            if rate_limit: params['rate-limit'] = rate_limit
            if remote_address: params['remote-address'] = remote_address
            if local_address: params['local-address'] = local_address
            if on_up: params['on-up'] = on_up
            if on_down: params['on-down'] = on_down
            existing = ppp_profile.get(name=name)
            existing = [p for p in existing if p.get('id')]
            if existing:
                ppp_profile.set(id=existing[0]['id'], **params)
            else:
                ppp_profile.add(name=name, **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_pppoe_profile(self, name, rate_limit=None, remote_address=None, local_address=None, on_up=None, on_down=None):
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
            if remote_address: params['remote-address'] = remote_address
            if local_address: params['local-address'] = local_address
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
            params = {'shared-users': '1'}
            if rate_limit: params['rate-limit'] = rate_limit
            existing = hotspot_profile.get(name=name)
            existing = [p for p in existing if p.get('id')]
            if existing:
                hotspot_profile.set(id=existing[0]['id'], **params)
            else:
                hotspot_profile.add(name=name, **params)
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

    # Simple Queue Management (Static IP customers -- no PPPoE/Hotspot auth,
    # just a bandwidth cap tied to their fixed address)

    def add_simple_queue(self, name, target, max_limit, comment=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            queue = api.get_resource('/queue/simple')
            existing = queue.get(name=name)
            existing = [q for q in existing if q.get('id')]
            params = {'target': target, 'max-limit': max_limit, 'disabled': 'no', 'comment': comment}
            if existing:
                queue.set(id=existing[0]['id'], **params)
            else:
                queue.add(name=name, **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to add simple queue {name}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def disable_simple_queue(self, name):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            queue = api.get_resource('/queue/simple')
            existing = [q for q in queue.get(name=name) if q.get('id')]
            if existing:
                queue.set(id=existing[0]['id'], disabled='yes')
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to disable simple queue {name}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def remove_simple_queue(self, name):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            queue = api.get_resource('/queue/simple')
            for q in [q for q in queue.get(name=name) if q.get('id')]:
                queue.remove(id=q['id'])
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to remove simple queue {name}: {str(e)}")
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

    # Router Provisioning (bootstrap a fresh router to serve Hotspot/PPPoE)

    def add_ip_pool(self, name, ranges):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            pool = api.get_resource('/ip/pool')
            existing = pool.get(name=name)
            existing = [p for p in existing if p.get('id')]
            if existing:
                pool.set(id=existing[0]['id'], ranges=ranges)
            else:
                pool.add(name=name, ranges=ranges)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_interface_address(self, address, interface, comment=''):
        """address is CIDR form e.g. '10.5.50.1/24'"""
        try:
            connection = self._get_connection()
            api = connection.get_api()
            ip_address = api.get_resource('/ip/address')
            existing = ip_address.get(interface=interface)
            existing = [a for a in existing if a.get('id')]
            same_network = [a for a in existing if a.get('address', '').split('/')[0] == address.split('/')[0]]
            if same_network:
                connection.disconnect()
                return {'success': True}
            ip_address.add(address=address, interface=interface, comment=comment)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_dhcp_server(self, name, interface, pool_name, lease_time='1h'):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            dhcp = api.get_resource('/ip/dhcp-server')
            existing = dhcp.get(interface=interface)
            existing = [d for d in existing if d.get('id')]
            if existing:
                dhcp.set(id=existing[0]['id'], name=name, **{'address-pool': pool_name, 'lease-time': lease_time, 'disabled': 'no'})
            else:
                dhcp.add(name=name, interface=interface, **{'address-pool': pool_name, 'lease-time': lease_time, 'disabled': 'no'})
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_dhcp_network(self, subnet, gateway, dns_servers=''):
        """subnet is CIDR form e.g. '10.5.50.0/24'"""
        try:
            connection = self._get_connection()
            api = connection.get_api()
            dhcp_network = api.get_resource('/ip/dhcp-server/network')
            existing = dhcp_network.get(address=subnet)
            existing = [n for n in existing if n.get('id')]
            params = {'gateway': gateway}
            if dns_servers:
                params['dns-server'] = dns_servers
            if existing:
                dhcp_network.set(id=existing[0]['id'], **params)
            else:
                dhcp_network.add(address=subnet, **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_hotspot_server_profile(self, name, hotspot_address, dns_name='', login_by='http-pap,cookie', html_directory='hotspot'):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hs_profile = api.get_resource('/ip/hotspot/profile')
            existing = hs_profile.get(name=name)
            existing = [p for p in existing if p.get('id')]
            params = {'hotspot-address': hotspot_address, 'login-by': login_by, 'html-directory': html_directory}
            if dns_name:
                params['dns-name'] = dns_name
            if existing:
                hs_profile.set(id=existing[0]['id'], **params)
            else:
                hs_profile.add(name=name, **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_hotspot_server(self, name, interface, pool_name, profile_name):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            hotspot_server = api.get_resource('/ip/hotspot')
            existing = hotspot_server.get(interface=interface)
            existing = [h for h in existing if h.get('id')]
            params = {'address-pool': pool_name, 'profile': profile_name, 'disabled': 'no'}
            if existing:
                hotspot_server.set(id=existing[0]['id'], name=name, **params)
            else:
                hotspot_server.add(name=name, interface=interface, **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_pppoe_server(self, service_name, interface, default_profile='default', one_session_per_host=True):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            pppoe_server = api.get_resource('/interface/pppoe-server/server')
            existing = pppoe_server.get(interface=interface)
            existing = [s for s in existing if s.get('id')]
            params = {
                'service-name': service_name,
                'default-profile': default_profile,
                'one-session-per-host': 'yes' if one_session_per_host else 'no',
                'disabled': 'no',
            }
            if existing:
                pppoe_server.set(id=existing[0]['id'], **params)
            else:
                pppoe_server.add(interface=interface, **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_bridge(self, name):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            bridge = api.get_resource('/interface/bridge')
            existing = bridge.get(name=name)
            existing = [b for b in existing if b.get('id')]
            if not existing:
                bridge.add(name=name)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_bridge_port(self, interface, bridge):
        """
        Enslave `interface` to `bridge`, moving it off whatever bridge it
        currently belongs to (if any). Idempotent.
        """
        try:
            connection = self._get_connection()
            api = connection.get_api()
            bridge_port = api.get_resource('/interface/bridge/port')
            existing = bridge_port.get(interface=interface)
            existing = [p for p in existing if p.get('id')]
            if existing:
                if existing[0].get('bridge') != bridge:
                    bridge_port.set(id=existing[0]['id'], bridge=bridge)
            else:
                bridge_port.add(interface=interface, bridge=bridge)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def upload_file(self, path, contents):
        """
        Write a text file to the router's flash storage (e.g. a Hotspot
        login.html). RouterOS's API `set contents=` *appends* rather than
        overwrites, so an existing file is removed and re-added fresh each
        time to keep this idempotent.
        """
        try:
            connection = self._get_connection()
            api = connection.get_api()
            file_resource = api.get_resource('/file')
            existing = file_resource.get(name=path)
            existing = [f for f in existing if f.get('id')]
            for f in existing:
                file_resource.remove(id=f['id'])
            file_resource.add(name=path, contents=contents)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def list_interfaces(self):
        """Read-only: real interface names on this router, for picking the
        correct MIKROTIK_PROVISION_INTERFACE value before provisioning."""
        try:
            connection = self._get_connection()
            api = connection.get_api()
            interfaces = api.get_resource('/interface').get()
            interfaces = [
                {'name': i.get('name'), 'type': i.get('type'), 'running': i.get('running') == 'true', 'disabled': i.get('disabled') == 'true'}
                for i in interfaces if i.get('name')
            ]
            connection.disconnect()
            return {'success': True, 'interfaces': interfaces}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_system_health(self):
        """
        Read-only: CPU load, memory/disk usage, and uptime from
        /system/resource, plus cumulative rx/tx byte counters on
        settings.MIKROTIK_WAN_INTERFACE -- RouterOS only exposes running
        totals here, not a rate, so the caller derives live throughput by
        diffing two polls a few seconds apart (same approach as
        get_active_sessions' PPPoE byte counters).
        """
        try:
            from django.conf import settings

            connection = self._get_connection()
            api = connection.get_api()

            resource = api.get_resource('/system/resource').get()
            res = resource[0] if resource else {}

            total_memory = int(res.get('total-memory', 0) or 0)
            free_memory = int(res.get('free-memory', 0) or 0)
            total_hdd = int(res.get('total-hdd-space', 0) or 0)
            free_hdd = int(res.get('free-hdd-space', 0) or 0)

            wan_rx, wan_tx = 0, 0
            wan_iface = settings.MIKROTIK_WAN_INTERFACE
            wan_interfaces = api.get_resource('/interface').get(name=wan_iface)
            if wan_interfaces:
                wan_rx = int(wan_interfaces[0].get('rx-byte', 0) or 0)
                wan_tx = int(wan_interfaces[0].get('tx-byte', 0) or 0)

            connection.disconnect()
            return {
                'success': True,
                'cpu_load': int(res.get('cpu-load', 0) or 0),
                'memory_used_pct': round((1 - free_memory / total_memory) * 100, 1) if total_memory else None,
                'disk_used_pct': round((1 - free_hdd / total_hdd) * 100, 1) if total_hdd else None,
                'uptime': res.get('uptime'),
                'board_name': res.get('board-name'),
                'version': res.get('version'),
                'wan_interface': wan_iface,
                'wan_rx_bytes': wan_rx,
                'wan_tx_bytes': wan_tx,
            }
        except Exception as e:
            logger.error(f"Failed to get system health: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_active_sessions(self):
        """
        Read-only: currently connected Hotspot + PPPoE users with live byte
        counters, for usage tracking and dashboard online-user counts.

        Hotspot sessions report bytes-in/out directly on /ip/hotspot/active.
        PPPoE sessions don't -- RouterOS exposes those on the dynamic
        "<pppoe-USERNAME>" interface it creates while the session is up, so
        we cross-reference /interface for rx-byte/tx-byte per username.
        """
        try:
            connection = self._get_connection()
            api = connection.get_api()

            hotspot_active = [
                s for s in api.get_resource('/ip/hotspot/active').get() if s.get('id')
            ]
            sessions = [
                {
                    'service_type': 'hotspot',
                    'session_id': s.get('id'),
                    'username': s.get('user'),
                    'address': s.get('address'),
                    'mac_address': s.get('mac-address'),
                    'uptime': s.get('uptime'),
                    'upload_bytes': int(s.get('bytes-in', 0) or 0),
                    'download_bytes': int(s.get('bytes-out', 0) or 0),
                }
                for s in hotspot_active
            ]

            ppp_active = [
                s for s in api.get_resource('/ppp/active').get() if s.get('id')
            ]
            if ppp_active:
                interfaces = api.get_resource('/interface').get()
                iface_bytes = {}
                for i in interfaces:
                    name = i.get('name', '')
                    if name.startswith('<pppoe-') and name.endswith('>'):
                        iface_bytes[name[len('<pppoe-'):-1]] = (
                            int(i.get('rx-byte', 0) or 0), int(i.get('tx-byte', 0) or 0)
                        )
                for s in ppp_active:
                    username = s.get('name')
                    rx, tx = iface_bytes.get(username, (0, 0))
                    sessions.append({
                        'service_type': 'pppoe',
                        'session_id': s.get('id'),
                        'username': username,
                        'address': s.get('address'),
                        'mac_address': s.get('caller-id'),
                        'uptime': s.get('uptime'),
                        'upload_bytes': rx,
                        'download_bytes': tx,
                    })

            connection.disconnect()
            return {'success': True, 'sessions': sessions}
        except Exception as e:
            logger.error(f"Failed to get active sessions: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_provisioning_snapshot(self, interface, pool_names, profile_names, bridge_ports=None):
        """
        Read the current state of every resource `provision_router` is about
        to touch, so there's a record of what existed beforehand. Read-only.

        bridge_ports, if given, records which bridge (if any) each of those
        physical ports currently belongs to -- provisioning moves them onto
        the new hotspot/PPPoE bridge, so this is what you'd restore to undo
        that move manually.
        """
        snapshot = {}
        try:
            connection = self._get_connection()
            api = connection.get_api()

            def clean(resource, **filters):
                items = resource.get(**filters) if filters else resource.get()
                return [i for i in items if i.get('id')]

            snapshot['bridges'] = clean(api.get_resource('/interface/bridge'))
            if bridge_ports:
                all_ports = clean(api.get_resource('/interface/bridge/port'))
                snapshot['bridge_ports'] = [p for p in all_ports if p.get('interface') in bridge_ports]
            snapshot['ip_addresses'] = clean(api.get_resource('/ip/address'), interface=interface)
            snapshot['dhcp_servers'] = clean(api.get_resource('/ip/dhcp-server'), interface=interface)
            snapshot['dhcp_networks'] = clean(api.get_resource('/ip/dhcp-server/network'))
            snapshot['hotspot_servers'] = clean(api.get_resource('/ip/hotspot'), interface=interface)
            snapshot['pppoe_servers'] = clean(api.get_resource('/interface/pppoe-server/server'), interface=interface)
            snapshot['ip_pools'] = [
                p for p in clean(api.get_resource('/ip/pool')) if p.get('name') in pool_names
            ]
            snapshot['hotspot_profiles'] = [
                p for p in clean(api.get_resource('/ip/hotspot/profile')) if p.get('name') in profile_names
            ]
            snapshot['hotspot_user_profiles'] = [
                p for p in clean(api.get_resource('/ip/hotspot/user/profile')) if p.get('name') in profile_names
            ]
            snapshot['ppp_profiles'] = [
                p for p in clean(api.get_resource('/ppp/profile')) if p.get('name') in profile_names
            ]
            snapshot['nat_rules'] = clean(api.get_resource('/ip/firewall/nat'), chain='srcnat')
            snapshot['hotspot_login_html'] = clean(api.get_resource('/file'), name='hotspot/login.html')

            connection.disconnect()
            return {'success': True, 'snapshot': snapshot}
        except Exception as e:
            logger.error(f"Failed to snapshot router before provisioning: {str(e)}")
            return {'success': False, 'error': str(e)}

    def add_nat_masquerade(self, src_address, comment=''):
        try:
            connection = self._get_connection()
            api = connection.get_api()
            nat = api.get_resource('/ip/firewall/nat')
            params = {'chain': 'srcnat', 'src-address': src_address, 'action': 'masquerade'}
            existing = nat.get(**params)
            existing = [n for n in existing if n.get('id')]
            if not existing:
                nat.add(comment=comment, **params)
            connection.disconnect()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Default instance
mikrotik_service = MikroTikService()
