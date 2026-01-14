from rest_framework import serializers
from .models import TenantConfig

class TenantConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantConfig
        fields = [
            'company_name', 'logo', 'favicon', 'primary_color',
            'mpesa_consumer_key', 'mpesa_consumer_secret', 
            'mpesa_shortcode', 'mpesa_passkey', 'mpesa_environment'
        ]
        
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Obfuscate sensitive data for non-admin users if needed
        # For now, we assume only admins access the settings page
        # But for public branding (logo/name), we might need a separate read-only view/serializer
        return ret

class TenantBrandingSerializer(serializers.ModelSerializer):
    """ Read-only serializer for public branding info """
    class Meta:
        model = TenantConfig
        fields = ['company_name', 'logo', 'favicon', 'primary_color']
