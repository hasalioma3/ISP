
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
    Collect usage statistics from MikroTik Router(s)
    Runs periodically (e.g. every 5-10 minutes)
    """
    logger.info("Starting usage statistics collection...")
    from apps.network.models import Router
    
    # Iterate all active routers
    routers = Router.objects.filter(is_active=True)
    if not routers.exists():
        logger.warning("No active routers found for usage stats.")
        return

    for router in routers:
        try:
            mikrotik = MikroTikService(
                host=router.ip_address,
                username=router.username, 
                password=router.password,
                port=router.port,
                use_ssl=router.use_ssl
            )
            conn = mikrotik._get_connection()
            api = conn.get_api()
            
            # 1. Fetch Hotspot Active Users
            try:
                hotspot_active = api.get_resource('/ip/hotspot/active').get()
                for session in hotspot_active:
                    username = session.get('user')
                    # Convert to integer, handle missing values
                    try:
                        bytes_in = int(session.get('bytes-in', 0))   # Upload
                        bytes_out = int(session.get('bytes-out', 0)) # Download
                    except:
                        continue
                        
                    session_id = session.get('.id', '') # Internal ID, might change. prefer 'id' or user+uptime
                    mac = session.get('mac-address', '')
                    ip = session.get('address', '')
                    
                    update_usage_record(username, bytes_in, bytes_out, mac, ip, session_id, 'hotspot')
            except Exception as e:
                logger.error(f"Error fetching hotspot stats from {router.name}: {e}")
            
            # 2. Fetch PPPoE Active Connections (via Interfaces)
            # PPPoE active sessions are best tracked via Interface stats for bytes
            try:
                # Get all dynamic interfaces (usually PPPoE ones are dynamic)
                # Or filter by type=pppoe-in if library supports it, otherwise get all and filter in python
                interfaces = api.get_resource('/interface').get()
                pppoe_interfaces = [i for i in interfaces if i.get('type') == 'pppoe-in']
                
                for iface in pppoe_interfaces:
                    # Interface name is usually the username for PPPoE Server bindings
                    # Assuming <pppoe-username> naming convention
                    username = iface.get('name')
                    # Typically names are like "<pppoe-user>", sometimes "pppoe-<user>"
                    # But standard Mikrotik use username as interface name
                    
                    try:
                        # RX = Upload (from client), TX = Download (to client)
                        bytes_in = int(iface.get('rx-byte', 0))
                        bytes_out = int(iface.get('tx-byte', 0))
                    except:
                        continue
                        
                    session_id = iface.get('.id', '')
                    
                    # Try to find IP (optional, might need /ip/address lookup)
                    ip = '' 
                    
                    update_usage_record(username, bytes_in, bytes_out, '', ip, session_id, 'pppoe')

            except Exception as e:
                logger.error(f"Error fetching PPPoE stats from {router.name}: {e}")

            conn.disconnect()
            
        except Exception as e:
            logger.error(f"Failed to collect usage stats from router {router.name}: {e}")
            
    logger.info("Usage statistics collection completed.")

def update_usage_record(username, upload, download, mac, ip, session_id, service_type):
    try:
        from apps.customers.models import Customer
        
        # 1. Find Customer
        # Handle "Phone_MAC" or "Phone" usernames
        customer = Customer.objects.filter(username=username).first()
        if not customer:
            # Maybe username is different?
            return

        # 2. Find Active Subscription
        subscription = Subscription.objects.filter(
            customer=customer, 
            status='active'
        ).last()
        
        if not subscription:
            return

        # 3. Create or Update Usage Record
        # We want to track PER SESSION if possible, or minimally per day.
        # User asked for "database for each subscriber session".
        # Session ID from Mikrotik (*123) changes on reconnect. 
        # Using it is good for distinct sessions.
        
        today = timezone.now()
        
        # Check if we have an open record for this session_id?
        # But 'session_id' (*A1) is ephemeral and reused.
        # Better key: User + StartTime? Or just User + Date + InterfaceID (if stable during session)?
        # For now, let's update a record for Today + User.
        # If we really want "Session" granularity, we need to detect Session Start/Stop (via Accounting/RADIUS).
        # With just polling, we only see "Current Totals".
        # If we just overwrite "Current Totals" into a record, we track the *current* session.
        # When session drops, the record remains. 
        # When new session starts, bytes reset to 0. We need to detect this reset.
        
        # LOGIC:
        # Find latest record for user.
        # If (new_bytes < latest_record.bytes) -> Session reset! -> Create NEW record.
        # Else -> Update existing record.
        
        latest_record = UsageRecord.objects.filter(
            customer=customer,
            subscription=subscription
        ).order_by('-created_at').first()
        
        create_new = False
        if not latest_record:
            create_new = True
        else:
            # Check if counters reset (new session)
            # Threshold: if current bytes are significantly less than stored, it's a reset.
            prev_total = latest_record.upload_bytes + latest_record.download_bytes
            curr_total = upload + download
            
            # If current < prev, likely a reset (new session started)
            if curr_total < prev_total:
                create_new = True
            
            # Also, if getting old (e.g., > 24h), maybe force new record? 
            # Let's stick to session reset logic for now.
            
        if create_new:
            UsageRecord.objects.create(
                customer=customer,
                subscription=subscription,
                upload_bytes=upload,
                download_bytes=download,
                session_time_seconds=0, # Hard to track via poll without uptime
                start_time=timezone.now(),
                nas_ip_address='',
                framed_ip_address=ip,
                session_id=session_id # Store mikrotik ID for ref
            )
        else:
            latest_record.upload_bytes = upload
            latest_record.download_bytes = download
            # Update framed IP if it changed/appeared
            if ip: latest_record.framed_ip_address = ip
            latest_record.save()
            
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
