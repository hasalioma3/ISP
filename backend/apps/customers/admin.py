from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(UserAdmin):
    list_display = ['username', 'phone_number', 'service_type', 'status', 'is_verified', 'created_at']
    list_filter = ['service_type', 'status', 'is_verified', 'created_at']
    search_fields = ['username', 'phone_number', 'email', 'first_name', 'last_name']
    
    fieldsets = UserAdmin.fieldsets + (
        ('ISP Information', {
            'fields': ('phone_number', 'id_number', 'address', 'service_type', 'status')
        }),
        ('PPPoE Credentials', {
            'fields': ('pppoe_username', 'pppoe_password')
        }),
        ('Hotspot Credentials', {
            'fields': ('hotspot_username', 'hotspot_password', 'hotspot_mac_address')
        }),
        ('Account Information', {
            'fields': ('account_balance', 'is_verified', 'notes')
        }),
    )
