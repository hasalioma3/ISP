from rest_framework import serializers
from apps.network.models import Router
from apps.network.services.network_automation import validate_portal_url

class RouterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Router
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'last_sync', 'provisioned', 'provisioned_at',
            'pre_provision_snapshot', 'pre_provision_snapshot_at', 'last_user_sync',
            'is_online', 'status_checked_at', 'last_seen_at', 'last_error', 'last_health',
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate_portal_url(self, value):
        if value:
            error = validate_portal_url(value)
            if error:
                raise serializers.ValidationError(error)
        return value
