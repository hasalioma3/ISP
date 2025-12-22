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
    
    def validate_phone_number(self, value):
        # Basic phone number validation
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Phone number is required")
        return value


class PaymentCallbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentCallback
        fields = '__all__'
