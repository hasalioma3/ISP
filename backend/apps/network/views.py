import re

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from apps.network.services.network_automation import network_automation

from rest_framework_simplejwt.authentication import JWTAuthentication

from rest_framework import viewsets
from apps.network.models import Router
from apps.network.serializers.router import RouterSerializer
from apps.network.services.mikrotik_service import MikroTikService
from apps.customers.permissions import RoleAllowed

class RouterViewSet(viewsets.ModelViewSet):
    """
    Manage routers. Technicians can view routers and run the two sync
    actions (pushing existing plans/subscriptions to a router), but can't
    add, edit, delete, provision, or back up a router -- those change what
    the router actually is, which stays admin-only.
    """
    queryset = Router.objects.all()
    serializer_class = RouterSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'sync_profiles', 'sync_users', 'sync_users_status', 'health']:
            return [RoleAllowed('admin', 'technician')()]
        return [RoleAllowed('admin')()]

    @action(detail=False, methods=['get'])
    def health(self, request):
        """
        Live CPU/RAM/disk + WAN traffic counters for every active router,
        for the admin dashboard's Router View card and Network Ops' live
        graph. Reachable routers are read live (the WAN counters are diffed
        between polls, so they must be fresh). A router already known to be
        offline is answered from its stored state without being contacted:
        before this, every 10s dashboard poll waited out the connect timeout
        on each offline router and the portal hung. The usage poll keeps
        re-checking offline routers, so they come back by themselves.
        Live reads run in parallel so one slow router doesn't delay the rest.
        """
        from concurrent.futures import ThreadPoolExecutor
        from apps.network.services import router_status

        routers = list(Router.objects.filter(is_active=True))
        router_param = request.query_params.get('router')
        if router_param:
            routers = [r for r in routers if str(r.id) == router_param]

        results = {}
        live = []
        for router in routers:
            if router_status.known_offline(router):
                results[router.id] = router_status.cached_health(router)
            else:
                live.append(router)

        def read(router):
            return MikroTikService(
                host=router.ip_address, username=router.username,
                password=router.password, port=router.port, use_ssl=router.use_ssl
            ).get_system_health()

        if live:
            with ThreadPoolExecutor(max_workers=min(len(live), 8)) as pool:
                healths = list(pool.map(read, live))
            # DB writes stay on this thread (Django connections are per-thread).
            for router, health in zip(live, healths):
                if health.get('success'):
                    router_status.mark_online(router, health)
                    results[router.id] = {**health, 'online': True}
                else:
                    router_status.mark_offline(router, health.get('error'))
                    results[router.id] = router_status.cached_health(router)
        return Response(results)

    @action(detail=True, methods=['post'])
    def provision(self, request, pk=None):
        """
        Full bootstrap of a router: IP pools, DHCP, NAT, Hotspot server +
        profile, PPPoE server, Hotspot login page, walled garden, and
        existing plan profiles.

        Requires username/password in the request body -- provisioning
        writes real config to the router, so credentials must be supplied
        fresh each time rather than trusting possibly-stale stored ones.
        On success, the supplied credentials (and portal_url, if given) are
        saved to the router.
        """
        router = self.get_object()
        username = request.data.get('username')
        password = request.data.get('password')
        portal_url = request.data.get('portal_url')
        if not username or not password:
            return Response({'error': 'Router username and password are required to provision.'}, status=400)
        result = network_automation.provision_router(router, username=username, password=password, portal_url=portal_url)
        if result.get('error'):
            return Response(result, status=400)
        return Response(result)

    @action(detail=True, methods=['post'])
    def sync_hotspot_login_page(self, request, pk=None):
        """Refreshes only the custom Hotspot login page, without reprovisioning the router."""
        router = self.get_object()
        result = network_automation.sync_hotspot_login_page(router)
        if result.get('error'):
            return Response({'error': result['error']}, status=400)
        return Response({
            'success': [f"Hotspot login page synced to {result['path']} (profile directory: {result['html_directory']})"],
            'failed': [],
        })

    @action(detail=True, methods=['post'])
    def backup(self, request, pk=None):
        """
        Read-only snapshot of the resources provisioning would touch, without
        writing anything. Useful before a provisioning run, or on its own.
        Accepts optional username/password to override stored credentials.
        """
        router = self.get_object()
        username = request.data.get('username')
        password = request.data.get('password')
        result = network_automation.snapshot_router(router, username=username, password=password)
        if not result.get('success'):
            return Response({'error': result.get('error')}, status=400)
        return Response({'snapshot': result['snapshot'], 'snapshot_at': router.pre_provision_snapshot_at})

    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """Reboots the router. Admin-only; clients on it lose connectivity briefly."""
        router = self.get_object()
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username,
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        result = mikrotik.reboot()
        if not result.get('success'):
            return Response({'error': result.get('error')}, status=400)
        return Response({'success': ['Restart command sent -- the router will be offline for a minute or two'], 'failed': []})

    @action(detail=True, methods=['get', 'post'])
    def maintenance_schedule(self, request, pk=None):
        """
        GET: current scheduled backup/update settings read from the router.
        POST: {backup: {frequency, time}, update: {frequency, time}} -- frequency
        is off/daily/weekly/monthly, time is HH:MM (router clock).
        """
        router = self.get_object()
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username,
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        if request.method == 'GET':
            result = mikrotik.get_maintenance_schedules()
            if not result.get('success'):
                return Response({'error': result.get('error')}, status=400)
            return Response({'schedules': result['schedules']})

        applied = []
        for task in ('backup', 'update'):
            cfg = request.data.get(task)
            if cfg is None:
                continue
            frequency = cfg.get('frequency')
            time_of_day = cfg.get('time') or ''
            if frequency != 'off' and frequency not in MikroTikService.MAINTENANCE_INTERVALS:
                return Response({'error': f'Invalid {task} frequency'}, status=400)
            if frequency != 'off' and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', time_of_day):
                return Response({'error': f'{task} time must be HH:MM'}, status=400)
            result = mikrotik.set_maintenance_schedule(task, frequency, time_of_day)
            if not result.get('success'):
                return Response({'error': result.get('error')}, status=400)
            applied.append(f"{task}: {'disabled' if frequency == 'off' else f'{frequency} at {time_of_day}'}")
        return Response({'success': [f'Scheduled {a}' for a in applied], 'failed': []})

    @action(detail=True, methods=['post'])
    def enable_wan_access(self, request, pk=None):
        """
        Opens Winbox + SSH on this router's WAN interface, scoped to
        whatever subnet it's currently addressed on (the upstream network
        that gives it internet) -- RouterOS blocks management access from
        WAN by default. Admin-only, like provision/backup: this is a
        firewall change, not read-only.
        """
        router = self.get_object()
        username = request.data.get('username')
        password = request.data.get('password')
        result = network_automation.enable_wan_management_access(router, username=username, password=password)
        if result.get('error'):
            return Response({'error': result['error']}, status=400)
        scopes = ', '.join([result['subnet']] + result.get('extra_subnets', []))
        return Response({
            'success': [f"WAN management access enabled, scoped to {scopes}"] + [f"Check: {c}" for c in result.get('checks', [])],
            'failed': [],
        })

    @action(detail=True, methods=['post'])
    def disable_wan_access(self, request, pk=None):
        """Removes exactly the rules enable_wan_access added."""
        router = self.get_object()
        username = request.data.get('username')
        password = request.data.get('password')
        result = network_automation.disable_wan_management_access(router, username=username, password=password)
        if result.get('error'):
            return Response({'error': result['error']}, status=400)
        return Response({'success': [f"WAN management access disabled ({result['removed_count']} rule(s) removed)"], 'failed': []})

    @action(detail=True, methods=['post'])
    def enable_mgmt_vlan(self, request, pk=None):
        """
        Separate management network for radios/APs (see
        NetworkAutomation.enable_management_vlan). Admin-only: it adds a
        VLAN, DHCP server, NAT and firewall rules to the router.
        """
        router = self.get_object()
        result = network_automation.enable_management_vlan(
            router, username=request.data.get('username'), password=request.data.get('password')
        )
        if result.get('error'):
            return Response({'error': result['error']}, status=400)
        plan = result['plan']
        return Response({
            'success': [f"Radio management VLAN {'updated' if plan['reused'] else 'enabled'}: "
                        f"VLAN {plan['vlan_id']}, subnet {plan['subnet']}"]
                       + [f"Done: {line}" for line in result['report']]
                       + [f"Next: on each radio set Management VLAN = {plan['vlan_id']} with DHCP (bridge mode)",
                          f"Next: on your LAN router, add a static route {plan['subnet']} via {plan['wan_ip']}"],
            'failed': [],
        })

    @action(detail=True, methods=['post'])
    def disable_mgmt_vlan(self, request, pk=None):
        """Removes exactly what enable_mgmt_vlan added."""
        router = self.get_object()
        result = network_automation.disable_management_vlan(
            router, username=request.data.get('username'), password=request.data.get('password')
        )
        if result.get('error'):
            return Response({'error': result['error']}, status=400)
        return Response({'success': [f"Radio management VLAN removed ({result['removed_count']} item(s))"], 'failed': []})

    @action(detail=False, methods=['post'])
    def test_connection(self, request):
        """
        Read-only connectivity check against a router's IP/credentials,
        without requiring it to be saved first. Returns real interface
        names so the correct MIKROTIK_PROVISION_INTERFACE value can be
        confirmed before provisioning is ever attempted.
        """
        ip_address = request.data.get('ip_address')
        username = request.data.get('username')
        password = request.data.get('password')
        port = request.data.get('port') or 8728
        use_ssl = request.data.get('use_ssl', False)
        if not ip_address or not username or not password:
            return Response({'error': 'ip_address, username and password are required.'}, status=400)
        mikrotik = MikroTikService(host=ip_address, username=username, password=password, port=port, use_ssl=use_ssl)
        result = mikrotik.list_interfaces()
        if not result.get('success'):
            return Response({'error': result.get('error')}, status=400)
        return Response({'interfaces': result['interfaces']})

    @action(detail=True, methods=['post'])
    def sync_profiles(self, request, pk=None):
        """Push all active Billing Plans to this router as PPPoE/Hotspot profiles."""
        router = self.get_object()
        result = network_automation.sync_all_profiles(router=router)
        if result.get('error'):
            return Response(result, status=400)
        return Response(result)

    @action(detail=True, methods=['post'])
    def sync_users(self, request, pk=None):
        """
        Push all active subscriptions to this router as PPPoE secrets /
        Hotspot users / static queues -- in the background (see
        tasks.sync_router_users): with dozens of customers this outlasts
        the web request timeout. Poll sync_users_status for the result.
        """
        from datetime import timedelta
        from django.utils import timezone
        from django.utils.dateparse import parse_datetime
        from apps.network.tasks import sync_router_users

        router = self.get_object()
        current = router.last_user_sync or {}
        started = parse_datetime(current.get('started_at') or '')
        # A run that never reported back (worker restarted mid-sync) mustn't
        # block new runs forever.
        if current.get('status') == 'running' and started and timezone.now() - started < timedelta(minutes=15):
            return Response({'running': True, 'started_at': current['started_at']})

        state = {'status': 'running', 'started_at': timezone.now().isoformat()}
        Router.objects.filter(pk=router.pk).update(last_user_sync=state)
        try:
            sync_router_users.delay(router.pk)
        except Exception as e:
            Router.objects.filter(pk=router.pk).update(last_user_sync=None)
            return Response({'error': f'Could not start the sync -- is the Celery worker running? ({e})'}, status=503)
        return Response({'running': True, 'started_at': state['started_at']}, status=202)

    @action(detail=True, methods=['get'])
    def sync_users_status(self, request, pk=None):
        """Outcome of the last background Sync Users run (see sync_users)."""
        return Response(self.get_object().last_user_sync or {'status': 'none'})


