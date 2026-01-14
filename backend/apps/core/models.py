from django.db import models
from django.core.cache import cache

class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super(SingletonModel, self).save(*args, **kwargs)
        self.set_cache()

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        if cache.get(cls.__name__) is None:
            obj, created = cls.objects.get_or_create(pk=1)
            if not created:
                obj.set_cache()
        return cache.get(cls.__name__)

    def set_cache(self):
        cache.set(self.__class__.__name__, self)

class TenantConfig(SingletonModel):
    # Branding
    company_name = models.CharField(max_length=255, default="ISP Billing")
    logo = models.ImageField(upload_to='branding/', null=True, blank=True)
    favicon = models.ImageField(upload_to='branding/', null=True, blank=True)
    primary_color = models.CharField(max_length=7, default="#000000", help_text="Hex color code")
    
    # M-Pesa Configuration
    mpesa_consumer_key = models.CharField(max_length=255, blank=True)
    mpesa_consumer_secret = models.CharField(max_length=255, blank=True)
    mpesa_shortcode = models.CharField(max_length=20, blank=True)
    mpesa_passkey = models.TextField(blank=True)
    mpesa_environment = models.CharField(
        max_length=20, 
        choices=[('sandbox', 'Sandbox'), ('production', 'Production')],
        default='sandbox'
    )

    def __str__(self):
        return "Tenant Configuration"

    class Meta:
        verbose_name = "Tenant Configuration"
        verbose_name_plural = "Tenant Configuration"
