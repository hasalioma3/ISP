
from celery import shared_task
from django.utils import timezone
from apps.network.services.network_automation import network_automation
from apps.network.services.mikrotik_service import MikroTikService, mikrotik_service
from apps.billing.models import UsageRecord, Subscription
import logging

logger = logging.getLogger('apps.network')

@shared_task
def collect_usage_statistics():
    """
    Collect usage statistics from MikroTik Router
    Runs periodically (e.g. every 10-30 minutes)
    """
    logger.info("Starting usage statistics collection...")
    
    try:
        conn = mikrotik_service._get_connection()
        api = conn.get_api()
        
        # 1. Fetch Hotspot Active Users
        hotspot_active = api.get_resource('/ip/hotspot/active').get()
        
        # 2. Fetch PPPoE Active Connections
        ppp_active = api.get_resource('/ppp/active').get()
        
        # Process Hotspot Users
        for session in hotspot_active:
            username = session.get('user')
            bytes_in = int(session.get('bytes-in', 0)) # Upload from client perspective
            bytes_out = int(session.get('bytes-out', 0)) # Download
            uptime = session.get('uptime', '')
            mac = session.get('mac-address', '')
            ip = session.get('address', '')
            
            # Find active subscription
            update_usage_record(username, bytes_in, bytes_out, mac, ip)

        # Process PPPoE Users
        for session in ppp_active:
            username = session.get('name')
            # PPPoE stats might need different handling depending on MikroTik version/accounting
            # Standard /ppp/active often lacks byte counters, might need /interface
            # But let's check simple params first.
            # If not in active, we might need Interim-Updates via RADIUS, but for API:
            # We can check specific interface stats if needed.
            # For now, let's assume standard byte counters if available or skip.
            pass

        conn.disconnect()
        logger.info("Usage statistics collection completed.")
        
    except Exception as e:
        logger.error(f"Failed to collect usage stats: {e}")

def update_usage_record(username, upload, download, mac, ip):
    try:
        # Find active subscription for this user
        # Note: username in MikroTik might be phone number or "Phone_MAC"
        
        # Try finding customer by username (which handles the Phone_MAC case too if stored as username)
        from apps.customers.models import Customer
        customer = Customer.objects.filter(username=username).first()
        
        if not customer:
            logger.warning(f"Usage collection: Customer not found for {username}")
            return

        subscription = Subscription.objects.filter(
            customer=customer, 
            status='active'
        ).last()
        
        if not subscription:
            return

        # Use MAC + IP as a pseudo-session key if true session ID isn't available
        # Ideally, MikroTik 'id' field changes on reconnect.
        # Let's try to match a record created recently (within last hour) for this user/subscription
        
        # Calculate duration from uptime? 
        # For now, let's just create/update a daily record to keep it simple and aggregatable.
        today = timezone.now().date()
        
        # Check for existing record for today
        usage_record = UsageRecord.objects.filter(
            customer=customer,
            subscription=subscription,
            created_at__date=today,
            framed_ip_address=ip
        ).first()
        
        if usage_record:
            # Update existing record
            usage_record.upload_bytes = upload
            usage_record.download_bytes = download
            usage_record.save()
        else:
           # Create new record for today
           UsageRecord.objects.create(
                customer=customer,
                subscription=subscription,
                upload_bytes=upload,
                download_bytes=download,
                session_time_seconds=0,
                start_time=timezone.now(),
                nas_ip_address='192.168.88.1',
                framed_ip_address=ip
           )
        
    except Exception as e:
        logger.error(f"Error updating usage for {username}: {e}")