class OnlineUsersView(APIView):
    """
    Currently connected Hotspot/PPPoE sessions (from the ActiveSession table
    kept fresh by the collect_usage_statistics celery task), joined with
    each customer's current plan/expiry/payment info for the admin
    Online Users page.
    """
    permission_classes = [RoleAllowed('admin', 'technician')]

    def get(self, request):
        from apps.network.models import ActiveSession
        from apps.billing.models import Subscription, Transaction

        service_type = request.query_params.get('type')
        sessions = ActiveSession.objects.select_related('customer', 'router').order_by('-start_time')
        if service_type in ('hotspot', 'pppoe', 'static'):
            sessions = sessions.filter(session_type=service_type)

        from django.db.models import Sum
        from apps.billing.models import UsageRecord

        sessions = list(sessions)
        customer_ids = {s.customer_id for s in sessions}
        active_subs = {}
        for sub in Subscription.objects.filter(customer_id__in=customer_ids, status='active').order_by('created_at'):
            active_subs[sub.customer_id] = sub  # latest active wins
        GB = 1024 ** 3

        def totals(qs, key):
            return {
                row[key]: ((row['up'] or 0) + (row['down'] or 0)) / GB
                for row in qs.values(key).annotate(up=Sum('upload_bytes'), down=Sum('download_bytes'))
            }
        # Two grouped queries for the whole page rather than two per row.
        all_time = totals(UsageRecord.objects.filter(customer_id__in=customer_ids), 'customer_id')
        period = totals(
            UsageRecord.objects.filter(subscription_id__in=[sub.id for sub in active_subs.values()]),
            'subscription_id',
        )

        data = []
        for s in sessions:
            customer = s.customer
            subscription = active_subs.get(customer.id)
            transaction = Transaction.objects.filter(
                customer=customer, status='completed'
            ).order_by('-created_at').first()

            method = '-'
            if transaction:
                if transaction.payment_method == 'mpesa':
                    method = f"M-Pesa - {transaction.mpesa_receipt_number or transaction.transaction_id}"
                elif transaction.payment_method == 'cash':
                    method = f"Manual - {transaction.notes[:30]}" if transaction.notes else 'Manual'
                else:
                    method = transaction.get_payment_method_display()

            data.append({
                'session_id': s.id,
                'customer_id': customer.id,
                'username': s.username,
                'plan_name': subscription.plan.name if subscription else '-',
                'type': s.session_type,
                'created_on': subscription.start_date if subscription else None,
                'expires_on': subscription.expiry_date if subscription else None,
                'method': method,
                'router': s.router.name,
                # The usage poll can't refresh (or drop) sessions on a router
                # it can't reach, so these are the last known sessions there.
                'router_online': s.router.is_online is not False,
                'status': 'online' if s.router.is_online is not False else 'router offline',
                'last_seen': s.last_update,
                'upload_gb': round(s.upload_bytes / (1024 ** 3), 2),
                'download_gb': round(s.download_bytes / (1024 ** 3), 2),
                # Recorded usage (UsageRecord): this plan period, and ever.
                'period_usage_gb': round(period.get(subscription.id, 0), 2) if subscription else None,
                'total_usage_gb': round(all_time.get(customer.id, 0), 2),
            })

        return Response(data)

    def post(self, request):
        """Manually trigger an immediate refresh against the live routers."""
        from apps.network.tasks import collect_usage_statistics
        collect_usage_statistics()
        return Response({'success': True})


