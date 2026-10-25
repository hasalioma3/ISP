from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.customers.permissions import RoleAllowed

from .models import CPEDevice
from .serializers import CPEDeviceSerializer
from .services.acs_service import ACSService


class CPEDeviceViewSet(viewsets.ModelViewSet):
    """
    Manage customer-premises TR-069 devices. Technicians can view devices
    and run diagnostics, but anything that writes to the device itself
    (reboot/factory-reset/WiFi change/firmware push) or changes what's
    registered (create/update/delete/link to a customer) stays admin-only
    -- same split RouterViewSet uses for MikroTik routers.
    """
    queryset = CPEDevice.objects.select_related('customer').all()
    serializer_class = CPEDeviceSerializer
    filterset_fields = ['brand', 'is_online']

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'diagnostics']:
            return [RoleAllowed('admin', 'technician')()]
        return [RoleAllowed('admin')()]

    def get_queryset(self):
        qs = super().get_queryset()
        unlinked = self.request.query_params.get('unlinked')
        if unlinked == 'true':
            qs = qs.filter(customer__isnull=True)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(serial_number__icontains=search)
        return qs

    @action(detail=True, methods=['post'])
    def link_customer(self, request, pk=None):
        device = self.get_object()
        customer_id = request.data.get('customer_id')
        if not customer_id:
            return Response({'error': 'customer_id is required'}, status=400)
        from apps.customers.models import Customer
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return Response({'error': 'Customer not found'}, status=404)
        if CPEDevice.objects.filter(customer=customer).exclude(pk=device.pk).exists():
            return Response({'error': f'{customer.username} already has a linked CPE device'}, status=400)
        device.customer = customer
        device.save(update_fields=['customer', 'updated_at'])
        return Response(CPEDeviceSerializer(device).data)

    @action(detail=True, methods=['post'])
    def unlink_customer(self, request, pk=None):
        device = self.get_object()
        device.customer = None
        device.save(update_fields=['customer', 'updated_at'])
        return Response(CPEDeviceSerializer(device).data)

    @action(detail=True, methods=['post'])
    def reboot(self, request, pk=None):
        device = self.get_object()
        result = ACSService().reboot(device.genieacs_device_id)
        return Response(result, status=200 if result['success'] else 502)

    @action(detail=True, methods=['post'])
    def factory_reset(self, request, pk=None):
        device = self.get_object()
        result = ACSService().factory_reset(device.genieacs_device_id)
        return Response(result, status=200 if result['success'] else 502)

    @action(detail=True, methods=['post'])
    def set_wifi(self, request, pk=None):
        device = self.get_object()
        ssid = (request.data.get('ssid') or '').strip()
        password = request.data.get('password') or ''
        if not ssid or len(password) < 8:
            return Response({'error': 'ssid is required and password must be at least 8 characters'}, status=400)
        result = ACSService().set_wifi(device.genieacs_device_id, ssid, password)
        if result['success']:
            device.wifi_ssid = ssid
            device.save(update_fields=['wifi_ssid', 'updated_at'])
        return Response(result, status=200 if result['success'] else 502)

    @action(detail=True, methods=['get'])
    def diagnostics(self, request, pk=None):
        device = self.get_object()
        result = ACSService().get_diagnostics(device.genieacs_device_id)
        return Response(result, status=200 if result['success'] else 502)

    @action(detail=True, methods=['post'])
    def push_firmware(self, request, pk=None):
        device = self.get_object()
        file_name = request.data.get('file_name')
        if not file_name:
            return Response({'error': 'file_name is required (upload it to GenieACS first)'}, status=400)
        result = ACSService().push_firmware(device.genieacs_device_id, file_name)
        return Response(result, status=200 if result['success'] else 502)
