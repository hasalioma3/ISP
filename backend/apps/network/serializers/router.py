from rest_framework import serializers
from apps.network.models import Router

class RouterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Router
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'last_sync', 'provisioned', 'provisioned_at',
            'pre_provision_snapshot', 'pre_provision_snapshot_at',
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }
