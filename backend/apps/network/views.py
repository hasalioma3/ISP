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

class RouterViewSet(viewsets.ModelViewSet):
    """
    Manage routers
    """
    queryset = Router.objects.all()
    serializer_class = RouterSerializer
    permission_classes = [IsAdminUser]

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
