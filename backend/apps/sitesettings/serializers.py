from django.conf import settings
from rest_framework import serializers
from .models import SiteSettings


class SiteSettingsSerializer(serializers.ModelSerializer):
    # Where customers can pay without an STK prompt (self-care "Or Paybill
    # ..." line). Read from the M-Pesa env config; public anyway since
    # customers pay to it. For a till there's no account number to quote.
    payment_shortcode = serializers.SerializerMethodField()
    payment_shortcode_type = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = ['company_name', 'logo', 'favicon', 'support_phone',
                  'payment_shortcode', 'payment_shortcode_type']
        read_only_fields = ['favicon']

    def get_payment_shortcode(self, obj):
        if settings.MPESA_SHORTCODE_TYPE == 'till':
            return settings.MPESA_TILL_NUMBER or settings.MPESA_SHORTCODE
        return settings.MPESA_SHORTCODE

    def get_payment_shortcode_type(self, obj):
        return settings.MPESA_SHORTCODE_TYPE
