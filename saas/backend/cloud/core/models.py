import secrets
from decimal import Decimal

from django.db import models

# Reused from the ISP billing app rather than copied: Fernet-encrypted
# column, keyed by NOTIFICATIONS_ENCRYPTION_KEY (= SAAS_ENCRYPTION_KEY here).
from apps.notifications.fields import EncryptedCharField


class EncryptedTextField(EncryptedCharField):
    """Long secrets (a PEM certificate) -- same encryption, TEXT column."""

    def get_internal_type(self):
        return 'TextField'

    def formfield(self, **kwargs):
        return models.TextField().formfield(**kwargs)


class PlatformSettings(models.Model):
    """Singleton (pk=1) holding how the whole platform behaves."""
    SETTLEMENT_SCHEDULES = [('daily', 'Daily'), ('weekly', 'Weekly'), ('manual', 'Manual only')]
    MPESA_ENVS = [('sandbox', 'Sandbox'), ('production', 'Production')]
    SHORTCODE_TYPES = [('paybill', 'Paybill'), ('till', 'Till (Buy Goods)')]

    brand_name = models.CharField(max_length=100, default='ISP Cloud')
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=30, blank=True)
    # Public HTTPS address of THIS app. Safaricom posts every STK callback,
    # C2B confirmation and settlement result here.
    public_base_url = models.URLField(blank=True, help_text='e.g. https://cloud.example.com')
    # Host the ISP instances are reached on; each instance gets its own port.
    tenant_host = models.CharField(max_length=255, default='localhost')
    tenant_url_template = models.CharField(max_length=255, default='https://{host}:{port}/',
                                           help_text='{host}, {port} and {slug} are filled in')
    port_range_start = models.PositiveIntegerField(default=9500)
    port_range_end = models.PositiveIntegerField(default=9999)
    max_tenants = models.PositiveIntegerField(default=200)

    # Sign-up & lifecycle
    signup_enabled = models.BooleanField(default=True)
    trial_days = models.PositiveSmallIntegerField(default=2)
    grace_days = models.PositiveSmallIntegerField(default=7, help_text='Days an invoice may be overdue before suspension')
    retention_days = models.PositiveSmallIntegerField(default=30, help_text='Days a suspended instance is kept before it can be deleted')
    terms_url = models.URLField(blank=True)

    # Invoicing
    invoice_day = models.PositiveSmallIntegerField(default=1, help_text='Day of the month invoices are issued (1-28)')
    invoice_due_days = models.PositiveSmallIntegerField(default=7)
    auto_deduct_invoices = models.BooleanField(default=True, help_text='Pay invoices from the M-Pesa money held for the ISP')

    # M-Pesa: the platform's own shortcode collects every ISP's payments.
    mpesa_environment = models.CharField(max_length=10, choices=MPESA_ENVS, default='sandbox')
    mpesa_shortcode = models.CharField(max_length=20, blank=True)
    mpesa_shortcode_type = models.CharField(max_length=10, choices=SHORTCODE_TYPES, default='paybill')
    mpesa_till_number = models.CharField(max_length=20, blank=True)
    mpesa_passkey = EncryptedCharField(max_length=500, blank=True)
    # The Daraja app this server uses (C2B registration, STK query,
    # settlements). Never given to an ISP instance.
    mpesa_consumer_key = EncryptedCharField(max_length=500, blank=True)
    mpesa_consumer_secret = EncryptedCharField(max_length=500, blank=True)
    # A SEPARATE Daraja app given to the ISP instances, with only "M-Pesa
    # Express" (STK) enabled. ISP admins control their instance and its
    # backups, so whatever is in its env must be safe for them to see.
    tenant_consumer_key = EncryptedCharField(max_length=500, blank=True)
    tenant_consumer_secret = EncryptedCharField(max_length=500, blank=True)
    c2b_secret = models.CharField(max_length=64, blank=True)
    c2b_registered_at = models.DateTimeField(null=True, blank=True)
    verify_stk_callbacks = models.BooleanField(default=True, help_text='Confirm each STK payment with Safaricom before crediting it')

    # Settlement (B2B to a paybill/till, B2C to a phone)
    settlement_shortcode = models.CharField(max_length=20, blank=True, help_text='Defaults to the collection shortcode')
    initiator_name = models.CharField(max_length=100, blank=True)
    initiator_password = EncryptedCharField(max_length=500, blank=True)
    mpesa_certificate = EncryptedTextField(max_length=10000, blank=True, help_text="Safaricom's public certificate (PEM)")
    settlement_schedule = models.CharField(max_length=10, choices=SETTLEMENT_SCHEDULES, default='daily')
    settlement_hour = models.PositiveSmallIntegerField(default=10)
    settlement_weekday = models.PositiveSmallIntegerField(default=0)  # 0 = Monday
    settlement_min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('100'))
    settlement_requires_approval = models.BooleanField(default=True)
    reserve_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'),
                                         help_text='Kept back from every payout (refunds, reversals)')
    # Default fees (a pricing plan can override them).
    collection_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    settlement_fee_flat = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'platform_settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        if not obj.c2b_secret:
            obj.c2b_secret = secrets.token_urlsafe(24)
            obj.save(update_fields=['c2b_secret'])
        return obj

    @property
    def mpesa_base_url(self):
        return 'https://api.safaricom.co.ke' if self.mpesa_environment == 'production' else 'https://sandbox.safaricom.co.ke'

    def public_url(self, path):
        return self.public_base_url.rstrip('/') + path

    def __str__(self):
        return 'Platform settings'
