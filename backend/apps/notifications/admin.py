from django.contrib import admin
from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'channel', 'event_type', 'status', 'customer', 'created_at']
    list_filter = ['event_type', 'status', 'channel', 'created_at']
    search_fields = ['recipient', 'customer__username', 'provider_message_id']
    raw_id_fields = ['customer', 'subscription']
