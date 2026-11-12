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


def _pool_networks(ranges):
    """RouterOS pool ranges ('10.5.60.2-10.5.60.254,10.5.61.0/24,...') ->
    the smallest network covering each range."""
    networks = []
    for part in (ranges or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            if '/' in part:
                networks.append(ipaddress.ip_network(part, strict=False))
                continue
            start, _, end = part.partition('-')
            first = ipaddress.ip_address(start)
            last = ipaddress.ip_address(end) if end else first
            for prefix in range(32, -1, -1):
                net = ipaddress.ip_network(f'{first}/{prefix}', strict=False)
                if last in net:
                    networks.append(net)
                    break
        except ValueError:
            continue
    return networks


def plan_management_vlan(layout, wan_interface, bridge, comment_prefix, preferred_vlan_id=90, extra_allowed=()):
    """
    Decide the radio management network from what the router actually has
    configured (layout from MikroTikService.read_network_layout):

    - VLAN ID: an existing management VLAN's (re-run), else
      preferred_vlan_id, else the next ID no VLAN on the router uses.
    - Subnet: the existing management VLAN's, else the first /24 in the
      same /16 as the bridge's own (hotspot) address -- from .90 up, so
      it reads as "next to" the customer subnets -- that overlaps no
      address, pool or the WAN subnet already on the router.
    - Allowed in (through the WAN port): the WAN interface's current
      network, plus extra_allowed (e.g. a VPN like UniFi Teleport).
    - Blocked: every customer-facing subnet -- the bridge's addresses and
      every IP pool (hotspot, PPPoE, ...).

    Raises ValueError when there's nothing sensible to plan against.
    """
    if bridge not in layout['interfaces']:
        raise ValueError(f"Interface {bridge!r} doesn't exist on this router -- provision it first.")

    static_addresses = [a for a in layout['addresses'] if not a['dynamic']]
    wan_addresses = [a for a in static_addresses if a['interface'] == wan_interface] or \
        [a for a in layout['addresses'] if a['interface'] == wan_interface]
    if not wan_addresses:
        raise ValueError(f"{wan_interface} has no IP address right now (DHCP not bound yet?).")
    wan_if = ipaddress.ip_interface(wan_addresses[0]['address'])
    lan_subnet = wan_if.network

    try:
        extra_nets = [ipaddress.ip_network(s, strict=False) for s in extra_allowed]
    except ValueError as e:
        raise ValueError(f'Invalid MIKROTIK_MGMT_VLAN_ALLOWED_SUBNETS entry: {e}')

    existing = next((v for v in layout['vlans'] if (v['comment'] or '').startswith(comment_prefix)), None)
    mgmt_interface = existing['name'] if existing else None

    used = [lan_subnet] + extra_nets
    customer = []
    existing_subnet = None
    for a in static_addresses:
        net = ipaddress.ip_interface(a['address']).network
        if a['interface'] == mgmt_interface:
            existing_subnet = net
            continue
        used.append(net)
        if a['interface'] == bridge:
            customer.append(net)
    for pool in layout['pools']:
        if pool['name'] == 'isp-mgmt-pool':
            continue
        nets = _pool_networks(pool['ranges'])
        used.extend(nets)
        customer.extend(nets)

    if existing:
        vlan_id = int(existing['vlan_id'])
        vlan_name = existing['name']
    else:
        taken_ids = {int(v['vlan_id']) for v in layout['vlans'] if str(v.get('vlan_id') or '').isdigit()}
        vlan_id = next(i for i in list(range(preferred_vlan_id, 4095)) + list(range(2, preferred_vlan_id))
                       if i not in taken_ids)
        vlan_name = f'mgmt-vlan{vlan_id}'

    subnet = existing_subnet
    if subnet is None or any(subnet.overlaps(u) for u in used):
        bridge_nets = [ipaddress.ip_interface(a['address']).network for a in static_addresses if a['interface'] == bridge]
        base = bridge_nets[0] if bridge_nets and bridge_nets[0].prefixlen >= 16 else ipaddress.ip_network('10.5.0.0/16')
        first_two = '.'.join(str(base.network_address).split('.')[:2])
        subnet = None
        for third in list(range(90, 256)) + list(range(0, 90)):
            candidate = ipaddress.ip_network(f'{first_two}.{third}.0/24')
            if not any(candidate.overlaps(u) for u in used):
                subnet = candidate
                break
        if subnet is None:
            raise ValueError(f'No free /24 left in {first_two}.0.0/16 for the management network.')

    blocked = sorted({str(n) for n in customer if not n.overlaps(lan_subnet) and not n.overlaps(subnet)})
    allowed = [str(lan_subnet)]
    for net in extra_nets:
        if str(net) not in allowed and not net.overlaps(subnet):
            allowed.append(str(net))
    return {
        'vlan_id': vlan_id,
        'vlan_name': vlan_name,
        'bridge': bridge,
        'wan_interface': wan_interface,
        'wan_ip': str(wan_if.ip),
        'subnet': str(subnet),
        'gateway': f'{subnet[1]}/{subnet.prefixlen}',
        'pool_range': f'{subnet[100]}-{subnet[200]}',
        'lan_subnet': str(lan_subnet),
        'allowed': allowed,
        'blocked': blocked,
        'reused': existing is not None,
    }


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
        Suspend network access for a customer on every active router
        (hotspot access is provisioned on all of them for roaming).
        """
        routers = list(Router.objects.filter(is_active=True))
        if not routers:
            return {'success': False, 'error': 'No active router configured'}

        errors = []
        for router in routers:
            res = self._suspend_on_router(customer, router)
            if not res.get('success'):
                errors.append(f"{router.name}: {res.get('error')}")
        if errors:
            return {'success': False, 'error': ", ".join(errors)}
        return {'success': True}

    def _suspend_on_router(self, customer, router):
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
                if customer.hotspot_mac_address:
                    mikrotik.set_hotspot_mac_user(customer.hotspot_mac_address, 'default', disabled=True)
                    mikrotik.disconnect_hotspot_by_mac(customer.hotspot_mac_address)
                
                if not res1['success']: results['errors'].append(f"Hotspot Disable: {res1.get('error')}")
                if not res2['success']: results['errors'].append(f"Hotspot Disconnect: {res2.get('error')}")
                
                # Remove Hotspot Cookies to force re-login
                res3 = mikrotik.remove_hotspot_cookie(username)
                if not res3['success']: logger.warning(f"Failed to remove cookie for {username}: {res3.get('error')}")

            # Suspend Static IP (just disable their bandwidth queue -- there's
            # no auth session to disconnect for a static/manually-configured IP)
            if customer.service_type == 'static':
                res1 = mikrotik.disable_simple_queue(customer.username)
                if not res1['success']: results['errors'].append(f"Static Queue Disable: {res1.get('error')}")
                res2 = mikrotik.remove_ip_binding(f"static-{customer.username}")
                if not res2['success']: results['errors'].append(f"Static IP Binding Remove: {res2.get('error')}")

            if results['errors']:
                logger.error(f"Suspend customer {customer.username} errors: {results['errors']}")
                return {'success': False, 'error': ", ".join(results['errors'])}
            logger.info(f"Suspend customer {customer.username} completed successfully")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Failed to suspend customer {customer.username}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def activate_customer(self, customer, plan):
        """
        Raises on failure (no active router, or a real push failure on any
        target router) rather than returning a swallow-able error dict --
        Subscription creation is the one moment that's actually supposed to
        mean "this customer is now connected", so a caller creating one
        needs to find out if that didn't actually happen. Callers that want
        best-effort behavior (e.g. a payment already succeeded, activation
        can be retried later) should wrap the call in their own try/except,
        same as apps/payments/services/payment_processor.py already does.
        """
        # Determine target routers: either from plan or fallback to all active
        plan_routers = plan.routers.filter(is_active=True)
        all_routers = Router.objects.filter(is_active=True)
        target_routers = plan_routers if plan_routers.exists() else all_routers

        if not all_routers.exists():
            raise Exception('No active router configured')

        errors = []

        for router in all_routers:
            customer_hotspot = (customer.service_type in ['hotspot', 'both']) and (plan.service_type in ['hotspot', 'both'])
            # Hotspot access is honored on every router (roaming); other
            # services stay limited to the plan's routers.
            if not customer_hotspot and not target_routers.filter(pk=router.pk).exists():
                continue
            if customer_hotspot and not target_routers.filter(pk=router.pk).exists():
                enable_only_hotspot = True
            else:
                enable_only_hotspot = False
            mikrotik = MikroTikService(
                host=router.ip_address, username=router.username,
                password=router.password, port=router.port, use_ssl=router.use_ssl
            )

            try:
                # Determine overlapping services
                # Only activate if BOTH Customer and Plan support the service
                enable_pppoe = (customer.service_type in ['pppoe', 'both']) and (plan.service_type in ['pppoe', 'both'])
                enable_hotspot = (customer.service_type in ['hotspot', 'both']) and (plan.service_type in ['hotspot', 'both'])
                enable_static = (customer.service_type == 'static') and (plan.service_type == 'static')

                if enable_pppoe and not enable_only_hotspot:
                    self._activate_pppoe(customer, plan, router, mikrotik)

                if enable_hotspot:
                    self._activate_hotspot(customer, plan, router, mikrotik)

                if enable_static and not enable_only_hotspot:
                    self._activate_static(customer, plan, router, mikrotik)

            except Exception as e:
                errors.append(f"{router.name}: {str(e)}")

        if errors:
            error_msg = ", ".join(errors)
            logger.error(f"Failed to activate customer {customer.username}: {error_msg}")
            raise Exception(error_msg)

    def _customer_has_fup(self, customer, plan):
        from apps.billing.models import Subscription
        subscription = Subscription.objects.filter(
            customer=customer,
            plan=plan,
            status='active',
            expiry_date__gt=timezone.now(),
        ).order_by('-created_at').first()
        return bool(subscription and subscription.fup_applied)

    def apply_customer_fup(self, customer, plan):
        """Apply reduced speeds to this customer's active network account."""
        plan_routers = plan.routers.filter(is_active=True)
        target_routers = plan_routers if plan_routers.exists() else Router.objects.filter(is_active=True)
        all_routers = Router.objects.filter(is_active=True)
        if not all_routers.exists():
            return {'success': False, 'error': 'No active router configured'}
        errors = []

        for router in all_routers:
            customer_hotspot = customer.service_type in ['hotspot', 'both'] and plan.service_type in ['hotspot', 'both']
            if not customer_hotspot and not target_routers.filter(pk=router.pk).exists():
                continue
            enable_only_hotspot = customer_hotspot and not target_routers.filter(pk=router.pk).exists()
            mikrotik = MikroTikService(
                host=router.ip_address,
                username=router.username,
                password=router.password,
                port=router.port,
                use_ssl=router.use_ssl,
            )
            try:
                if customer.service_type in ['pppoe', 'both'] and plan.service_type in ['pppoe', 'both'] and not enable_only_hotspot:
                    self._activate_pppoe(customer, plan, router, mikrotik, profile_name=plan.get_fup_mikrotik_profile())
                if customer_hotspot:
                    self._activate_hotspot(customer, plan, router, mikrotik, profile_name=plan.get_fup_mikrotik_profile())
                if customer.service_type == 'static' and plan.service_type == 'static' and not enable_only_hotspot:
                    self._activate_static(customer, plan, router, mikrotik, fup_applied=True)
            except Exception as e:
                errors.append(f"{router.name}: {e}")

        if errors:
            return {'success': False, 'error': ', '.join(errors)}
        return {'success': True}
    
    def _activate_pppoe(self, customer, plan, router, mikrotik, profile_name=None):
        profile_name = profile_name or (
            plan.get_fup_mikrotik_profile() if self._customer_has_fup(customer, plan) else plan.mikrotik_profile
        )
        pppoe_secret, created = PPPoESecret.objects.get_or_create(
            customer=customer,
            defaults={
                'router': router,
                'username': customer.pppoe_username or customer.username,
                'password': customer.pppoe_password or customer.username,
                'profile': profile_name,
                'status': 'enabled'
            }
        )
        
        # Ensure we sync to router regardless of whether created locally or not
        # If created locally, we definitely add.
        # If existing locally, we update. BUT if missing on router, update fails, so we must add.

        # needs_update tracks whether anything *locally recorded* changed --
        # used below to decide whether to interrupt an already-connected
        # session. It must NOT be used to skip the router push itself: local
        # DB state can drift from what's actually on the router (a prior
        # sync failure, a manual change on the router, an expiry/resubscribe
        # cycle, etc), so every activation always re-confirms the enabled
        # state on the router rather than trusting the local record.
        needs_update = False
        if not created:
             if pppoe_secret.profile != profile_name:
                 needs_update = True
             if pppoe_secret.password != (customer.pppoe_password or customer.username):
                 needs_update = True
             # If status was disabled locally, we need to re-enable
             if pppoe_secret.status != 'enabled':
                 needs_update = True

        success = False
        error = None
        if not created:
            # Try updating first
            res = mikrotik.update_pppoe_secret(
                username=pppoe_secret.username,
                profile=profile_name,
                password=customer.pppoe_password or customer.username,
                disabled='no'
            )
            if res['success']:
                success = True
            elif 'not found' in res.get('error', '').lower():
                # It's missing on router, so let's fall through to add it
                created = True
            else:
                error = res.get('error')
                logger.error(f"Failed to update PPPoE secret: {error}")

        if created:
            res = mikrotik.add_pppoe_secret(
                username=pppoe_secret.username,
                password=customer.pppoe_password or customer.username,
                profile=profile_name
            )
            if res['success']:
                success = True
            else:
                error = res.get('error')
                logger.error(f"Failed to add PPPoE secret: {error}")

        # Only record the customer as synced -- and only overwrite the
        # locally-recorded profile/password/status -- if the router actually
        # confirmed it. Recording success regardless of what the router said
        # is exactly how a customer ends up silently uncapped: their secret
        # keeps referencing (or falls back to) a profile that was never
        # actually applied, while the app believes activation succeeded.
        if not success:
            pppoe_secret.router = router
            pppoe_secret.synced_to_router = False
            pppoe_secret.save()
            raise Exception(f"Failed to activate PPPoE for {customer.username}: {error}")

        if not created:
            pppoe_secret.profile = profile_name
            pppoe_secret.password = customer.pppoe_password or customer.username
            pppoe_secret.status = 'enabled'

        pppoe_secret.router = router
        pppoe_secret.synced_to_router = True
        pppoe_secret.save()

        # Only interrupt an existing session if something actually changed
        # (or we just (re)created the secret) -- otherwise leave an
        # already-working connection alone.
        if needs_update or created:
            mikrotik.disconnect_pppoe_session(pppoe_secret.username)
    
    def push_pppoe_secret(self, pppoe_secret, previous_username=None):
        """
        Push a PPPoESecret's current username/password/profile/status to its
        router -- used after a manual edit (Django admin), which otherwise
        only changes the database. previous_username is the name the router
        knows it by, if the edit renamed it. Kicks the live session so the
        new credentials/profile take effect instead of waiting for a
        reconnect. Returns {'success': bool, 'error'?: str}.
        """
        router = pppoe_secret.router
        if not router:
            return {'success': False, 'error': 'no router assigned to this secret'}

        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username,
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        lookup = previous_username or pppoe_secret.username
        disabled = 'no' if pppoe_secret.status == 'enabled' else 'yes'
        res = mikrotik.update_pppoe_secret(
            lookup, name=pppoe_secret.username, password=pppoe_secret.password,
            profile=pppoe_secret.profile, disabled=disabled,
        )
        if not res['success'] and 'not found' in res.get('error', '').lower():
            res = mikrotik.add_pppoe_secret(pppoe_secret.username, pppoe_secret.password, pppoe_secret.profile)
            if res['success'] and disabled == 'yes':
                res = mikrotik.disable_pppoe_secret(pppoe_secret.username)

        PPPoESecret.objects.filter(pk=pppoe_secret.pk).update(synced_to_router=res['success'])
        if res['success']:
            mikrotik.disconnect_pppoe_session(lookup)
        else:
            logger.error(f"Failed to push PPPoE secret {pppoe_secret.username} to {router.name}: {res.get('error')}")
        return res

    def update_pppoe_credentials(self, customer, username, password):
        """
        Change a customer's PPPoE login everywhere it lives: the Customer
        fields (what the frontend shows and activation reads) and, if they
        already have a PPPoESecret, that record and the router. Returns
        push_pppoe_secret's result, or {'success': True, 'synced': False}
        when the customer was never activated on a router -- their next
        activation will simply use the new values.
        """
        customer.pppoe_username = username
        customer.pppoe_password = password
        customer.save(update_fields=['pppoe_username', 'pppoe_password'])

        secret = PPPoESecret.objects.select_related('router').filter(customer=customer).first()
        if not secret:
            return {'success': True, 'synced': False}
        previous_username = secret.username
        secret.username = username or customer.username
        secret.password = password or customer.username
        secret.save(update_fields=['username', 'password'])
        return {**self.push_pppoe_secret(secret, previous_username=previous_username), 'synced': True}

    def _activate_hotspot(self, customer, plan, router, mikrotik, profile_name=None):
        profile_name = profile_name or (
            plan.get_fup_mikrotik_profile() if self._customer_has_fup(customer, plan) else plan.mikrotik_profile
        )
        hotspot_user, created = HotspotUser.objects.get_or_create(
            customer=customer,
            defaults={
                'router': router,
                'username': customer.hotspot_username or customer.username,
                'password': customer.hotspot_password or customer.username,
                'profile': profile_name,
                'mac_address': customer.hotspot_mac_address,
                'status': 'enabled'
            }
        )

        # needs_update tracks whether anything *locally recorded* changed --
        # used below to decide whether to interrupt an already-connected
        # session. It must NOT be used to skip the router push itself: local
        # DB state can drift from what's actually on the router (a prior
        # sync failure, a manual change on the router, an expiry/resubscribe
        # cycle, etc), so every activation always re-confirms the enabled
        # state on the router rather than trusting the local record.
        needs_update = False
        if not created:
            if hotspot_user.profile != profile_name:
                needs_update = True
            if hotspot_user.password != (customer.hotspot_password or customer.username):
                needs_update = True
            current_mac = hotspot_user.mac_address or ''
            target_mac = customer.hotspot_mac_address or ''
            if current_mac != target_mac:
                needs_update = True
            if hotspot_user.status != 'enabled':
                needs_update = True

        success = False
        error = None
        if not created:
             res = mikrotik.update_hotspot_user(
                username=hotspot_user.username,
                     profile=profile_name,
                password=customer.hotspot_password or customer.username,
                disabled='no',
                mac_address=customer.hotspot_mac_address or ''
            )
             if res['success']:
                 success = True
             elif 'not found' in res.get('error', '').lower():
                 created = True
             else:
                 error = res.get('error')
                 logger.error(f"Failed to update Hotspot user: {error}")

        if created:
            res = mikrotik.add_hotspot_user(
                username=hotspot_user.username,
                password=hotspot_user.password,
                profile=profile_name,
                mac_address=hotspot_user.mac_address or ''
            )
            if res['success']:
                success = True
            else:
                error = res.get('error')
                logger.error(f"Failed to add Hotspot user: {error}")

        # Only record the customer as synced -- and only overwrite the
        # locally-recorded profile/password/status -- if the router actually
        # confirmed it. Recording success regardless of what the router said
        # is exactly how a customer ends up silently uncapped: their user
        # keeps referencing (or falls back to) a profile that was never
        # actually applied, while the app believes activation succeeded.
        if not success:
            hotspot_user.router = router
            hotspot_user.synced_to_router = False
            hotspot_user.save()
            raise Exception(f"Failed to activate Hotspot for {customer.username}: {error}")

        if not created:
            hotspot_user.profile = profile_name
            hotspot_user.password = customer.hotspot_password or customer.username
            hotspot_user.status = 'enabled'
            if customer.hotspot_mac_address:
                hotspot_user.mac_address = customer.hotspot_mac_address

        hotspot_user.router = router
        hotspot_user.synced_to_router = True
        hotspot_user.save()

        # Only interrupt an existing session if something actually changed
        # (or we just (re)created the user) -- otherwise leave an
        # already-working connection alone.
        if customer.hotspot_mac_address:
            mikrotik.ensure_hotspot_mac_login()
            res_mac = mikrotik.set_hotspot_mac_user(customer.hotspot_mac_address, profile_name)
            if not res_mac['success']:
                logger.error(f"{router.name}: MAC login user failed for {customer.username}: {res_mac.get('error')}")
            else:
                mikrotik.reset_unauthorized_hotspot_host(customer.hotspot_mac_address)

        if needs_update or created:
            mikrotik.disconnect_hotspot_session(hotspot_user.username)
            if customer.hotspot_mac_address:
                mikrotik.disconnect_hotspot_by_mac(customer.hotspot_mac_address)

    def _activate_static(self, customer, plan, router, mikrotik, fup_applied=None):
        """
        Static IP customers have no PPPoE/Hotspot auth -- their IP is
        configured manually (or by a technician on-site), so "activation"
        is just enforcing the plan's speed via a Simple Queue targeting
        that fixed address.
        """
        if not customer.static_ip_address:
            raise ValueError(f"{customer.username} has service_type='static' but no static_ip_address set")

        if fup_applied is None:
            fup_applied = self._customer_has_fup(customer, plan)
        upload_speed = plan.fup_upload_speed if fup_applied else plan.upload_speed
        download_speed = plan.fup_download_speed if fup_applied else plan.download_speed
        rate_limit = f"{upload_speed}M/{download_speed}M"
        res = mikrotik.add_simple_queue(
            name=customer.username,
            target=f"{customer.static_ip_address}/32",
            max_limit=rate_limit,
            comment=f"ISP Billing - {plan.name}",
        )
        if not res['success']:
            raise Exception(res.get('error'))

        binding = mikrotik.add_ip_binding_bypass(
            customer.static_ip_address, comment=f"static-{customer.username}"
        )
        if not binding['success']:
            raise Exception(f"IP binding failed: {binding.get('error')}")

    def sync_static_plan(self, plan, router, mikrotik):
        """Push a static plan's current speed to each active static customer's queue."""
        from apps.billing.models import Subscription
        synced, failed = [], []
        subscriptions = Subscription.objects.filter(
            plan=plan, status='active', expiry_date__gt=timezone.now(), customer__service_type='static',
        ).select_related('customer')
        for subscription in subscriptions:
            customer = subscription.customer
            try:
                self._activate_static(customer, plan, router, mikrotik)
                synced.append(customer.username)
            except Exception as e:
                failed.append(f"{customer.username}: {e}")
        return {'success': synced, 'failed': failed}

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
        pppoe_gateway = None
        try:
            pppoe_gateway = str(ipaddress.ip_network(router.pppoe_subnet, strict=False)[1])
        except ValueError:
            logger.error(f"{router.name}: invalid pppoe_subnet {router.pppoe_subnet!r}, leaving PPPoE profiles' local-address unset")
        for plan in plans:
            rate_limit = f"{plan.upload_speed}M/{plan.download_speed}M"
            if plan.service_type in ['pppoe', 'both']:
                res = mikrotik.update_pppoe_profile(plan.mikrotik_profile, rate_limit, remote_address='pppoe_pool', local_address=pppoe_gateway)
                if not res['success'] and 'not found' in res.get('error', ''):
                    res = mikrotik.add_pppoe_profile(plan.mikrotik_profile, rate_limit, remote_address='pppoe_pool', local_address=pppoe_gateway)
                if res['success']: results['success'].append(f"PPPoE: {plan.name}")
                else: results['failed'].append(f"PPPoE: {plan.name} - {res.get('error')}")
                if plan.fup_limit_gb is not None:
                    fup_profile = plan.get_fup_mikrotik_profile()
                    fup_rate = f"{plan.fup_upload_speed}M/{plan.fup_download_speed}M"
                    fup_res = mikrotik.update_pppoe_profile(fup_profile, fup_rate, remote_address='pppoe_pool', local_address=pppoe_gateway)
                    if not fup_res['success'] and 'not found' in fup_res.get('error', ''):
                        fup_res = mikrotik.add_pppoe_profile(fup_profile, fup_rate, remote_address='pppoe_pool', local_address=pppoe_gateway)
                    if fup_res['success']: results['success'].append(f"PPPoE FUP: {plan.name}")
                    else: results['failed'].append(f"PPPoE FUP: {plan.name} - {fup_res.get('error')}")
            if plan.service_type in ['hotspot', 'both']:
                res = mikrotik.update_hotspot_profile(plan.mikrotik_profile, rate_limit)
                if not res['success'] and 'not found' in res.get('error', ''):
                    res = mikrotik.add_hotspot_profile(plan.mikrotik_profile, rate_limit)
                if res['success']: results['success'].append(f"Hotspot: {plan.name}")
                else: results['failed'].append(f"Hotspot: {plan.name} - {res.get('error')}")
                if plan.fup_limit_gb is not None:
                    fup_profile = plan.get_fup_mikrotik_profile()
                    fup_rate = f"{plan.fup_upload_speed}M/{plan.fup_download_speed}M"
                    fup_res = mikrotik.update_hotspot_profile(fup_profile, fup_rate)
                    if not fup_res['success'] and 'not found' in fup_res.get('error', ''):
                        fup_res = mikrotik.add_hotspot_profile(fup_profile, fup_rate)
                    if fup_res['success']: results['success'].append(f"Hotspot FUP: {plan.name}")
                    else: results['failed'].append(f"Hotspot FUP: {plan.name} - {fup_res.get('error')}")
            if plan.service_type == 'static':
                plan_routers = plan.routers.filter(is_active=True)
                if not plan_routers.exists() or plan_routers.filter(pk=router.pk).exists():
                    static = self.sync_static_plan(plan, router, mikrotik)
                    results['success'].extend(f"Static: {name}" for name in static['success'])
                    results['failed'].extend(f"Static: {err}" for err in static['failed'])
        refreshed = mikrotik.refresh_hotspot_sessions()
        if refreshed.get('refreshed'):
            results['success'].append(f"Reconnected {len(refreshed['refreshed'])} session(s) to apply new speeds")
        return results

    def sync_all_users(self, router=None):
        if router is None:
            routers = list(Router.objects.filter(is_active=True))
            if not routers:
                return {'error': 'No active router configured'}
            merged = {'success': [], 'failed': []}
            for r in routers:
                res = self.sync_all_users(router=r)
                merged['success'] += [f"{r.name}: {s}" for s in res.get('success', [])]
                merged['failed'] += [f"{r.name}: {s}" for s in res.get('failed', [])]
            return merged

        from apps.billing.models import Subscription
        results = {'success': [], 'failed': []}
        active_subs = Subscription.objects.filter(status='active', expiry_date__gt=timezone.now())
        plan_scoped = lambda plan: (not plan.routers.filter(is_active=True).exists()
                                    or plan.routers.filter(pk=router.pk).exists())
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username, 
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        for sub in active_subs:
            customer = sub.customer
            plan = sub.plan
            try:
                # Both customer AND plan must support the service -- a
                # customer.service_type='both' on a hotspot-ONLY plan must
                # not attempt PPPoE activation using that plan's (hotspot)
                # mikrotik_profile, same requirement activate_customer
                # already enforces.
                if customer.service_type in ['pppoe', 'both'] and plan.service_type in ['pppoe', 'both'] and plan_scoped(plan):
                    self._activate_pppoe(customer, plan, router, mikrotik)
                    results['success'].append(f"PPPoE: {customer.username}")
                if customer.service_type in ['hotspot', 'both'] and plan.service_type in ['hotspot', 'both']:
                    self._activate_hotspot(customer, plan, router, mikrotik)
                    results['success'].append(f"Hotspot: {customer.username}")
                if customer.service_type == 'static' and plan.service_type == 'static' and plan_scoped(plan):
                    self._activate_static(customer, plan, router, mikrotik)
                    results['success'].append(f"Static: {customer.username}")
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
        # access) are left exactly as they are. Configured ports that don't
        # actually exist on this router (e.g. wlan1 on a wired-only model)
        # are skipped rather than attempted-and-failed, since
        # MIKROTIK_PROVISION_BRIDGE_PORTS is one fixed list shared across
        # every router regardless of hardware. ---
        step(f'Create {interface} bridge', mikrotik.add_bridge, interface)

        # RouterOS's own quick-setup wizard adds a `forward
        # fasttrack-connection` firewall rule by default on virtually every
        # router. Combined with bridge fast-forward (just handled by
        # add_bridge above), this is enough on its own to let a customer's
        # traffic bypass Simple Queue rate-limiting entirely after the
        # first few packets of each connection -- silently defeating every
        # plan's speed cap regardless of how correctly it's configured.
        step('Disable fasttrack (bypasses queue rate-limits)', mikrotik.disable_fasttrack)

        existing_interface_names = set()
        interfaces_res = mikrotik.list_interfaces()
        if interfaces_res.get('success'):
            existing_interface_names = {i['name'] for i in interfaces_res['interfaces']}
        for port in settings.MIKROTIK_PROVISION_BRIDGE_PORTS:
            if existing_interface_names and port not in existing_interface_names:
                results['success'].append(f'Skip {port} (not present on this router)')
                continue
            step(f'Add {port} to {interface}', mikrotik.set_bridge_port, port, interface)

        # --- Hotspot: interface IP, pool, DHCP, server profile, server ---
        step('Hotspot interface address', mikrotik.add_interface_address,
             f"{hotspot_gateway}/{hotspot_net.prefixlen}", interface, comment='ISP Billing - Hotspot gateway')
        step('Hotspot IP pool', mikrotik.add_ip_pool, 'hotspot_pool', hotspot_pool_range)
        step('Hotspot DHCP server', mikrotik.add_dhcp_server, 'hotspot_dhcp', interface, 'hotspot_pool')
        step('Hotspot DHCP network', mikrotik.add_dhcp_network,
             str(hotspot_net), hotspot_gateway, dns_servers=router.dns_servers)
        step('Hotspot default user profile', mikrotik.add_hotspot_profile, 'default', settings.MIKROTIK_DEFAULT_PROFILE_RATE_LIMIT)
        step('Hotspot server profile', mikrotik.add_hotspot_server_profile,
             'hotspot_profile', hotspot_gateway)
        step('Hotspot server', mikrotik.add_hotspot_server,
             'hotspot1', interface, 'hotspot_pool', 'hotspot_profile')
        login_page_res = mikrotik.configure_hotspot_login_page(
            'hotspot_profile', build_hotspot_login_html(router.portal_url)
        )
        if login_page_res.get('success'):
            results['success'].append(
                f"Hotspot login page ({login_page_res['path']}; profile directory: {login_page_res['html_directory']})"
            )
        else:
            results['failed'].append(f"Hotspot login page: {login_page_res.get('error')}")

        # --- PPPoE: pool, default profile, server ---
        step('PPPoE IP pool', mikrotik.add_ip_pool, 'pppoe_pool', pppoe_pool_range)
        step('PPPoE default profile', mikrotik.add_pppoe_profile, 'default',
             rate_limit=settings.MIKROTIK_DEFAULT_PROFILE_RATE_LIMIT, remote_address='pppoe_pool',
             local_address=pppoe_gateway)
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

    def sync_hotspot_login_page(self, router):
        """Refresh only the custom login page and the profile's HTML folder."""
        portal_url_error = validate_portal_url(router.portal_url)
        if portal_url_error:
            return {'error': portal_url_error}

        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username,
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        result = mikrotik.configure_hotspot_login_page(
            'hotspot_profile', build_hotspot_login_html(router.portal_url)
        )
        if not result.get('success'):
            return {'error': result.get('error')}
        return result

    # Shared comment prefix so enable/disable find and remove exactly the
    # rules this feature added, never anything an admin configured by hand.
    WAN_MGMT_COMMENT_PREFIX = 'ISP Billing - WAN Mgmt Access'

    def enable_wan_management_access(self, router, username=None, password=None):
        """
        Opens Winbox + SSH on this router's WAN interface
        (settings.MIKROTIK_WAN_INTERFACE), scoped to whatever subnet that
        interface's own current address is on -- RouterOS blocks
        management access from WAN by default, so this is needed to reach
        the router from the upstream network that gives it internet.
        Derives the subnet live from the router's own WAN address rather
        than a stored/entered value, so it can't go stale if the upstream
        network's addressing ever changes.
        """
        snapshot_res = self.snapshot_router(router, username=username, password=password)
        if not snapshot_res.get('success'):
            return {'error': f"Could not connect to router: {snapshot_res.get('error')}"}

        mikrotik = MikroTikService(
            host=router.ip_address, username=username or router.username,
            password=password or router.password, port=router.port, use_ssl=router.use_ssl
        )

        wan_interface = settings.MIKROTIK_WAN_INTERFACE
        addr_res = mikrotik.get_interface_address(wan_interface)
        if not addr_res.get('success'):
            return {'error': f"Could not read {wan_interface}'s address: {addr_res.get('error')}"}
        if not addr_res.get('address'):
            return {'error': f"{wan_interface} has no IP address right now (DHCP not bound yet?) -- nothing to scope the rule to."}

        try:
            subnet = ipaddress.ip_interface(addr_res['address']).network
        except ValueError as e:
            return {'error': f"Could not parse {wan_interface}'s address {addr_res['address']!r}: {e}"}

        result = mikrotik.allow_management_access(wan_interface, str(subnet), self.WAN_MGMT_COMMENT_PREFIX)
        if not result.get('success'):
            return {'error': result.get('error')}

        # LAN/VPN subnets reach the router from any interface, so no in-interface match.
        extra_subnets = []
        for raw in settings.MIKROTIK_MGMT_ALLOWED_SUBNETS:
            try:
                net = str(ipaddress.ip_network(raw, strict=False))
            except ValueError as e:
                return {'error': f'Invalid MIKROTIK_MGMT_ALLOWED_SUBNETS entry {raw!r}: {e}'}
            res = mikrotik.allow_management_access(None, net, self.WAN_MGMT_COMMENT_PREFIX, tag=f' [{net}]')
            if not res.get('success'):
                return {'error': res.get('error')}
            extra_subnets.append(net)

        # Checks + provisioning beyond the input rules: Winbox/SSH services must be
        # enabled and allow-listed, and LAN/VPN hosts must be able to forward to
        # devices behind the router (radios etc.).
        allowed = [str(subnet)] + extra_subnets
        svc_res = mikrotik.ensure_service_access(['winbox', 'ssh'], allowed)
        if not svc_res.get('success'):
            return {'error': f"Service check failed: {svc_res.get('error')}"}
        checks = svc_res['report']
        for net in extra_subnets:
            fwd = mikrotik.ensure_forward_accept(
                net, wan_interface, f'{self.WAN_MGMT_COMMENT_PREFIX} [{net}] (Forward)'
            )
            if not fwd.get('success'):
                return {'error': f"Forward rule for {net} failed: {fwd.get('error')}"}
        if extra_subnets:
            checks.append(f"forward: {', '.join(extra_subnets)} may reach networks behind the router (not WAN)")
        return {'success': True, 'subnet': str(subnet), 'extra_subnets': extra_subnets, 'checks': checks}

    # Shared by every object enable_management_vlan creates, so a re-run
    # updates them and disable removes exactly those, nothing hand-made.
    MGMT_VLAN_COMMENT_PREFIX = 'ISP Billing - Radio Mgmt'

    def enable_management_vlan(self, router, username=None, password=None):
        """
        Set up a separate management network for radios/APs: a VLAN on the
        customer bridge with its own subnet, DHCP and NAT, outside the
        Hotspot (so radios need no login or bypass), reachable from the
        WAN-side LAN and blocked from customers. VLAN ID and subnet are
        chosen from what's free on the router -- see plan_management_vlan.
        Safe to re-run: it updates the existing setup in place.
        """
        snapshot_res = self.snapshot_router(router, username=username, password=password)
        if not snapshot_res.get('success'):
            return {'error': f"Could not connect to router: {snapshot_res.get('error')}"}

        mikrotik = MikroTikService(
            host=router.ip_address, username=username or router.username,
            password=password or router.password, port=router.port, use_ssl=router.use_ssl
        )
        layout_res = mikrotik.read_network_layout()
        if not layout_res.get('success'):
            return {'error': f"Could not read router configuration: {layout_res.get('error')}"}
        try:
            plan = plan_management_vlan(
                layout_res['layout'], settings.MIKROTIK_WAN_INTERFACE, settings.MIKROTIK_PROVISION_INTERFACE,
                self.MGMT_VLAN_COMMENT_PREFIX, settings.MIKROTIK_MGMT_VLAN_ID,
                extra_allowed=settings.MIKROTIK_MGMT_VLAN_ALLOWED_SUBNETS,
            )
        except ValueError as e:
            return {'error': str(e)}

        result = mikrotik.apply_management_vlan(plan, self.MGMT_VLAN_COMMENT_PREFIX, dns_servers=router.dns_servers)
        if not result.get('success'):
            return {'error': f"Applying management VLAN failed: {result.get('error')}"}
        return {'success': True, 'plan': plan, 'report': result['report']}

    def disable_management_vlan(self, router, username=None, password=None):
        """Removes exactly what enable_management_vlan created."""
        snapshot_res = self.snapshot_router(router, username=username, password=password)
        if not snapshot_res.get('success'):
            return {'error': f"Could not connect to router: {snapshot_res.get('error')}"}

        mikrotik = MikroTikService(
            host=router.ip_address, username=username or router.username,
            password=password or router.password, port=router.port, use_ssl=router.use_ssl
        )
        result = mikrotik.remove_management_vlan(self.MGMT_VLAN_COMMENT_PREFIX)
        if not result.get('success'):
            return {'error': result.get('error')}
        return {'success': True, 'removed_count': result.get('removed_count', 0)}

    def disable_wan_management_access(self, router, username=None, password=None):
        """Removes exactly the rules enable_wan_management_access added."""
        snapshot_res = self.snapshot_router(router, username=username, password=password)
        if not snapshot_res.get('success'):
            return {'error': f"Could not connect to router: {snapshot_res.get('error')}"}

        mikrotik = MikroTikService(
            host=router.ip_address, username=username or router.username,
            password=password or router.password, port=router.port, use_ssl=router.use_ssl
        )
        result = mikrotik.revoke_management_access(self.WAN_MGMT_COMMENT_PREFIX)
        if not result.get('success'):
            return {'error': result.get('error')}
        return {'success': True, 'removed_count': result.get('removed_count', 0)}

network_automation = NetworkAutomation()
