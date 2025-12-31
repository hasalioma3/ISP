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
    
    def activate_customer(self, customer, plan):
        try:
            router = Router.objects.filter(is_active=True).first()
            if not router:
                return {'success': False, 'error': 'No active router configured'}
            mikrotik = MikroTikService(
                host=router.ip_address, username=router.username, 
                password=router.password, port=router.port, use_ssl=router.use_ssl
            )
            if customer.service_type in ['pppoe', 'both']:
                self._activate_pppoe(customer, plan, router, mikrotik)
            if customer.service_type in ['hotspot', 'both']:
                self._activate_hotspot(customer, plan, router, mikrotik)
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
        if created:
            mikrotik.add_pppoe_secret(
                username=pppoe_secret.username, password=pppoe_secret.password, profile=plan.mikrotik_profile
            )
        else:
            pppoe_secret.profile = plan.mikrotik_profile
            pppoe_secret.status = 'enabled'
            pppoe_secret.save()
            mikrotik.update_pppoe_secret(username=pppoe_secret.username, profile=plan.mikrotik_profile, disabled='no')
            mikrotik.disconnect_pppoe_session(pppoe_secret.username)
        pppoe_secret.synced_to_router = True
        pppoe_secret.save()
    
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
        if created:
            mikrotik.add_hotspot_user(
                username=hotspot_user.username, 
                password=hotspot_user.password, 
                profile=plan.mikrotik_profile,
                mac_address=hotspot_user.mac_address
            )
        else:
            hotspot_user.profile = plan.mikrotik_profile
            hotspot_user.status = 'enabled'
            # Sync MAC if available and different
            if customer.hotspot_mac_address:
                hotspot_user.mac_address = customer.hotspot_mac_address
            
            hotspot_user.save()
            mikrotik.update_hotspot_user(
                username=hotspot_user.username, 
                profile=plan.mikrotik_profile, 
                disabled='no',
                mac_address=hotspot_user.mac_address
            )
            mikrotik.disconnect_hotspot_session(hotspot_user.username)
        hotspot_user.synced_to_router = True
        hotspot_user.save()

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
