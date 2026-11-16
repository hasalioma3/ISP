from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    verbose_name = 'Audit log'

    def ready(self):
        from apps.audit import signals  # noqa: F401  (connects the model/auth/celery hooks)
