from rest_framework import serializers

from .models import CPEDevice


class CPEDeviceSerializer(serializers.ModelSerializer):
    customer_username = serializers.CharField(source='customer.username', read_only=True, default=None)
    customer_full_name = serializers.CharField(source='customer.full_name', read_only=True, default=None)
    brand_display = serializers.CharField(source='get_brand_display', read_only=True)

    class Meta:
        model = CPEDevice
        fields = [
            'id', 'customer', 'customer_username', 'customer_full_name',
            'genieacs_device_id', 'serial_number', 'brand', 'brand_display',
            'manufacturer', 'model_name', 'software_version', 'mac_address',
            'wifi_ssid', 'last_inform', 'is_online', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'genieacs_device_id', 'manufacturer', 'model_name', 'software_version',
            'mac_address', 'wifi_ssid', 'last_inform', 'is_online',
            'created_at', 'updated_at',
        ]
