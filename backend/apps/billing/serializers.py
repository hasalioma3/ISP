from rest_framework import serializers
from django.db.models.functions import Lower, Trim
from apps.billing.models import BillingPlan, Subscription, Transaction, UsageRecord


class BillingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPlan
        fields = '__all__'

    def validate_name(self, value):
        value = value.strip()
        existing_plans = BillingPlan.objects.annotate(
            normalized_name=Lower(Trim('name'))
        ).filter(normalized_name=value.lower())
        if self.instance:
            existing_plans = existing_plans.exclude(pk=self.instance.pk)
        if existing_plans.exists():
            raise serializers.ValidationError('A plan with this name already exists.')
        return value

    def validate(self, attrs):
        fup_values = {
            field: attrs.get(field, getattr(self.instance, field, None))
            for field in ('fup_limit_gb', 'fup_download_speed', 'fup_upload_speed')
        }
        if all(value is None for value in fup_values.values()):
            return attrs
        if any(value is None for value in fup_values.values()):
            raise serializers.ValidationError({
                'fup_limit_gb': 'Set the FUP limit and both reduced speeds, or leave all three blank.'
            })
        if fup_values['fup_limit_gb'] < 1:
            raise serializers.ValidationError({'fup_limit_gb': 'FUP limit must be at least 1 GB.'})
        if fup_values['fup_download_speed'] < 1 or fup_values['fup_upload_speed'] < 1:
            raise serializers.ValidationError({'fup_download_speed': 'FUP speeds must be at least 1 Mbps.'})

        download_speed = attrs.get('download_speed', getattr(self.instance, 'download_speed', None))
        upload_speed = attrs.get('upload_speed', getattr(self.instance, 'upload_speed', None))
        if download_speed is not None and fup_values['fup_download_speed'] > download_speed:
            raise serializers.ValidationError({'fup_download_speed': 'FUP download speed cannot exceed the plan speed.'})
        if upload_speed is not None and fup_values['fup_upload_speed'] > upload_speed:
            raise serializers.ValidationError({'fup_upload_speed': 'FUP upload speed cannot exceed the plan speed.'})
        data_limit_gb = attrs.get('data_limit_gb', getattr(self.instance, 'data_limit_gb', None))
        if data_limit_gb is not None and fup_values['fup_limit_gb'] >= data_limit_gb:
            raise serializers.ValidationError({'fup_limit_gb': 'FUP threshold must be below the plan data limit.'})
        return attrs


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
    plan_name = serializers.CharField(source='plan.name', read_only=True, allow_null=True)
    
    class Meta:
        model = VoucherBatch
        fields = ['id', 'created_at', 'quantity', 'value', 'plan', 'plan_name', 'note', 'generated_by_username', 'vouchers']


class VoucherGenerationSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=1000)
    value = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    plan_id = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)


class VoucherRedeemSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=20)
    mac_address = serializers.CharField(required=False, allow_blank=True, max_length=17)
