from django.contrib import admin, messages
from .models import Router, PPPoESecret, HotspotUser, ActiveSession
from apps.network.services.network_automation import network_automation


@admin.register(Router)
class RouterAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip_address', 'is_active', 'last_sync']
    list_filter = ['is_active', 'last_sync']
    search_fields = ['name', 'ip_address', 'location']
    actions = ['sync_profiles', 'sync_active_users']

    @admin.action(description="Sync Plans to MikroTik Profiles")
    def sync_profiles(self, request, queryset):
        for router in queryset:
            try:
                result = network_automation.sync_all_profiles()
                if result.get('error'):
                    self.message_user(request, f"Error syncing {router.name}: {result['error']}", messages.ERROR)
                else:
                    success_count = len(result.get('success', []))
                    failed_count = len(result.get('failed', []))
                    self.message_user(
                        request, 
                        f"Synced {router.name}: {success_count} success, {failed_count} failed.",
                        messages.SUCCESS
                    )
            except Exception as e:
                self.message_user(request, f"Critical error syncing {router.name}: {str(e)}", messages.ERROR)

    @admin.action(description="Sync Active Subscriptions to MikroTik Users")
    def sync_active_users(self, request, queryset):
        for router in queryset:
            try:
                result = network_automation.sync_all_users()
                if result.get('error'):
                    self.message_user(request, f"Error syncing {router.name}: {result['error']}", messages.ERROR)
                else:
                    success_count = len(result.get('success', []))
                    failed_count = len(result.get('failed', []))
                    self.message_user(
                        request, 
                        f"Synced {router.name}: {success_count} success, {failed_count} failed.",
                        messages.SUCCESS
                    )
            except Exception as e:
                self.message_user(request, f"Critical error syncing {router.name}: {str(e)}", messages.ERROR)


@admin.register(PPPoESecret)
class PPPoESecretAdmin(admin.ModelAdmin):
    list_display = ['username', 'customer', 'router', 'profile', 'status', 'synced_to_router']
    list_filter = ['status', 'synced_to_router', 'router']
    search_fields = ['username', 'customer__username']
    raw_id_fields = ['customer', 'router']


@admin.register(HotspotUser)
class HotspotUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'customer', 'router', 'profile', 'status', 'synced_to_router']
    list_filter = ['status', 'synced_to_router', 'router']
    search_fields = ['username', 'customer__username', 'mac_address']
    raw_id_fields = ['customer', 'router']


@admin.register(ActiveSession)
class ActiveSessionAdmin(admin.ModelAdmin):
    list_display = ['username', 'session_type', 'ip_address', 'total_gb', 'start_time']
    list_filter = ['session_type', 'start_time']
    search_fields = ['username', 'ip_address', 'session_id']
    raw_id_fields = ['customer', 'router']
