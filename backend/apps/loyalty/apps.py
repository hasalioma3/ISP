from django.apps import AppConfig


class LoyaltyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.loyalty'
    verbose_name = 'Loyalty programme'

    def ready(self):
        from apps.loyalty import signals  # noqa: F401
