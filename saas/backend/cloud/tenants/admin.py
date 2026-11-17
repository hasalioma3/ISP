from django.contrib import admin

from cloud.tenants.models import Tenant, TenantEvent


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['slug', 'name', 'status', 'plan', 'port', 'instance_state', 'created_at']
    list_filter = ['status', 'instance_state']
    search_fields = ['slug', 'name', 'contact_email']
    exclude = ['db_password', 'secret_key', 'encryption_key', 'c2b_secret', 'pending_admin_password']


admin.site.register(TenantEvent)
