from django.contrib import admin

from apps.notifications.models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'channel', 'audience', 'event', 'recipient',
                    'customer', 'status', 'attempts', 'provider')
    list_filter = ('channel', 'status', 'audience', 'event')
    search_fields = ('recipient', 'message', 'customer__username', 'customer__phone_number')
    readonly_fields = [f.name for f in NotificationLog._meta.fields]
    date_hierarchy = 'created_at'
    actions = ['retry_failed']

    def has_add_permission(self, request):
        return False

    @admin.action(description='Retry sending selected notifications')
    def retry_failed(self, request, queryset):
        from apps.notifications.tasks import send_notification
        count = 0
        for log in queryset.exclude(status='sent'):
            send_notification.delay(log.id)
            count += 1
        self.message_user(request, f"Re-queued {count} notification(s).")
