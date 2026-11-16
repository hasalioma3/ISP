from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only, superusers only (the log is append-only)."""
    list_display = ('created_at', 'actor_username', 'action', 'model', 'object_repr', 'ip_address', 'source')
    list_filter = ('action', 'source', 'model')
    search_fields = ('actor_username', 'object_repr', 'path', 'object_id')
    date_hierarchy = 'created_at'

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
