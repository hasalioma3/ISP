from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from apps.network.services.network_automation import network_automation

from rest_framework_simplejwt.authentication import JWTAuthentication

from rest_framework import viewsets
from apps.network.models import Router
from apps.network.serializers.router import RouterSerializer

from rest_framework.decorators import action
from apps.network.models import RouterInterfaceStat
from django.db.models import Sum

class RouterViewSet(viewsets.ModelViewSet):
    """
    Manage routers
    """
    queryset = Router.objects.all()
    serializer_class = RouterSerializer
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'])
    def total_activity(self, request):
        """
        Get total real-time network activity (sum of all monitored interfaces)
        """
        # Sum all routers
        stats = RouterInterfaceStat.objects.aggregate(
            total_rx=Sum('rx_bps'),
            total_tx=Sum('tx_bps')
        )
        
        rx_bps = stats['total_rx'] or 0
        tx_bps = stats['total_tx'] or 0
        
        return Response({
            'upload_bps': rx_bps, # RX on router is Upload from client
            'download_bps': tx_bps, # TX on router is Download to client
            'upload_mbps': round(rx_bps / 1000000.0, 2),
            'download_mbps': round(tx_bps / 1000000.0, 2)
        })

    @action(detail=True, methods=['post'])
    def configure(self, request, pk=None):
        """
        Auto-configure MikroTik Router (Radius, Services)
        """
        router = self.get_object()
        from apps.network.services.mikrotik_service import MikroTikService
        from django.conf import settings
        
        mikrotik = MikroTikService(
            host=router.ip_address, 
            username=router.username, 
            password=router.password, 
            port=router.port, 
            use_ssl=router.use_ssl
        )
        
        results = {'steps': []}
        
        # 1. Configure Radius Client
        try:
            # Use RADIUS_SERVER from settings, or fallback to the server IP seen by router?
            # Ideally settings.RADIUS_SERVER should be the IP reachable by the router.
            res = mikrotik.configure_radius_client(
                address=settings.RADIUS_SERVER,
                secret=settings.RADIUS_SECRET
            )
            if res['success']:
                results['steps'].append({'name': 'Radius Client', 'status': 'success'})
            else:
                results['steps'].append({'name': 'Radius Client', 'status': 'failed', 'error': res.get('error')})
        except Exception as e:
            results['steps'].append({'name': 'Radius Client', 'status': 'failed', 'error': str(e)})

        # 2. Enable Radius for Hotspot/PPPoE
        try:
            res = mikrotik.enable_service_radius()
            if res['success']:
                results['steps'].append({'name': 'Service Radius', 'status': 'success'})
            else:
                results['steps'].append({'name': 'Service Radius', 'status': 'failed', 'error': res.get('error')})
        except Exception as e:
             results['steps'].append({'name': 'Service Radius', 'status': 'failed', 'error': str(e)})

        # 3. Walled Garden (Optional default entries?)
        # For now, we skip detailed walled garden setup as it depends on payment providers.
        
        # Check overall success
        failed = any(s['status'] == 'failed' for s in results['steps'])
        
        return Response({
            'success': not failed,
            'router': router.name,
            'results': results
        })
