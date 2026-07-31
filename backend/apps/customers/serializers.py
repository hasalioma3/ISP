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
    # The following are only populated when the queryset annotates them
    # (SubscriberViewSet) -- Customer itself has no expiry/plan/router/IP
    # field of its own, they're derived from related Subscription/Router/
    # UsageRecord rows. On non-annotated instances (register/login/profile)
    # these are simply omitted from the response.
    calculated_expiry = serializers.DateTimeField(read_only=True)
    current_plan_name = serializers.CharField(read_only=True)
    current_plan_status = serializers.CharField(read_only=True)
    router_name = serializers.CharField(read_only=True)
    last_ip = serializers.CharField(read_only=True)

    # Plaintext by necessity (RouterOS needs the raw value for PPPoE/Hotspot
    # auth) -- unlike the portal login password, which is a one-way hash
    # (set_password) and genuinely can't be recovered by anyone, superadmin
    # included. Populated for a superuser caller (viewing anyone), or for a
    # customer viewing their own profile (they already know it -- they need
    # it to configure a router/device); every other caller gets null. Only
    # applies when the request is present in context, which a view must
    # explicitly pass (e.g. SubscriberViewSet, profile()).
    pppoe_password = serializers.SerializerMethodField()
    hotspot_password = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ['id', 'username', 'email', 'phone_number', 'first_name', 'last_name',
                  'full_name', 'service_type', 'status', 'account_balance', 'is_verified',
                  'pppoe_username', 'pppoe_password', 'hotspot_username', 'hotspot_password',
                  'hotspot_mac_address', 'static_ip_address',
                  'address', 'id_number', 'notes', 'created_at', 'is_staff', 'is_superuser',
                  'role', 'calculated_expiry', 'current_plan_name', 'current_plan_status',
                  'router_name', 'last_ip']
        read_only_fields = ['id', 'status', 'account_balance', 'is_verified', 'created_at', 'is_staff', 'is_superuser']

    def _may_see_passwords(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None):
            return False
        return bool(request.user.is_superuser or request.user == obj)

    def get_pppoe_password(self, obj):
        return obj.pppoe_password if self._may_see_passwords(obj) else None

    def get_hotspot_password(self, obj):
        return obj.hotspot_password if self._may_see_passwords(obj) else None


class SelfProfileSerializer(serializers.ModelSerializer):
    """
    Used only by the self-service "edit my profile" endpoint -- a narrow
    whitelist of genuinely personal fields. Deliberately NOT the same as
    CustomerSerializer: that one also exposes `role`/`service_type`/
    `notes`/etc for admin-side subscriber management, and letting a user
    write those on themselves would (for `role` specifically) let a
    technician un-set their own income-visibility restriction -- role
    changes must only happen through StaffViewSet (admin-only).
    """
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = Customer
        fields = ['id', 'username', 'email', 'phone_number', 'first_name', 'last_name', 'full_name']
        read_only_fields = ['id', 'username']


class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Customer
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone_number',
                  'role', 'is_staff', 'is_active', 'is_superuser', 'password', 'date_joined']
        read_only_fields = ['id', 'is_superuser', 'date_joined']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        validated_data['is_staff'] = True
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