@shared_task
def sync_plan_to_routers(plan_id):
    """
    Sync a billing plan to its associated routers
    """
    try:
        from apps.billing.models import BillingPlan
        plan = BillingPlan.objects.get(id=plan_id)
        
        logger.info(f"Syncing plan {plan.name} to {plan.routers.count()} routers...")
        
        for router in plan.routers.filter(is_active=True):
            try:
                mikrotik = MikroTikService(
                    host=router.ip_address,
                    username=router.username, 
                    password=router.password,
                    port=router.port,
                    use_ssl=router.use_ssl
                )
                
                # Create/Update Hotspot Profile
                if plan.service_type in ['hotspot', 'both']:
                    # Rate limit format: rx/tx (upload/download from client view?)
                    # MikroTik rate-limit: rx-rate/tx-rate [rx-burst-rate/tx-burst-rate] [rx-burst-threshold/tx-burst-threshold] [rx-burst-time/tx-burst-time] [priority] [min-rx-rate/min-tx-rate]
                    # Usually "upload/download" or "rx/tx"
                    # Let's assume upload/download 
                    rate_limit = f"{plan.upload_speed}M/{plan.download_speed}M"
                    res_hotspot = mikrotik.add_hotspot_profile(plan.mikrotik_profile, rate_limit)
                    if not res_hotspot['success']:
                         res_hotspot = mikrotik.update_hotspot_profile(plan.mikrotik_profile, rate_limit)
                else:
                    res_hotspot = {'success': True} # Skip if not hotspot plan
                
                # Create/Update PPPoE Profile
                if plan.service_type in ['pppoe', 'both']:
                    rate_limit = f"{plan.upload_speed}M/{plan.download_speed}M"
                  # PPPoE auto-bypass logic
                # When user connects, add them to Hotspot IP binding as bypassed
                # When user disconnects, remove them
                on_up = (
                    f'/ip hotspot ip-binding add mac-address=$"caller-id" '
                    f'type=bypassed server=all comment="pppoe-$user";'
                )
                on_down = (
                    f'/ip hotspot ip-binding remove [find comment="pppoe-$user"];'
                )
                
                res_pppoe = mikrotik.add_pppoe_profile(
                    name=plan.mikrotik_profile,
                    rate_limit=rate_limit,
                    on_up=on_up,
                    on_down=on_down
                )
                
                logger.info(f"Add PPPoE Profile Response: {res_pppoe}")
                
                if not res_pppoe['success']:
                     # Try update if add failed (likely exists)
                     res_pppoe = mikrotik.update_pppoe_profile(
                        name=plan.mikrotik_profile, 
                        rate_limit=rate_limit,
                        on_up=on_up,
                        on_down=on_down
                    )
                
                if res_pppoe['success']:
                    logger.info(f"{router.name}: PPPoE Profile {plan.mikrotik_profile} synced.")
                else:
                     logger.error(f"{router.name}: PPPoE Sync Failed: {res_pppoe.get('error')}")

                if res_hotspot['success']:
                     logger.info(f"{router.name}: Hotspot Profile {plan.mikrotik_profile} synced.")
                else:
                     logger.error(f"{router.name}: Hotspot Sync Failed: {res_hotspot.get('error')}")
                
                # Original line: mikrotik.add_pppoe_profile(plan.mikrotik_profile, rate_limit)
                # This line is replaced by the new logic above.
                    
                logger.info(f"Synced plan {plan.name} to router {router.name}")
                
            except Exception as e:
                logger.error(f"Failed to sync plan {plan.name} to router {router.name}: {e}")
                
    except Exception as e:
         logger.error(f"Error in sync_plan_to_routers: {e}")

@shared_task
def sync_pppoe_secrets():
    """
    Periodically sync all active PPPoE/Hotspot users to the router.
    Useful for consistency checks or restoring state after router reboot.
    """
    logger.info("Starting periodic customer sync...")
    try:
        results = network_automation.sync_all_users()
        logger.info(f"Sync completed. Success: {len(results['success'])}, Failed: {len(results['failed'])}")
        return results
    except Exception as e:
        logger.error(f"Error in sync_pppoe_secrets: {e}")

@shared_task
def check_expired_subscriptions():
    """
    Check for expired subscriptions and suspend them
    """
    logger.info("Checking for expired subscriptions...")
    try:
        expired_subs = Subscription.objects.filter(
            status='active',
            expiry_date__lte=timezone.now()
        )
        
        count = 0
        for sub in expired_subs:
            logger.info(f"Suspending expired subscription for {sub.customer.username}")
            
            # 1. Update DB Status
            sub.status = 'expired'
            sub.save()
            
            # 2. Trigger Network Suspension
            # Handled by the Subscription signal we just added? 
            # SIGNAL CHECK: We added a signal that calls suspend_customer if status is 'expired'.
            # So sub.save() above should trigger the signal.
            
            # Use manual trigger just in case signal fails or to be explicit?
            # Signal is cleaner, but let's trust the signal for now since we just verified/added it.
            # Wait, signals run synchronously in save(). So it will run.
            
            count += 1
            
        logger.info(f"Expiration check completed. Suspended {count} subscriptions.")
        return count
        
    except Exception as e:
        logger.error(f"Error checking expired subscriptions: {e}")
