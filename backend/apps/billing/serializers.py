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
