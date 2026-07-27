"""
Network Automation Service
Handles automatic network access control based on payment and subscription status
"""

import ipaddress
import logging
from urllib.parse import urlparse
from django.conf import settings
from django.utils import timezone
from apps.network.models import PPPoESecret, HotspotUser, Router
from apps.network.services.mikrotik_service import MikroTikService

logger = logging.getLogger('apps.network')


def validate_portal_url(url):
    """
    Returns an error string if `url` isn't a usable absolute URL, else None.
    A scheme-less value (e.g. a bare IP) is silently valid JavaScript but
    resolves as a *relative* path against whatever page is loading it --
    the router's own gateway -- producing a broken URL instead of an error,
    so this must be checked explicitly rather than left to fail naturally.
    """
    parsed = urlparse(url or '')
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return (
            f"Captive portal URL {url!r} must be a full URL including scheme, "
            f"e.g. https://192.168.88.254/portal -- a bare IP or host resolves "
            f"as a relative link off the router's own gateway and won't load."
        )
    return None


def build_hotspot_login_html(portal_url):
    """
    RouterOS hotspot login.html: the $(...) tokens are literal text in the
    file that RouterOS substitutes itself when serving the page to a client
    (not Python string formatting) -- only `portal_url` is filled in here.
    Redirects unauthenticated clients to the external captive portal
    (CaptivePortal.tsx), passing MAC + the router's own login/orig links so
    it can log the client back in after payment/voucher redemption.
    """
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Connecting...</title></head>
<body>
<script>
  window.location.replace(
    "{portal_url}" +
    "?mac=$(mac)" +
    "&link-login=" + encodeURIComponent("$(link-login-only)") +
    "&link-orig=" + encodeURIComponent("$(link-orig)")
  );
