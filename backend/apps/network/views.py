from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from apps.network.services.network_automation import network_automation

from rest_framework_simplejwt.authentication import JWTAuthentication

from rest_framework import viewsets
from apps.network.models import Router
from apps.network.serializers.router import RouterSerializer

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
        profile, PPPoE server, walled garden, and existing plan profiles.
        """
        router = self.get_object()
        result = network_automation.provision_router(router)
        if result.get('error'):
            return Response(result, status=400)
        return Response(result)

    @action(detail=True, methods=['post'])
    def backup(self, request, pk=None):
        """
        Read-only snapshot of the resources provisioning would touch, without
        writing anything. Useful before a provisioning run, or on its own.
        """
        router = self.get_object()
        result = network_automation.snapshot_router(router)
        if not result.get('success'):
            return Response({'error': result.get('error')}, status=400)
        return Response({'snapshot': result['snapshot'], 'snapshot_at': router.pre_provision_snapshot_at})

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
