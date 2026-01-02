
from celery import shared_task
from django.utils import timezone
from apps.network.services.network_automation import network_automation
from apps.network.services.mikrotik_service import MikroTikService, mikrotik_service
from apps.billing.models import UsageRecord, Subscription
import logging

logger = logging.getLogger('apps.network')


def parse_mikrotik_uptime(uptime_str):
    """
    Parse MikroTik uptime string (e.g. '2w1d', '1h30m', '50s') to seconds.
    """
    if not uptime_str:
        return 0
    
    total_seconds = 0
    current_num = ""
    
    for char in str(uptime_str):
        if char.isdigit():
            current_num += char
        else:
            if not current_num: continue
            val = int(current_num)
            if char == 'w': total_seconds += val * 604800
            elif char == 'd': total_seconds += val * 86400
            elif char == 'h': total_seconds += val * 3600
            elif char == 'm': total_seconds += val * 60
            elif char == 's': total_seconds += val
            current_num = ""
            
    return total_seconds

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
        
            # 1. Collect Interface Stats (ether1 - WAN)
            try:
                # Monitor 'ether1' (WAN) traffic
                # WAN RX = Internet Download -> Client Download
                # WAN TX = Internet Upload <- Client Upload
                if_stats_list = api.get_resource('/interface').call('monitor-traffic', {
                    'interface': 'ether1', 
                    'once': 'true'
                })
                
                if if_stats_list:
                    s = if_stats_list[0]
                    wan_rx = int(s.get('rx-bits-per-second', 0)) # Download from Net
                    wan_tx = int(s.get('tx-bits-per-second', 0)) # Upload to Net
                    
                    # Import Model here to avoid circular imports if any
                    from apps.network.models import RouterInterfaceStat
                    
                    # We map:
                    # DB tx_bps (Client Download) = WAN RX
                    # DB rx_bps (Client Upload) = WAN TX
                    RouterInterfaceStat.objects.update_or_create(
                        router=router,
                        interface_name='ether1',
                        defaults={
                            'rx_bps': wan_tx, # Client Upload
                            'tx_bps': wan_rx  # Client Download
                        }
                    )
                    logger.debug(f"Router {router.name}: ether1 (WAN) rate Download={wan_rx}, Upload={wan_tx}")
            except Exception as e:
                # Interface might not exist or other error
                pass

            # 2. Fetch Hotspot Active Users
            try:
                hotspot_active = api.get_resource('/ip/hotspot/active').get()
                
                # Fetch Queues for Realtime Rate
                try:
                    queues = api.get_resource('/queue/simple').get()
                    # Create map: name -> queue_data
                    # Hotspot queues are usually "<hotspot-user>"
                    queue_map = {q.get('name'): q for q in queues}
                except:
                    queue_map = {}
                
                logger.info(f"Router {router.name}: Found {len(hotspot_active)} active hotspot users.")
                for session in hotspot_active:
                    username = session.get('user')
                    # ... (rest of parsing)
                    
                    # Try to find queue rate
                    real_up_mbps = None
                    real_down_mbps = None
                    
                    queue_data = None
                    q_name = f"<hotspot-{username}>" 
                    
                    if q_name in queue_map:
                        queue_data = queue_map[q_name]
                    elif username in queue_map:
                        queue_data = queue_map[username]
                        
                    if queue_data:
                        queue_rate = queue_data.get('rate', "0/0")
                        logger.debug(f"User {username} Queue Rate: {queue_rate}")
                        # Parse Rate
                        try:
                            rate_parts = queue_rate.split('/')
                            if len(rate_parts) == 2:
                                # MikroTik rate: rx/tx (upload/download from router perspective = user up/down?)
                                # Verify direction: 24624/1755768 (24k/1.7M). User is downloading.
                                # So 1.7M is TX from Router -> User (Download).
                                # 24k is RX to Router <- User (Upload).
                                # Correct.
                                real_up_mbps = int(rate_parts[0]) / 1000000.0
                                real_down_mbps = int(rate_parts[1]) / 1000000.0
                        except:
                            pass


                    try:
                        bytes_in = int(session.get('bytes-in', 0))
                        bytes_out = int(session.get('bytes-out', 0))
                    except:
                        continue
                        
                    session_id = session.get('.id', '')
                    mac = session.get('mac-address', '')
                    ip = session.get('address', '')
                    uptime_str = session.get('uptime', '')
                    
                    uptime_seconds = parse_mikrotik_uptime(uptime_str)
                    
                    update_usage_record(
                        username, bytes_in, bytes_out, mac, ip, session_id, 'hotspot', 
                        uptime_seconds=uptime_seconds,
                        real_up_mbps=real_up_mbps,
                        real_down_mbps=real_down_mbps
                    )
            except Exception as e:
                logger.error(f"Error fetching hotspot stats from {router.name}: {e}")

            # 2. Fetch PPPoE Active Connections (via Interfaces)
            try:
                interfaces = api.get_resource('/interface').get()
                pppoe_interfaces = [i for i in interfaces if i.get('type') == 'pppoe-in']
                
                if pppoe_interfaces:
                    logger.info(f"Router {router.name}: Found {len(pppoe_interfaces)} active PPPoE sessions.")

                for iface in pppoe_interfaces:
                    username = iface.get('name')
                    try:
                        bytes_in = int(iface.get('rx-byte', 0))
                        bytes_out = int(iface.get('tx-byte', 0))
                    except:
                        continue
                        
                    session_id = iface.get('.id', '')
                    ip = '' 
                    
                    update_usage_record(username, bytes_in, bytes_out, '', ip, session_id, 'pppoe', 0)

            except Exception as e:
                logger.error(f"Error fetching PPPoE stats from {router.name}: {e}")

            # 3. Sync Active Sessions to DB
            # We collected 'hotspot_active' and 'pppoe_interfaces'
            # Let's update the ActiveSession table
            
            # Get list of current session IDs to track stale ones
            current_session_ids = []
            
            from apps.network.models import ActiveSession
            from apps.customers.models import Customer
            
            # HOTSPOT SESSIONS
            for session in hotspot_active: # We fetched this earlier
                 username = session.get('user')
                 ip = session.get('address')
                 mac = session.get('mac-address')
                 session_id = session.get('.id')
                 uptime_str = session.get('uptime')
                 bytes_in = int(session.get('bytes-in', 0))
                 bytes_out = int(session.get('bytes-out', 0))
                 
                 customer = Customer.objects.filter(username=username).first()
                 if customer:
                     obj, created = ActiveSession.objects.update_or_create(
                         router=router,
                         session_id=session_id,
                         defaults={
                             'customer': customer,
                             'username': username,
                             'session_type': 'hotspot',
                             'ip_address': ip,
                             'mac_address': mac,
                             'upload_bytes': bytes_in, # In from Client = Upload
                             'download_bytes': bytes_out, # Out to Client = Download
                             'uptime_seconds': parse_mikrotik_uptime(uptime_str),
                             'start_time': timezone.now() # Approximate if created, or keep existing?
                             # ideally start_time should be calculated from uptime but we can accept now() for new
                         }
                     )
                     if not created:
                         # Don't overwrite start_time on update
                         pass
                     current_session_ids.append(session_id)

            # PPPoE SESSIONS
            # Re-fetch or use cached 'pppoe_interfaces'
            # Note: PPPoE interfaces ID is internal ID, but session ID usually refers to the PPP Active ID.
            # Let's fetch /ppp/active for better session data than /interface
            try:
                ppp_active = api.get_resource('/ppp/active').get()
                for session in ppp_active:
                    username = session.get('name')
                    ip = session.get('address')
                    mac = session.get('caller-id') # MAC
                    session_id = session.get('.id')
                    uptime_str = session.get('uptime')
                    # Stats are usually on the dynamic interface
                    # We might need to match via name if stats not in /ppp/active
                    # But verifying presence is enough for Active list. 
                    # For stats we can try to find interface with name <username> but sometimes it differs.
                    
                    customer = Customer.objects.filter(username=username).first()
                    if customer:
                         obj, created = ActiveSession.objects.update_or_create(
                             router=router,
                             session_id=session_id,
                             defaults={
                                 'customer': customer,
                                 'username': username,
                                 'session_type': 'pppoe',
                                 'ip_address': ip,
                                 'mac_address': mac,
                                 # We might miss byte counters here if not in ppp/active
                                 # checking if we can get them from interface list
                                 'uptime_seconds': parse_mikrotik_uptime(uptime_str),
                                 'start_time': timezone.now()
                             }
                         )
                         current_session_ids.append(session_id)
            except Exception as e:
                logger.error(f"Error fetching PPP active: {e}")

            # CLEANUP STALE SESSIONS
            # Delete sessions for this router that are NOT in current_session_ids
            stale_count, _ = ActiveSession.objects.filter(router=router).exclude(session_id__in=current_session_ids).delete()
            if stale_count > 0:
                logger.info(f"Router {router.name}: Removed {stale_count} stale sessions.")

            conn.disconnect()
            
        except Exception as e:
            logger.error(f"Failed to collect usage stats from router {router.name}: {e}")
            
    logger.info("Usage statistics collection completed.")

