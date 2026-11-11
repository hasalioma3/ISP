from django.contrib import admin, messages
from .models import Router, PPPoESecret, HotspotUser, ActiveSession
from apps.network.services.network_automation import network_automation


@admin.register(Router)
class RouterAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip_address', 'is_active', 'provisioned', 'last_sync']
    list_filter = ['is_active', 'provisioned', 'last_sync']
    search_fields = ['name', 'ip_address', 'location']
    actions = ['backup_router', 'provision_router', 'sync_profiles', 'sync_active_users']

    @admin.action(description="Backup Router Config (snapshot only, no changes)")
    def backup_router(self, request, queryset):
        for router in queryset:
            try:
                result = network_automation.snapshot_router(router)
                if result.get('success'):
                    self.message_user(request, f"Snapshot saved for {router.name}.", messages.SUCCESS)
                else:
                    self.message_user(request, f"Error backing up {router.name}: {result.get('error')}", messages.ERROR)
            except Exception as e:
                self.message_user(request, f"Critical error backing up {router.name}: {str(e)}", messages.ERROR)

    @admin.action(description="Provision Router (full bootstrap: pools, DHCP, NAT, Hotspot/PPPoE server)")
    def provision_router(self, request, queryset):
        for router in queryset:
            try:
                result = network_automation.provision_router(router)
                if result.get('error'):
                    self.message_user(request, f"Error provisioning {router.name}: {result['error']}", messages.ERROR)
                    continue
                success_count = len(result.get('success', []))
                failed_count = len(result.get('failed', []))
                if failed_count > 0:
                    errors = "; ".join(result['failed'][:3])
                    self.message_user(
                        request,
                        f"Provisioned {router.name}: {success_count} steps ok, {failed_count} failed. Errors: {errors}",
                        messages.WARNING
                    )
                else:
                    self.message_user(
                        request,
                        f"Provisioned {router.name}: all {success_count} steps completed. Ready for Hotspot/PPPoE connections.",
                        messages.SUCCESS
                    )
            except Exception as e:
                self.message_user(request, f"Critical error provisioning {router.name}: {str(e)}", messages.ERROR)

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
                    if failed_count > 0:
                        # Show first few errors to help debug
                        errors = "; ".join(result['failed'][:2])
                        self.message_user(
                            request, 
                            f"Synced {router.name}: {success_count} success, {failed_count} failed. Errors: {errors}",
                            messages.WARNING
                        )
                    else:
                        self.message_user(
                            request, 
                            f"Synced {router.name}: {success_count} success.",
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
                    if failed_count > 0:
                        errors = "; ".join(result['failed'][:2])
                        self.message_user(
                            request, 
                            f"Synced {router.name}: {success_count} success, {failed_count} failed. Errors: {errors}",
                            messages.WARNING
                        )
                    else:
                        self.message_user(
                            request, 
                            f"Synced {router.name}: {success_count} success.",
                            messages.SUCCESS
                        )
            except Exception as e:
                self.message_user(request, f"Critical error syncing {router.name}: {str(e)}", messages.ERROR)


PPPOE_SYNC_FIELDS = {'username', 'password', 'profile', 'status', 'router'}


def report_pppoe_push(model_admin, request, pppoe_secret, previous_username=None):
    result = network_automation.push_pppoe_secret(pppoe_secret, previous_username=previous_username)
    if result['success']:
        model_admin.message_user(request, f"PPPoE secret {pppoe_secret.username} updated on {pppoe_secret.router.name}.", messages.SUCCESS)
    else:
        model_admin.message_user(
            request, f"Saved, but NOT updated on the router: {result.get('error')}", messages.ERROR
        )


@admin.register(PPPoESecret)
class PPPoESecretAdmin(admin.ModelAdmin):
    list_display = ['username', 'customer', 'router', 'profile', 'status', 'synced_to_router']
    list_filter = ['status', 'synced_to_router', 'router']
    search_fields = ['username', 'customer__username']
    raw_id_fields = ['customer', 'router']

    def save_model(self, request, obj, form, change):
        previous_username = PPPoESecret.objects.filter(pk=obj.pk).values_list('username', flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        # Customer.pppoe_username/pppoe_password are what the frontend shows
        # and what activation pushes -- without this, the next activation
        # silently reverts the router to the old credentials.
        type(obj.customer).objects.filter(pk=obj.customer_id).update(
            pppoe_username=obj.username, pppoe_password=obj.password,
        )
        if change and PPPOE_SYNC_FIELDS & set(form.changed_data):
            report_pppoe_push(self, request, obj, previous_username=previous_username)


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
