"""
Network Automation Service
Handles automatic network access control based on payment and subscription status
"""

import logging
from django.utils import timezone
from apps.network.models import PPPoESecret, HotspotUser, Router
from apps.network.services.mikrotik_service import MikroTikService

logger = logging.getLogger('apps.network')

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

    def sync_all_profiles(self):
        from apps.billing.models import BillingPlan
        results = {'success': [], 'failed': []}
        plans = BillingPlan.objects.filter(is_active=True)
        router = Router.objects.filter(is_active=True).first()
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

    def sync_all_users(self):
        from apps.billing.models import Subscription
        results = {'success': [], 'failed': []}
        active_subs = Subscription.objects.filter(status='active', expiry_date__gt=timezone.now())
        router = Router.objects.filter(is_active=True).first()
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

network_automation = NetworkAutomation()