def update_usage_record(username, upload, download, mac, ip, session_id, service_type, uptime_seconds=0, real_up_mbps=None, real_down_mbps=None):
    try:
        from apps.customers.models import Customer
        from django.utils import timezone
        from django.utils import timezone
        
        # 1. Find Customer
        customer = Customer.objects.filter(username=username).first()
        if not customer:
            logger.debug(f"Usage Update: Customer '{username}' not found.")
            return

        # 2. Find Active Subscription
        subscription = Subscription.objects.filter(
            customer=customer, 
            status='active'
        ).last()
        
        if not subscription:
            logger.debug(f"Usage Update: No active subscription for '{username}'.")
            return

        # ... (rest of logic) ...
        
        latest_record = UsageRecord.objects.filter(
            customer=customer,
            subscription=subscription
        ).order_by('-created_at').first()
        
        create_new = False
        if not latest_record:
            create_new = True
            logger.info(f"Usage Update: Creating FIRST record for {username}")
        else:
            # Check if counters reset (new session)
            prev_total = latest_record.upload_bytes + latest_record.download_bytes
            curr_total = upload + download
            
            if curr_total < prev_total:
                create_new = True
                logger.info(f"Usage Update: Session reset detected for {username}. Creating NEW record.")
            
        if create_new:
            UsageRecord.objects.create(
                customer=customer,
                subscription=subscription,
                upload_bytes=upload,
                download_bytes=download,
                session_time_seconds=uptime_seconds,
                start_time=timezone.now(),
                nas_ip_address='',
                framed_ip_address=ip,
                session_id=session_id,
                upload_speed_mbps=real_up_mbps if real_up_mbps is not None else 0.0,
                download_speed_mbps=real_down_mbps if real_down_mbps is not None else 0.0
            )
            logger.info(f"Created UsageRecord for {username} (Up: {upload}, Down: {download})")
        else:
            # Calculate Speed Dynamically OR Use Realtime
            if real_up_mbps is not None and real_down_mbps is not None:
                # Use provided realtime speed (Better accuracy)
                up_speed_mbps = real_up_mbps
                down_speed_mbps = real_down_mbps
            else:
                # Fallback to Delta Calculation
                now = timezone.now()
                # ...
                
                delta_up_bytes = max(0, upload - latest_record.upload_bytes)
                delta_down_bytes = max(0, download - latest_record.download_bytes)
                
                # Calculate time difference
                if latest_record.updated_at:
                    time_delta = (now - latest_record.updated_at).total_seconds()
                else:
                    time_delta = 1.0 # Fallback
                
                # Prevent division by zero or extremely small delta
                if time_delta < 0.1: time_delta = 1.0
                
                up_speed_mbps = (delta_up_bytes * 8) / (time_delta * 1000000)
                down_speed_mbps = (delta_down_bytes * 8) / (time_delta * 1000000)
            
            latest_record.upload_bytes = upload
            latest_record.download_bytes = download
            # Update framed IP if it changed/appeared
            if ip: latest_record.framed_ip_address = ip
            if uptime_seconds > 0: latest_record.session_time_seconds = uptime_seconds
            
            latest_record.upload_speed_mbps = round(up_speed_mbps, 2)
            latest_record.download_speed_mbps = round(down_speed_mbps, 2)
            
            latest_record.save()
            logger.info(f"Updated UsageRecord for {username} (Speed: {down_speed_mbps:.2f} Mbps)")
            
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