class DisconnectSessionView(APIView):
    """Kick a currently-online user off the router (admin/technician only)."""
    permission_classes = [RoleAllowed('admin', 'technician')]

    def post(self, request, pk):
        from apps.network.models import ActiveSession

        try:
            session = ActiveSession.objects.select_related('router').get(pk=pk)
        except ActiveSession.DoesNotExist:
            return Response({'error': 'Session not found'}, status=404)

        router = session.router
        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username,
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        if session.session_type == 'static':
            return Response(
                {'error': 'Static IP customers have no login session to disconnect; suspend the customer instead.'},
                status=400,
            )
        if session.session_type == 'hotspot':
            result = mikrotik.disconnect_hotspot_session(session.username)
        else:
            result = mikrotik.disconnect_pppoe_session(session.username)

        if not result.get('success'):
            return Response({'error': result.get('error')}, status=400)

        session.delete()
        return Response({'success': True})


class MySessionView(APIView):
    """
    The logged-in customer's own live session, straight from the router
    (not the ActiveSession table, which is only refreshed every 5 minutes
    by the collect_usage_statistics celery task -- too stale for a
    dashboard widget that's meant to refresh every few seconds).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = request.user
        router = None
        if hasattr(customer, 'pppoe_secret'):
            router = customer.pppoe_secret.router
        elif hasattr(customer, 'hotspot_user'):
            router = customer.hotspot_user.router

        if not router:
            return Response({'active': False})

        # Don't make the customer's widget wait on a router we already know
        # is down (see router_status).
        from apps.network.services import router_status
        if router_status.known_offline(router):
            return Response({'active': False, 'router_offline': True})

        mikrotik = MikroTikService(
            host=router.ip_address, username=router.username,
            password=router.password, port=router.port, use_ssl=router.use_ssl
        )
        res = mikrotik.get_active_sessions()
        if not res.get('success'):
            return Response({'active': False, 'error': res.get('error')})

        usernames = {u for u in (customer.pppoe_username, customer.hotspot_username) if u}
        session = next((s for s in res['sessions'] if s['username'] in usernames), None)
        if not session:
            return Response({'active': False})

        return Response({'active': True, **session})
