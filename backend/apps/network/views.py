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

        except Exception as e:
            results['steps'].append({'name': 'Service Radius', 'status': 'failed', 'error': str(e)})

        # 3. Interface Setup (Bridge)
        try:
            # Create bridge
            res = mikrotik.create_bridge(name='hotspot-bridge')
            if res['success']:
                results['steps'].append({'name': 'Bridge: hotspot-bridge', 'status': 'success'})
            else:
                results['steps'].append({'name': 'Bridge: hotspot-bridge', 'status': 'failed', 'error': res.get('error')})
            
            # Add port (assuming ether3 as per request/plan)
            # CAUTION: This might cut off access if connected via ether3!
            # Assuming backend is not connected via ether3 or is via VLAN.
            res = mikrotik.add_port_to_bridge(bridge='hotspot-bridge', interface='ether3')
            if res['success']:
                results['steps'].append({'name': 'Port: ether3 -> bridge', 'status': 'success'})
            else:
                results['steps'].append({'name': 'Port: ether3 -> bridge', 'status': 'failed', 'error': res.get('error')})
        except Exception as e:
             results['steps'].append({'name': 'Interface Setup', 'status': 'failed', 'error': str(e)})

        # 4. IP & Network Setup
        try:
            # Add Gateway IP
            res = mikrotik.add_ip_address(address='10.5.50.1/24', interface='hotspot-bridge', comment='Hotspot Gateway')
            if res['success']:
                results['steps'].append({'name': 'IP: 10.5.50.1/24', 'status': 'success'})
            else:
                results['steps'].append({'name': 'IP: 10.5.50.1/24', 'status': 'failed', 'error': res.get('error')})
            
            # Add IP Pool
            res = mikrotik.add_ip_pool(name='hs-pool-1', ranges='10.5.50.10-10.5.50.254')
            if res['success']:
                results['steps'].append({'name': 'Pool: hs-pool-1', 'status': 'success'})
            else:
                results['steps'].append({'name': 'Pool: hs-pool-1', 'status': 'failed', 'error': res.get('error')})
        except Exception as e:
            results['steps'].append({'name': 'Network Setup', 'status': 'failed', 'error': str(e)})

        # 5. Hotspot Setup
        try:
            # Server Profile
            res = mikrotik.add_hotspot_server_profile(name='hsprof1', dns_name='login.isp.local', html_directory='hotspot')
            if res['success']:
                results['steps'].append({'name': 'HS Profile: hsprof1', 'status': 'success'})
            else:
                results['steps'].append({'name': 'HS Profile: hsprof1', 'status': 'failed', 'error': res.get('error')})
            
            # Hotspot Server
            res = mikrotik.add_hotspot_server(name='hotspot1', interface='hotspot-bridge', profile='hsprof1', address_pool='hs-pool-1')
            if res['success']:
                results['steps'].append({'name': 'HS Server: hotspot1', 'status': 'success'})
            else:
                results['steps'].append({'name': 'HS Server: hotspot1', 'status': 'failed', 'error': res.get('error')})
        except Exception as e:
            results['steps'].append({'name': 'Hotspot Setup', 'status': 'failed', 'error': str(e)})

        # 6. Walled Garden
        try:
            # Generic rules
            mikrotik.add_walled_garden_host(dst_host='*.hasalioma.online', comment='ISP Billing')
            mikrotik.add_walled_garden_host(dst_host='*.safaricom.co.ke', comment='MPesa')
            # M-Pesa IPs (Examples, normally detailed list)
            mikrotik.add_walled_garden_ip(dst_address='196.201.230.0/24', comment='MPesa IP')
            results['steps'].append({'name': 'Walled Garden', 'status': 'success'})
        except Exception as e:
            results['steps'].append({'name': 'Walled Garden', 'status': 'failed', 'error': str(e)})
        
        return Response({
            'success': not failed,
            'router': router.name,
            'results': results
        })
