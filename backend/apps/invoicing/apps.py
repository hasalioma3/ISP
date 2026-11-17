from django.apps import AppConfig


class InvoicingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.invoicing'
    verbose_name = 'Customer invoices'

    def ready(self):
        from apps.invoicing import signals  # noqa: F401
