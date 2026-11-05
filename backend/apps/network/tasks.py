
import ipaddress
from celery import shared_task
from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone
from apps.network.services.network_automation import network_automation
from apps.network.services.mikrotik_service import MikroTikService, parse_duration_seconds as parse_uptime_seconds
from apps.billing.models import UsageRecord, Subscription
import logging

logger = logging.getLogger('apps.network')


@shared_task
def collect_usage_statistics():
    """
    Poll usage, then enforce data caps and FUP immediately on the fresh
    totals. Overlapping runs are skipped so a slow router can't double-count.
    """
    lock = None
    try:
        import redis
        lock = redis.from_url(settings.CELERY_BROKER_URL).lock('collect-usage-statistics', timeout=120)
        if not lock.acquire(blocking=False):
            logger.info("Usage collection already running; skipping this tick.")
            return
    except Exception as e:
        logger.warning(f"Usage collection lock unavailable ({e}); running unlocked.")
        lock = None

    try:
        _collect_usage_once()
        enforce_subscription_data_limits()
        enforce_subscription_fup()
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass


def _collect_usage_once():
    """
    Collect live usage statistics (bytes in/out) from every active router's
    connected Hotspot + PPPoE sessions, and refresh the ActiveSession table
    (used for online-user counts on the admin dashboard).
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

        sessions = res['sessions']
        static_targets = _static_targets_for_router(router)
        if static_targets:
            static_res = mikrotik.get_static_sessions(static_targets)
            if static_res.get('success'):
                sessions = sessions + static_res['sessions']
            else:
                logger.error(f"Static session read failed for router {router.name}: {static_res.get('error')}")

        seen_session_ids = []
        for session in sessions:
            session_id = session.get('session_id')
            upload_raw = session['upload_bytes']
            download_raw = session['download_bytes']

            if session['service_type'] == 'static':
                delta_up, delta_down = _static_queue_delta(router, session['username'], upload_raw, download_raw)
            else:
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
            # Static usage is recorded above regardless, but the customer is
            # only listed online on live evidence (see get_static_sessions)
            # or traffic since the last poll.
            if session['service_type'] == 'static' and not (
                session.get('online') or delta_up > 0 or delta_down > 0
            ):
                continue
            seen_session_ids.append(session_id)
            customer = _find_customer(session['username'], session['mac_address'])
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

    # A roaming device can still hold a stale session on the router it left.
    # Keep the most recent one (lowest uptime) and drop the rest.
    newest = {}
    for sess in ActiveSession.objects.select_related('router').filter(session_type='hotspot'):
        key = (sess.customer_id, (sess.mac_address or '').upper())
        cur = newest.get(key)
        if cur is None or sess.uptime_seconds < cur.uptime_seconds:
            newest[key] = sess
    keep_ids = {v.id for v in newest.values()}
    for sess in ActiveSession.objects.select_related('router').filter(session_type='hotspot').exclude(id__in=keep_ids):
        try:
            r = sess.router
            ms = MikroTikService(host=r.ip_address, username=r.username,
                                 password=r.password, port=r.port, use_ssl=r.use_ssl)
            ms.disconnect_hotspot_session(sess.username)
        except Exception as e:
            logger.warning(f"Could not drop stale session {sess.username} on {sess.router.name}: {e}")
        sess.delete()

    logger.info(f"Usage statistics collection completed. {total_updated} sessions updated.")


@shared_task
def enforce_subscription_data_limits():
    """Expire capped subscriptions once combined upload and download reach the limit."""
    capped_subscriptions = Subscription.objects.filter(
        status='active',
        expiry_date__gt=timezone.now(),
        plan__data_limit_gb__isnull=False,
    ).select_related('customer', 'plan')

    expired_count = 0
    for subscription in capped_subscriptions:
        usage = UsageRecord.objects.filter(subscription=subscription).aggregate(
            upload=Sum('upload_bytes'),
            download=Sum('download_bytes'),
        )
        used_bytes = (usage['upload'] or 0) + (usage['download'] or 0)
        limit_bytes = int(subscription.plan.data_limit_gb * (1024 ** 3))

        if used_bytes >= limit_bytes:
            subscription.status = 'expired'
            subscription.save(update_fields=['status', 'updated_at'])
            expired_count += 1
            logger.info(
                "Expired subscription %s for %s after reaching its %s GB data limit",
                subscription.id,
                subscription.customer.username,
                subscription.plan.data_limit_gb,
            )

    return expired_count


@shared_task
def enforce_subscription_fup():
    """Apply reduced speeds after an active subscription reaches its FUP threshold."""
    subscriptions = Subscription.objects.filter(
        status='active',
        expiry_date__gt=timezone.now(),
        fup_applied=False,
        plan__fup_limit_gb__isnull=False,
    ).select_related('customer', 'plan')

    applied_count = 0
    for subscription in subscriptions:
        usage = UsageRecord.objects.filter(subscription=subscription).aggregate(
            upload=Sum('upload_bytes'),
            download=Sum('download_bytes'),
        )
        used_bytes = (usage['upload'] or 0) + (usage['download'] or 0)
        limit_bytes = subscription.plan.fup_limit_gb * (1024 ** 3)
        if used_bytes < limit_bytes:
            continue

        result = network_automation.apply_customer_fup(subscription.customer, subscription.plan)
        if not result.get('success'):
            logger.error(
                "Failed to apply FUP for subscription %s: %s",
                subscription.id,
                result.get('error'),
            )
            continue

        updated = Subscription.objects.filter(
            pk=subscription.pk,
            status='active',
            fup_applied=False,
        ).update(fup_applied=True, updated_at=timezone.now())
        applied_count += updated
        if updated:
            logger.info(
                "Applied FUP to subscription %s for %s at %s GB",
                subscription.id,
                subscription.customer.username,
                subscription.plan.fup_limit_gb,
            )

    return applied_count

def _static_targets_for_router(router):
    """Active static customers whose plan is served by this router."""
    targets = []
    subscriptions = Subscription.objects.filter(
        status='active', expiry_date__gt=timezone.now(),
        plan__service_type='static', customer__service_type='static',
        customer__static_ip_address__isnull=False,
    ).select_related('customer', 'plan')
    for subscription in subscriptions:
        plan_routers = subscription.plan.routers.filter(is_active=True)
        if plan_routers.exists() and not plan_routers.filter(pk=router.pk).exists():
            continue
        targets.append({
            'username': subscription.customer.username,
            'ip': str(subscription.customer.static_ip_address),
        })
    return targets


def _static_queue_delta(router, username, upload_raw, download_raw):
    """
    Bytes a static customer's simple queue moved since the last poll. Queue
    counters are cumulative and survive the device going offline, so the
    baseline is kept in StaticQueueCounter rather than ActiveSession. A
    counter that went backwards (router reboot, queue re-created) restarted
    from 0, so its raw value is all new. With no baseline yet, the current
    value becomes one -- falling back to the ActiveSession left from before
    StaticQueueCounter existed, so the upgrade doesn't re-count lifetime
    totals already recorded.
    """
    from apps.network.models import ActiveSession, StaticQueueCounter

    counter = StaticQueueCounter.objects.filter(router=router, username=username).first()
    if counter is None:
        legacy = ActiveSession.objects.filter(router=router, session_id=f"static-{username}").first()
        prev_up = legacy.upload_bytes if legacy else upload_raw
        prev_down = legacy.download_bytes if legacy else download_raw
    else:
        prev_up, prev_down = counter.upload_bytes, counter.download_bytes

    delta_up = upload_raw - prev_up if upload_raw >= prev_up else upload_raw
    delta_down = download_raw - prev_down if download_raw >= prev_down else download_raw
    StaticQueueCounter.objects.update_or_create(
        router=router, username=username,
        defaults={'upload_bytes': upload_raw, 'download_bytes': download_raw},
    )
    return delta_up, delta_down


def _find_customer(username, mac=None):
    """Roaming MAC-login sessions use the MAC as username, so fall back to it."""
    from apps.customers.models import Customer
    customer = Customer.objects.filter(username=username).first()
    if customer:
        return customer

    # Several customers can share one MAC (old voucher/guest accounts); the one
    # with a live subscription must win or its usage is never recorded.
    macs = [m for m in (mac, username if username and ':' in username else None) if m]
    for candidate_mac in macs:
        matches = Customer.objects.filter(hotspot_mac_address__iexact=candidate_mac)
        active = matches.filter(
            subscriptions__status='active', subscriptions__expiry_date__gt=timezone.now()
        ).order_by('-subscriptions__created_at').first()
        customer = active or matches.first()
        if customer:
            return customer
    return None

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
        customer = _find_customer(username, mac)

        if not customer:
            logger.warning(f"Usage collection: Customer not found for {username}")
            return False

        # Newest first (Meta ordering is -created_at), so a just-lapsed row
        # still awaiting check_expired_subscriptions can't steal the usage.
        subscription = Subscription.objects.filter(
            customer=customer,
            status='active'
        ).first()

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
        from apps.network.models import Router
        plan = BillingPlan.objects.get(id=plan_id)

        # Same fallback as network_automation.activate_customer: a plan with
        # no routers explicitly assigned applies to every active router, not
        # zero. Without this, a plan created/left with routers blank (the
        # UI's own "blank = all active routers" default) never got its
        # profile pushed anywhere -- so any customer activated on it failed,
        # since activate_customer WAS using this same "all active routers"
        # fallback for activation, just not for this sync.
        target_routers = plan.routers.filter(is_active=True)
        # Hotspot plans must exist on every router so a customer can roam.
        if plan.service_type in ['hotspot', 'both'] or not target_routers.exists():
            target_routers = Router.objects.filter(is_active=True)

        logger.info(f"Syncing plan {plan.name} to {target_routers.count()} routers...")

        for router in target_routers:
            try:
                mikrotik = MikroTikService(
                    host=router.ip_address,
                    username=router.username,
                    password=router.password,
                    port=router.port,
                    use_ssl=router.use_ssl
                )

                # Same gateway this router was provisioned with (see
                # provision_router) -- without it, a plan-specific PPPoE
                # profile has no local-address/remote-address of its own, so
                # a customer on it never actually draws an IP from the
                # PPPoE pool.
                pppoe_gateway = None
                try:
                    pppoe_net = ipaddress.ip_network(router.pppoe_subnet, strict=False)
                    pppoe_gateway = str(pppoe_net[1])
                except ValueError:
                    logger.error(f"{router.name}: invalid pppoe_subnet {router.pppoe_subnet!r}, leaving PPPoE profile's local-address unset")
                
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
                    if plan.fup_limit_gb is not None:
                        fup_rate_limit = f"{plan.fup_upload_speed}M/{plan.fup_download_speed}M"
                        fup_profile = plan.get_fup_mikrotik_profile()
                        fup_hotspot = mikrotik.add_hotspot_profile(fup_profile, fup_rate_limit)
                        if not fup_hotspot['success']:
                            fup_hotspot = mikrotik.update_hotspot_profile(fup_profile, fup_rate_limit)
                        if not fup_hotspot['success']:
                            logger.error(f"{router.name}: Hotspot FUP profile sync failed: {fup_hotspot.get('error')}")
                    refreshed = mikrotik.refresh_hotspot_sessions()
                    if refreshed.get('refreshed'):
                        logger.info(f"{router.name}: reconnected sessions to apply new speed: {refreshed['refreshed']}")
                else:
                    res_hotspot = {'success': True} # Skip if not hotspot plan
                
                # Create/Update PPPoE Profile
                if plan.service_type in ['pppoe', 'both']:
                    rate_limit = f"{plan.upload_speed}M/{plan.download_speed}M"
                    # PPPoE auto-bypass logic: when a PPPoE user connects, add
                    # them to the Hotspot IP binding as bypassed (so they
                    # don't also get hit by the hotspot walled garden/login),
                    # and remove that binding again when they disconnect.
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
                        remote_address='pppoe_pool',
                        local_address=pppoe_gateway,
                        on_up=on_up,
                        on_down=on_down
                    )

                    logger.info(f"Add PPPoE Profile Response: {res_pppoe}")

                    if not res_pppoe['success']:
                        # Try update if add failed (likely exists)
                        res_pppoe = mikrotik.update_pppoe_profile(
                            name=plan.mikrotik_profile,
                            rate_limit=rate_limit,
                            remote_address='pppoe_pool',
                            local_address=pppoe_gateway,
                            on_up=on_up,
                            on_down=on_down
                        )

                    if res_pppoe['success']:
                        logger.info(f"{router.name}: PPPoE Profile {plan.mikrotik_profile} synced.")
                    else:
                        logger.error(f"{router.name}: PPPoE Sync Failed: {res_pppoe.get('error')}")
                    if plan.fup_limit_gb is not None:
                        fup_profile = plan.get_fup_mikrotik_profile()
                        fup_rate_limit = f"{plan.fup_upload_speed}M/{plan.fup_download_speed}M"
                        fup_pppoe = mikrotik.add_pppoe_profile(
                            name=fup_profile,
                            rate_limit=fup_rate_limit,
                            remote_address='pppoe_pool',
                            local_address=pppoe_gateway,
                            on_up=on_up,
                            on_down=on_down,
                        )
                        if not fup_pppoe['success']:
                            fup_pppoe = mikrotik.update_pppoe_profile(
                                name=fup_profile,
                                rate_limit=fup_rate_limit,
                                remote_address='pppoe_pool',
                                local_address=pppoe_gateway,
                                on_up=on_up,
                                on_down=on_down,
                            )
                        if not fup_pppoe['success']:
                            logger.error(f"{router.name}: PPPoE FUP profile sync failed: {fup_pppoe.get('error')}")
                else:
                    res_pppoe = {'success': True}  # Skip if not a PPPoE plan

                # Static plans have no router profile; each customer has their own queue.
                if plan.service_type == 'static':
                    static = network_automation.sync_static_plan(plan, router, mikrotik)
                    for err in static['failed']:
                        logger.error(f"{router.name}: Static sync failed: {err}")
                    logger.info(f"{router.name}: Static plan {plan.name} queues synced: {static['success']}")

                if res_hotspot['success']:
                     logger.info(f"{router.name}: Hotspot Profile {plan.mikrotik_profile} synced.")
                else:
                     logger.error(f"{router.name}: Hotspot Sync Failed: {res_hotspot.get('error')}")

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

            from apps.notifications.tasks import send_suspension_notice
            send_suspension_notice.delay(sub.customer_id, sub.id)

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
