from rest_framework import serializers
from .models import SiteSettings


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = ['company_name', 'logo', 'favicon']
        read_only_fields = ['favicon']
