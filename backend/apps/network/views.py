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
        if self.action in ['list', 'retrieve', 'sync_profiles', 'sync_users', 'health']:
            return [RoleAllowed('admin', 'technician')()]
        return [RoleAllowed('admin')()]

    @action(detail=False, methods=['get'])
    def health(self, request):
        """
        Live CPU/RAM/disk + WAN traffic counters for every active router,
        for the admin dashboard's Router View card. Hits each router
        directly (not DB-cached, unlike the online-user counts) -- fine for
        a 10s poll across a handful of routers, not meant for hundreds.
        """
        results = {}
        routers = Router.objects.filter(is_active=True)
        router_param = request.query_params.get('router')
        if router_param:
            routers = routers.filter(id=router_param)
        for router in routers:
            mikrotik = MikroTikService(
                host=router.ip_address, username=router.username,
                password=router.password, port=router.port, use_ssl=router.use_ssl
            )
            results[router.id] = mikrotik.get_system_health()
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
    def enable_acs_provisioning(self, request, pk=None):
        """
        Broadcasts the TR-069 ACS URL via DHCP option 43 on this router's
        Hotspot network, so CPE devices that support zero-touch
        provisioning configure themselves automatically -- see
        NetworkAutomation.enable_acs_auto_provisioning for the scope/
        caveats (Hotspot network only, not every CPE device supports this).
        Explicit opt-in action, admin-only like provision/backup.
        """
        router = self.get_object()
        username = request.data.get('username')
        password = request.data.get('password')
        result = network_automation.enable_acs_auto_provisioning(router, username=username, password=password)
        if result.get('error'):
            return Response({'error': result['error']}, status=400)
        return Response({'success': [f"CPE auto-provisioning enabled (ACS URL: {result['acs_url']})"], 'failed': []})

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
        """Push all active subscriptions to this router as PPPoE secrets / Hotspot users."""
        router = self.get_object()
        result = network_automation.sync_all_users(router=router)
        if result.get('error'):
            return Response(result, status=400)
        return Response(result)


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
        if service_type in ('hotspot', 'pppoe'):
            sessions = sessions.filter(session_type=service_type)

        data = []
        for s in sessions:
            customer = s.customer
            subscription = Subscription.objects.filter(
                customer=customer, status='active'
            ).order_by('-created_at').first()
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
                'status': 'online',
                'last_seen': s.last_update,
                'upload_gb': round(s.upload_bytes / (1024 ** 3), 2),
                'download_gb': round(s.download_bytes / (1024 ** 3), 2),
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
