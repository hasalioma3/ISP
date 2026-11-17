from rest_framework import serializers
from apps.payments.models import PaymentRequest, PaymentCallback


class PaymentRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRequest
        fields = '__all__'
        read_only_fields = ['customer', 'merchant_request_id', 'checkout_request_id',
                           'response_code', 'response_description', 'customer_message', 'status']


class InitiatePaymentSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()
    phone_number = serializers.CharField(max_length=15)
    mac_address = serializers.CharField(required=False, allow_blank=True, max_length=17)
    
    def validate_phone_number(self, value):
        # Stored and used as the guest username in 07XXXXXXXX form, so a
        # bare "725316559" or "254725316559" lands on the same account.
        from apps.payments.services.phone_hash import local_phone, normalize_phone
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Phone number is required")
        full = normalize_phone(value)
        if not (full.isdigit() and len(full) == 12):
            raise serializers.ValidationError("Enter a valid phone number, e.g. 0712345678")
        return local_phone(value)


class PaymentCallbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentCallback
        fields = '__all__'
