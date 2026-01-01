from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from apps.customers.models import Customer


class CustomerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = Customer
        fields = ['username', 'email', 'password', 'password2', 'phone_number', 
                  'first_name', 'last_name', 'service_type']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        
        customer = Customer.objects.create(**validated_data)
        customer.set_password(password)
        
        # Generate PPPoE/Hotspot credentials
        if customer.service_type in ['pppoe', 'both']:
            customer.pppoe_username = customer.username
            customer.pppoe_password = password
        
        if customer.service_type in ['hotspot', 'both']:
            customer.hotspot_username = customer.username
            customer.hotspot_password = password
        
        customer.save()
        return customer



class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    current_subscription = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = ['id', 'username', 'email', 'phone_number', 'first_name', 'last_name',
                  'full_name', 'service_type', 'status', 'account_balance', 'is_verified',
                  'pppoe_username', 'hotspot_username', 'created_at', 'is_staff', 'is_superuser',
                  'current_subscription']
        read_only_fields = ['id', 'status', 'account_balance', 'is_verified', 'created_at', 'is_staff', 'is_superuser']

    def get_current_subscription(self, obj):
        # Return simplified details of the latest subscription
        sub = obj.subscriptions.order_by('-created_at').first()
        if sub:
            return {
                'id': sub.id,
                'plan_name': sub.plan.name,
                'status': sub.status,
                'expiry_date': sub.expiry_date,
                'days_remaining': sub.days_remaining
            }
        return None

class CustomerDetailSerializer(CustomerSerializer):
    subscription_history = serializers.SerializerMethodField()
    usage_summary = serializers.SerializerMethodField()
    
    class Meta(CustomerSerializer.Meta):
        fields = CustomerSerializer.Meta.fields + ['subscription_history', 'usage_summary']
        
    def get_subscription_history(self, obj):
        # Last 10 subscriptions with payment details
        history = []
        subs = obj.subscriptions.all().order_by('-created_at')[:10]
        for sub in subs:
            # Find associated transaction (if any)
            # Assuming 1-to-1 or 1-to-many, take latest transaction for this sub
            trans = sub.transactions.last()
            history.append({
                'id': sub.id,
                'plan_name': sub.plan.name,
                'start_date': sub.start_date,
                'expiry_date': sub.expiry_date,
                'status': sub.status,
                'amount': trans.amount if trans else 0,
                'payment_method': trans.payment_method if trans else 'N/A',
                'mpesa_receipt': trans.mpesa_receipt_number if trans else None,
                'transaction_date': trans.created_at if trans else sub.created_at
            })
        return history

    def get_usage_summary(self, obj):
        # Latest usage record
        usage = obj.usage_records.order_by('-start_time').first()
        if usage:
            return {
                'total_gb': usage.total_gb,
                'upload_speed_mbps': usage.upload_speed_mbps,
                'download_speed_mbps': usage.download_speed_mbps,
                'session_time_seconds': usage.session_time_seconds,
                'last_updated': usage.updated_at
            }
        return None

class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = Customer
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone_number', 
                  'is_staff', 'is_active', 'is_superuser', 'password', 'date_joined']
        read_only_fields = ['id', 'date_joined']
        
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = Customer.objects.create(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user
        
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
