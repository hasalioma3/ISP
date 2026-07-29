from io import BytesIO
from django.core.files.base import ContentFile
from django.db import models


class SiteSettings(models.Model):
    """
    Singleton (always pk=1) branding settings: company name and logo, used
    for the admin header/favicon. Use SiteSettings.load() to fetch it.
    """
    company_name = models.CharField(max_length=100, default='ISP Admin')
    logo = models.ImageField(upload_to='site/', blank=True, null=True)
    # Auto-generated (see save()) square PNG derived from `logo` -- browser
    # tabs render favicons in a tiny square, so an arbitrary (often wide,
    # "wordmark"-shaped) uploaded logo needs to be fitted/padded into a
    # proper square icon rather than used as-is.
    favicon = models.ImageField(upload_to='site/', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'site_settings'
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.company_name

    def save(self, *args, **kwargs):
        self.pk = 1

        try:
            logo_changed = SiteSettings.objects.get(pk=1).logo != self.logo
        except SiteSettings.DoesNotExist:
            logo_changed = bool(self.logo)

        if self.logo and logo_changed:
            self._generate_favicon()
        elif not self.logo:
            self.favicon = None

        super().save(*args, **kwargs)

    def _generate_favicon(self, size=64):
        from PIL import Image

        self.logo.seek(0)
        img = Image.open(self.logo).convert('RGBA')
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)

        buffer = BytesIO()
        canvas.save(buffer, format='PNG')
        self.favicon.save('favicon.png', ContentFile(buffer.getvalue()), save=False)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
