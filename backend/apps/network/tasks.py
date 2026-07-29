
import re
from celery import shared_task
from django.db.models import F
from django.utils import timezone
from apps.network.services.network_automation import network_automation
from apps.network.services.mikrotik_service import MikroTikService
from apps.billing.models import UsageRecord, Subscription
import logging

logger = logging.getLogger('apps.network')

UPTIME_RE = re.compile(r'(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?')


def parse_uptime_seconds(uptime):
    """Best-effort parse of RouterOS uptime strings like '1w2d3h4m5s'."""
    if not uptime:
        return 0
    m = UPTIME_RE.fullmatch(uptime)
    if not m:
        return 0
    w, d, h, mi, s = (int(g) if g else 0 for g in m.groups())
    return w * 604800 + d * 86400 + h * 3600 + mi * 60 + s


@shared_task
def collect_usage_statistics():
    """
    Collect live usage statistics (bytes in/out) from every active router's
    connected Hotspot + PPPoE sessions, and refresh the ActiveSession table
    (used for online-user counts on the admin dashboard). Scheduled
    periodically in celery.py.
    """
    from apps.customers.models import Customer
    from apps.network.models import Router, ActiveSession

    logger.info("Starting usage statistics collection...")
    total_updated = 0

    for router in Router.objects.filter(is_active=True):
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username,
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        res = mikrotik.get_active_sessions()
        if not res.get('success'):
            logger.error(f"Usage collection failed for router {router.name}: {res.get('error')}")
            continue

        seen_session_ids = []
        for session in res['sessions']:
            session_id = session.get('session_id')
            upload_raw = session['upload_bytes']
            download_raw = session['download_bytes']

            # Delta since the last poll of *this* session_id. RouterOS
            # resets byte counters to 0 on reconnect, which mints a new
            # session_id -- so a missing/reset previous row means the raw
            # counter itself is all-new usage, not that nothing happened.
            delta_up, delta_down = upload_raw, download_raw
            if session_id:
                prev = ActiveSession.objects.filter(router=router, session_id=session_id).first()
                if prev:
                    delta_up = upload_raw - prev.upload_bytes if upload_raw >= prev.upload_bytes else upload_raw
                    delta_down = download_raw - prev.download_bytes if download_raw >= prev.download_bytes else download_raw

            if update_usage_record(
                session['username'], delta_up, delta_down,
                session['mac_address'], session['address'], router.ip_address
            ):
                total_updated += 1

            if not session_id:
                continue
            seen_session_ids.append(session_id)
            customer = Customer.objects.filter(username=session['username']).first()
            if not customer:
                continue
            ActiveSession.objects.update_or_create(
                router=router, session_id=session_id,
                defaults={
                    'customer': customer,
                    'session_type': session['service_type'],
                    'username': session['username'],
                    'ip_address': session['address'] or '0.0.0.0',
                    'mac_address': session['mac_address'] or None,
                    'upload_bytes': upload_raw,
                    'download_bytes': download_raw,
                    'uptime_seconds': parse_uptime_seconds(session.get('uptime')),
                    'start_time': timezone.now() - timezone.timedelta(seconds=parse_uptime_seconds(session.get('uptime'))),
                }
            )

        # Sessions that ended since the last run are no longer in the live
        # list -- drop them so online-user counts stay accurate.
        ActiveSession.objects.filter(router=router).exclude(session_id__in=seen_session_ids).delete()

    logger.info(f"Usage statistics collection completed. {total_updated} sessions updated.")

def update_usage_record(username, delta_upload, delta_download, mac, ip, router_ip=''):
    """
    Add this poll's byte delta onto today's UsageRecord for a customer, so
    usage persists across disconnect/reconnect instead of being overwritten
    by the new session's reset-to-zero counters. Returns True if a record
    was created/updated, False otherwise.
    """
    if delta_upload <= 0 and delta_download <= 0:
        return False

    try:
        from apps.customers.models import Customer
        customer = Customer.objects.filter(username=username).first()

        if not customer:
            logger.warning(f"Usage collection: Customer not found for {username}")
            return False

        subscription = Subscription.objects.filter(
            customer=customer,
            status='active'
        ).last()

        if not subscription:
            return False

        # One accumulating record per customer per day per source IP.
        today = timezone.now().date()

        usage_record = UsageRecord.objects.filter(
            customer=customer,
            subscription=subscription,
            created_at__date=today,
            framed_ip_address=ip
        ).first()

        if usage_record:
            UsageRecord.objects.filter(pk=usage_record.pk).update(
                upload_bytes=F('upload_bytes') + delta_upload,
                download_bytes=F('download_bytes') + delta_download,
            )
        else:
            UsageRecord.objects.create(
                customer=customer,
                subscription=subscription,
                upload_bytes=delta_upload,
                download_bytes=delta_download,
                session_time_seconds=0,
                start_time=timezone.now(),
                nas_ip_address=router_ip or None,
                framed_ip_address=ip or None
            )
        return True

    except Exception as e:
        logger.error(f"Error updating usage for {username}: {e}")
        return False

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
