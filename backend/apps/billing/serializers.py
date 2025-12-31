from rest_framework import serializers
from apps.billing.models import BillingPlan, Subscription, Transaction, UsageRecord


class BillingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPlan
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = BillingPlanSerializer(read_only=True)
    customer_username = serializers.CharField(source='customer.username', read_only=True)
    is_expired = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()
    
    class Meta:
        model = Subscription
        fields = '__all__'


class TransactionSerializer(serializers.ModelSerializer):
    customer_username = serializers.CharField(source='customer.username', read_only=True)
    
    class Meta:
        model = Transaction
        fields = '__all__'


class UsageRecordSerializer(serializers.ModelSerializer):
    total_gb = serializers.ReadOnlyField()
    
    class Meta:
        model = UsageRecord
        fields = '__all__'


from apps.billing.models import Voucher, VoucherBatch


class VoucherSerializer(serializers.ModelSerializer):
    batch_id = serializers.ReadOnlyField(source='batch.id')
    
    class Meta:
        model = Voucher
        fields = ['id', 'code', 'amount', 'status', 'batch_id', 'expiry_date', 'created_at']


class VoucherBatchSerializer(serializers.ModelSerializer):
    vouchers = VoucherSerializer(many=True, read_only=True)
    generated_by_username = serializers.CharField(source='generated_by.username', read_only=True)
    
    class Meta:
        model = VoucherBatch
        fields = ['id', 'created_at', 'quantity', 'value', 'note', 'generated_by_username', 'vouchers']


class VoucherGenerationSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=1000)
    value = serializers.DecimalField(max_digits=10, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True)


class VoucherRedeemSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=12, max_length=20)