</script>
<noscript>Please enable JavaScript, or visit {portal_url} to continue.</noscript>
</body>
</html>
"""


class NetworkAutomation:
    """
    Automate network access based on billing status
    """
    
    
    def suspend_customer(self, customer):
        """
        Suspend network access for a customer
        """
        router = Router.objects.filter(is_active=True).first()
        if not router:
            return {'success': False, 'error': 'No active router configured'}
            
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username, 
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        
        results = {'success': True, 'errors': []}
        
        try:
            # Suspend PPPoE
            if customer.service_type in ['pppoe', 'both']:
                # Update Local
                PPPoESecret.objects.filter(customer=customer).update(status='disabled')
                
                # Update Router
                username = customer.pppoe_username or customer.username
                res1 = mikrotik.disable_pppoe_secret(username)
                res2 = mikrotik.disconnect_pppoe_session(username)
                
                if not res1['success']: results['errors'].append(f"PPPoE Disable: {res1.get('error')}")
                if not res2['success']: results['errors'].append(f"PPPoE Disconnect: {res2.get('error')}")

            # Suspend Hotspot
            if customer.service_type in ['hotspot', 'both']:
                # Update Local
                HotspotUser.objects.filter(customer=customer).update(status='disabled')
                
                # Update Router
                username = customer.hotspot_username or customer.username
                res1 = mikrotik.disable_hotspot_user(username)
                res2 = mikrotik.disconnect_hotspot_session(username)
                
                if not res1['success']: results['errors'].append(f"Hotspot Disable: {res1.get('error')}")
                if not res2['success']: results['errors'].append(f"Hotspot Disconnect: {res2.get('error')}")
                
                # Remove Hotspot Cookies to force re-login
                res3 = mikrotik.remove_hotspot_cookie(username)
                if not res3['success']: logger.warning(f"Failed to remove cookie for {username}: {res3.get('error')}")

            if results['errors']:
                logger.error(f"Suspend customer {customer.username} errors: {results['errors']}")
                return {'success': False, 'error': ", ".join(results['errors'])}
            logger.info(f"Suspend customer {customer.username} completed successfully")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Failed to suspend customer {customer.username}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def activate_customer(self, customer, plan):
        try:
            # Determine target routers: either from plan or fallback to all active
            target_routers = plan.routers.filter(is_active=True)
            if not target_routers.exists():
                # Fallback to default behavior: use the first active router (or all?)
                # For now, let's just pick the first active one to be safe, or all active?
                # Using all active routers is safer for consistency.
                target_routers = Router.objects.filter(is_active=True)
                
            if not target_routers.exists():
                return {'success': False, 'error': 'No active router configured'}
                
            results = {'errors': []}
            
            for router in target_routers:
                mikrotik = MikroTikService(
                    host=router.ip_address, username=router.username, 
                    password=router.password, port=router.port, use_ssl=router.use_ssl
                )
                
                try:
                    # Determine overlapping services
                    # Only activate if BOTH Customer and Plan support the service
                    enable_pppoe = (customer.service_type in ['pppoe', 'both']) and (plan.service_type in ['pppoe', 'both'])
                    enable_hotspot = (customer.service_type in ['hotspot', 'both']) and (plan.service_type in ['hotspot', 'both'])
                    
                    if enable_pppoe:
                        self._activate_pppoe(customer, plan, router, mikrotik)
                    
                    if enable_hotspot:
                        self._activate_hotspot(customer, plan, router, mikrotik)
                        
                except Exception as e:
                    results['errors'].append(f"{router.name}: {str(e)}")
                    
            if results['errors']:
                return {'success': False, 'error': ", ".join(results['errors'])}
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Failed to activate customer {customer.username}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _activate_pppoe(self, customer, plan, router, mikrotik):
        pppoe_secret, created = PPPoESecret.objects.get_or_create(
            customer=customer,
            defaults={
                'router': router,
                'username': customer.pppoe_username or customer.username,
                'password': customer.pppoe_password or customer.username,
                'profile': plan.mikrotik_profile,
                'status': 'enabled'
            }
        )
        
        # Ensure we sync to router regardless of whether created locally or not
        # If created locally, we definitely add.
        # If existing locally, we update. BUT if missing on router, update fails, so we must add.
        
        # Check if update is actually needed (optimization & stability)
        needs_update = False
        if not created:
             if pppoe_secret.profile != plan.mikrotik_profile:
                 needs_update = True
             if pppoe_secret.password != (customer.pppoe_password or customer.username):
                 needs_update = True
             # If status was disabled locally, we need to re-enable
             if pppoe_secret.status != 'enabled':
                 needs_update = True

        if not created and not needs_update:
             # Nothing changed, skip router interaction to prevent disconnects
             return

        success = False
        if not created:
            # Try updating first
            res = mikrotik.update_pppoe_secret(
                username=pppoe_secret.username, 
                profile=plan.mikrotik_profile, 
                password=customer.pppoe_password or customer.username,
                disabled='no'
            )
            if res['success']:
                success = True
            elif 'not found' in res.get('error', '').lower():
                # It's missing on router, so let's fall through to add it
                created = True 
            else:
                logger.error(f"Failed to update PPPoE secret: {res.get('error')}")

        if created:
            mikrotik.add_pppoe_secret(
                username=pppoe_secret.username, 
                password=customer.pppoe_password or customer.username, 
                profile=plan.mikrotik_profile
            )

        # Ensure correct local state
        if not created:
            pppoe_secret.profile = plan.mikrotik_profile
            pppoe_secret.password = customer.pppoe_password or customer.username
            pppoe_secret.status = 'enabled'
        
        pppoe_secret.router = router
        pppoe_secret.synced_to_router = True
        pppoe_secret.save()
        
        # Reset session only if we touched the router
        mikrotik.disconnect_pppoe_session(pppoe_secret.username)
    
    def _activate_hotspot(self, customer, plan, router, mikrotik):
        hotspot_user, created = HotspotUser.objects.get_or_create(
            customer=customer,
            defaults={
                'router': router,
                'username': customer.hotspot_username or customer.username,
                'password': customer.hotspot_password or customer.username,
                'profile': plan.mikrotik_profile,
                'mac_address': customer.hotspot_mac_address,
                'status': 'enabled'
            }
        )

        # Check if update is actually needed
        needs_update = False
        if not created:
            if hotspot_user.profile != plan.mikrotik_profile:
                needs_update = True
            if hotspot_user.password != (customer.hotspot_password or customer.username):
                needs_update = True
            current_mac = hotspot_user.mac_address or ''
            target_mac = customer.hotspot_mac_address or ''
            if current_mac != target_mac:
                needs_update = True
            if hotspot_user.status != 'enabled':
                needs_update = True
        
        if not created and not needs_update:
             return

        success = False
        if not created:
             res = mikrotik.update_hotspot_user(
                username=hotspot_user.username, 
                profile=plan.mikrotik_profile, 
                password=customer.hotspot_password or customer.username,
                disabled='no',
                mac_address=customer.hotspot_mac_address or ''
            )
             if res['success']:
                 success = True
             elif 'not found' in res.get('error', '').lower():
                 created = True
             else:
                 logger.error(f"Failed to update Hotspot user: {res.get('error')}")

        if created:
            mikrotik.add_hotspot_user(
                username=hotspot_user.username, 
                password=hotspot_user.password, 
                profile=plan.mikrotik_profile,
                mac_address=hotspot_user.mac_address or ''
            )

        if not created:
            hotspot_user.profile = plan.mikrotik_profile
            hotspot_user.password = customer.hotspot_password or customer.username
            hotspot_user.status = 'enabled'
            if customer.hotspot_mac_address:
                hotspot_user.mac_address = customer.hotspot_mac_address
                
        hotspot_user.router = router
        hotspot_user.synced_to_router = True
        hotspot_user.save()

        # Only disconnect if we made changes
        mikrotik.disconnect_hotspot_session(hotspot_user.username)
        if customer.hotspot_mac_address:
            mikrotik.disconnect_hotspot_by_mac(customer.hotspot_mac_address)

    def sync_all_profiles(self, router=None):
        from apps.billing.models import BillingPlan
        results = {'success': [], 'failed': []}
        plans = BillingPlan.objects.filter(is_active=True)
        router = router or Router.objects.filter(is_active=True).first()
        if not router: return {'error': 'No active router configured'}
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username, 
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        for plan in plans:
            rate_limit = f"{plan.upload_speed}M/{plan.download_speed}M"
            if plan.service_type in ['pppoe', 'both']:
                res = mikrotik.update_pppoe_profile(plan.mikrotik_profile, rate_limit)
                if not res['success'] and 'not found' in res.get('error', ''):
                    res = mikrotik.add_pppoe_profile(plan.mikrotik_profile, rate_limit)
                if res['success']: results['success'].append(f"PPPoE: {plan.name}")
                else: results['failed'].append(f"PPPoE: {plan.name} - {res.get('error')}")
            if plan.service_type in ['hotspot', 'both']:
                res = mikrotik.update_hotspot_profile(plan.mikrotik_profile, rate_limit)
                if not res['success'] and 'not found' in res.get('error', ''):
                    res = mikrotik.add_hotspot_profile(plan.mikrotik_profile, rate_limit)
                if res['success']: results['success'].append(f"Hotspot: {plan.name}")
                else: results['failed'].append(f"Hotspot: {plan.name} - {res.get('error')}")
        return results

    def sync_all_users(self, router=None):
        from apps.billing.models import Subscription
        results = {'success': [], 'failed': []}
        active_subs = Subscription.objects.filter(status='active', expiry_date__gt=timezone.now())
        router = router or Router.objects.filter(is_active=True).first()
        if not router: return {'error': 'No active router configured'}
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username, 
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        for sub in active_subs:
            customer = sub.customer
            plan = sub.plan
            try:
                if customer.service_type in ['pppoe', 'both']:
                    self._activate_pppoe(customer, plan, router, mikrotik)
                    results['success'].append(f"PPPoE: {customer.username}")
                if customer.service_type in ['hotspot', 'both']:
                    self._activate_hotspot(customer, plan, router, mikrotik)
                    results['success'].append(f"Hotspot: {customer.username}")
            except Exception as e:
                results['failed'].append(f"{customer.username}: {str(e)}")
        return results

    def snapshot_router(self, router, username=None, password=None):
        """
        Read-only capture of whatever currently occupies the resources
        `provision_router` is about to write to, so there's a record to
        manually roll back to if a provisioning run needs undoing.

        username/password, if given, override the router's stored
        credentials for this call only (they are not persisted here).
        """
        interface = settings.MIKROTIK_PROVISION_INTERFACE
        mikrotik = MikroTikService(
            host=router.ip_address, username=username or router.username,
            password=password or router.password, port=router.port, use_ssl=router.use_ssl
        )
        res = mikrotik.get_provisioning_snapshot(
            interface=interface,
            pool_names=['hotspot_pool', 'pppoe_pool'],
            profile_names=['default', 'hotspot_profile'],
            bridge_ports=settings.MIKROTIK_PROVISION_BRIDGE_PORTS,
        )
        if res.get('success'):
            router.pre_provision_snapshot = res['snapshot']
            router.pre_provision_snapshot_at = timezone.now()
            router.save(update_fields=['pre_provision_snapshot', 'pre_provision_snapshot_at'])
        return res

    def provision_router(self, router, username=None, password=None, portal_url=None):
        """
        Bootstrap a freshly-added router so it's ready to serve Hotspot and
        PPPoE connections: creates settings.MIKROTIK_PROVISION_INTERFACE as a
        bridge (if missing), enslaves settings.MIKROTIK_PROVISION_BRIDGE_PORTS
        to it, then sets up IP pools, DHCP, NAT, Hotspot server + profile,
        PPPoE server, walled garden, the Hotspot login.html redirect to the
        external captive portal, and existing billing-plan profiles -- all
        bound to that one bridge. Ports left out of
        MIKROTIK_PROVISION_BRIDGE_PORTS (WAN, a reserved management port,
        etc.) are never touched.

        username/password, if given, override the router's stored
        credentials for this run, and are persisted to the router once a
        connection with them succeeds (so stored credentials can't silently
        go stale without being noticed). portal_url, if given, likewise
        overrides and persists router.portal_url.
        """
        results = {'success': [], 'failed': []}
        interface = settings.MIKROTIK_PROVISION_INTERFACE

        effective_portal_url = portal_url or router.portal_url
        portal_url_error = validate_portal_url(effective_portal_url)
        if portal_url_error:
            return {'error': portal_url_error}

        try:
            hotspot_net = ipaddress.ip_network(router.hotspot_subnet, strict=False)
            pppoe_net = ipaddress.ip_network(router.pppoe_subnet, strict=False)
        except ValueError as e:
            return {'error': f'Invalid subnet configured on router: {e}'}

        hotspot_gateway = str(hotspot_net[1])
        hotspot_pool_range = f"{hotspot_net[2]}-{hotspot_net[-2]}"
        pppoe_gateway = str(pppoe_net[1])
        pppoe_pool_range = f"{pppoe_net[2]}-{pppoe_net[-2]}"

        # Safety net: record what's on the router before we change anything.
        # This also verifies the credentials work before any write happens.
        snapshot_res = self.snapshot_router(router, username=username, password=password)
        if not snapshot_res.get('success'):
            return {'error': f"Could not connect to router before provisioning: {snapshot_res.get('error')}"}

        if username and password:
            router.username = username
            router.password = password
            router.save(update_fields=['username', 'password'])

        if portal_url:
            router.portal_url = portal_url
            router.save(update_fields=['portal_url'])

        mikrotik = MikroTikService(
            host=router.ip_address, username=username or router.username,
            password=password or router.password, port=router.port, use_ssl=router.use_ssl
        )

        def step(label, fn, *args, **kwargs):
            res = fn(*args, **kwargs)
            if res.get('success'):
                results['success'].append(label)
            else:
                results['failed'].append(f"{label}: {res.get('error')}")
            return res

        # --- Bridge: create it, and enslave the configured LAN ports to it.
        # Ports not listed (WAN, and anything reserved e.g. for management
        # access) are left exactly as they are. ---
        step(f'Create {interface} bridge', mikrotik.add_bridge, interface)
        for port in settings.MIKROTIK_PROVISION_BRIDGE_PORTS:
            step(f'Add {port} to {interface}', mikrotik.set_bridge_port, port, interface)

        # --- Hotspot: interface IP, pool, DHCP, server profile, server ---
        step('Hotspot interface address', mikrotik.add_interface_address,
             f"{hotspot_gateway}/{hotspot_net.prefixlen}", interface, comment='ISP Billing - Hotspot gateway')
        step('Hotspot IP pool', mikrotik.add_ip_pool, 'hotspot_pool', hotspot_pool_range)
        step('Hotspot DHCP server', mikrotik.add_dhcp_server, 'hotspot_dhcp', interface, 'hotspot_pool')
        step('Hotspot DHCP network', mikrotik.add_dhcp_network,
             str(hotspot_net), hotspot_gateway, dns_servers=router.dns_servers)
        step('Hotspot default user profile', mikrotik.add_hotspot_profile, 'default')
        step('Hotspot server profile', mikrotik.add_hotspot_server_profile,
             'hotspot_profile', hotspot_gateway)
        step('Hotspot server', mikrotik.add_hotspot_server,
             'hotspot1', interface, 'hotspot_pool', 'hotspot_profile')
        step('Hotspot login page', mikrotik.upload_file,
             'hotspot/login.html', build_hotspot_login_html(router.portal_url))

        # --- PPPoE: pool, default profile, server ---
        step('PPPoE IP pool', mikrotik.add_ip_pool, 'pppoe_pool', pppoe_pool_range)
        step('PPPoE default profile', mikrotik.add_pppoe_profile, 'default')
        step('PPPoE server', mikrotik.add_pppoe_server, 'pppoe-service', interface, default_profile='default')

        # --- NAT so both subnets can reach the internet ---
        step('NAT masquerade (Hotspot)', mikrotik.add_nat_masquerade,
             str(hotspot_net), comment='ISP Billing - Hotspot NAT')
        step('NAT masquerade (PPPoE)', mikrotik.add_nat_masquerade,
             str(pppoe_net), comment='ISP Billing - PPPoE NAT')

        # --- Walled garden: let unauthenticated Hotspot clients reach the portal.
        # The login page redirects to router.portal_url, so that host must be
        # walled-gardened too, on top of whatever's configured globally.
        #
        # dst-host walled-garden entries only match DNS lookups -- a bare IP
        # (no DNS involved) needs a dst-address entry instead, or it's simply
        # never matched and the portal stays unreachable to new clients.
        walled_garden_hosts = set(settings.MIKROTIK_WALLED_GARDEN_HOSTS)
        portal_host = urlparse(router.portal_url).hostname
        if portal_host:
            walled_garden_hosts.add(portal_host)
        for host in walled_garden_hosts:
            try:
                ipaddress.ip_address(host)
                step(f'Walled garden ({host})', mikrotik.add_walled_garden_ip, host, comment='ISP Billing - Portal')
            except ValueError:
                step(f'Walled garden ({host})', mikrotik.add_walled_garden_host, host, comment='ISP Billing - Portal')

        # --- Push existing billing-plan profiles so plans are sellable immediately ---
        plan_sync = self.sync_all_profiles(router=router)
        if isinstance(plan_sync, dict) and plan_sync.get('error'):
            results['failed'].append(f"Plan profiles: {plan_sync['error']}")
        else:
            results['success'].extend(plan_sync.get('success', []))
            results['failed'].extend(plan_sync.get('failed', []))

        router.provisioned = not results['failed']
        router.provisioned_at = timezone.now()
        router.last_sync = timezone.now()
        router.save(update_fields=['provisioned', 'provisioned_at', 'last_sync'])

        return results

network_automation = NetworkAutomation()
