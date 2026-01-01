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
    
    class Meta:
        model = Customer
        fields = ['id', 'username', 'email', 'phone_number', 'first_name', 'last_name',
                  'full_name', 'service_type', 'status', 'account_balance', 'is_verified',
                  'pppoe_username', 'hotspot_username', 'created_at', 'is_staff', 'is_superuser']
        read_only_fields = ['id', 'status', 'account_balance', 'is_verified', 'created_at', 'is_staff', 'is_superuser']

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
