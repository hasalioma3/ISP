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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change or not {'pppoe_username', 'pppoe_password'} & set(form.changed_data):
            return
        from django.contrib import messages
        from apps.network.services.network_automation import network_automation

        result = network_automation.update_pppoe_credentials(obj, obj.pppoe_username, obj.pppoe_password)
        if not result['synced']:
            return  # never activated on a router -- activation will use the new values
        if result['success']:
            self.message_user(request, f"PPPoE login for {obj.username} updated on the router.", messages.SUCCESS)
        else:
            self.message_user(request, f"Saved, but NOT updated on the router: {result.get('error')}", messages.ERROR)
