import re
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.notifications.fields import EncryptedCharField

SLUG_RE = re.compile(r'^[a-z][a-z0-9]{2,29}$')
RESERVED_SLUGS = {
    'admin', 'api', 'app', 'www', 'mail', 'cloud', 'master', 'saas', 'root', 'postgres', 'template0', 'template1',
    'support', 'billing', 'status', 'help', 'login', 'signup', 'portal', 'static', 'media', 'test', 'demo', 'isp',
}


class Tenant(models.Model):
    """
    One ISP on the platform, and the instance of the ISP billing app that
    runs for it: its own Docker stack (project saas-<slug>), its own
    database (t_<slug>) and Redis index, reached on its own port.
    """
    STATUSES = [
        ('pending', 'Waiting to be set up'),
        ('provisioning', 'Setting up'),
        ('trial', 'Free trial'),
        ('active', 'Active'),
        ('past_due', 'Payment overdue'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Setup failed'),
        ('deleted', 'Deleted'),
    ]
    INSTANCE_STATES = [('', 'Not created'), ('running', 'Running'), ('stopped', 'Stopped'),
                       ('unhealthy', 'Not responding'), ('missing', 'Missing')]
    SETTLEMENT_METHODS = [('', 'Not set'), ('paybill', 'Paybill (B2B)'), ('till', 'Till / Buy Goods (B2B)'),
                          ('phone', 'M-Pesa phone (B2C)')]
    # States where the instance is meant to be up and serving.
    LIVE = ('trial', 'active', 'past_due')

    slug = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=15, choices=STATUSES, default='pending', db_index=True)
    plan = models.ForeignKey('pricing.PricingPlan', null=True, blank=True, on_delete=models.PROTECT, related_name='tenants')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    trial_reminder_sent = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True, help_text='When the ISP became a paying customer')
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspend_reason = models.CharField(max_length=255, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)

    # Instance
    port = models.PositiveIntegerField(unique=True, null=True, blank=True)
    redis_db = models.PositiveIntegerField(unique=True, null=True, blank=True)
    db_name = models.CharField(max_length=63, blank=True)
    db_user = models.CharField(max_length=63, blank=True)
    db_password = EncryptedCharField(max_length=500, blank=True)
    secret_key = EncryptedCharField(max_length=500, blank=True)
    encryption_key = EncryptedCharField(max_length=500, blank=True)
    c2b_secret = EncryptedCharField(max_length=500, blank=True)
    # In the STK callback URL handed to Safaricom (…/api/mpesa/stk/<token>/):
    # tells us which ISP a callback belongs to, and can't be guessed.
    callback_token = models.CharField(max_length=64, unique=True)
    # Optional account-number prefix for paybill payments (see billing.routing).
    account_prefix = models.CharField(max_length=10, unique=True)
    admin_username = models.CharField(max_length=150, default='admin')
    # The owner's chosen password, held (encrypted) only until the instance's
    # admin account has been created with it, then wiped.
    pending_admin_password = EncryptedCharField(max_length=500, blank=True)
    instance_state = models.CharField(max_length=10, choices=INSTANCE_STATES, default='', blank=True)
    last_health_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    image_tag = models.CharField(max_length=50, blank=True)

    # Where the ISP's money is sent
    settlement_method = models.CharField(max_length=10, choices=SETTLEMENT_METHODS, default='', blank=True)
    settlement_account = models.CharField(max_length=20, blank=True, help_text='Paybill/till number, or phone')
    settlement_account_ref = models.CharField(max_length=50, blank=True, help_text='Account number (paybill only)')
    settlement_name = models.CharField(max_length=150, blank=True)
    settlement_hold = models.BooleanField(default=False, help_text='Pause payouts to this ISP')

    # Last known subscriber counts (see tenants.metrics)
    metrics = models.JSONField(default=dict, blank=True)
    metrics_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tenants'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.slug})'

    def save(self, *args, **kwargs):
        if not self.callback_token:
            self.callback_token = secrets.token_urlsafe(24)
        if not self.account_prefix:
            self.account_prefix = self._free_prefix()
        super().save(*args, **kwargs)

    def _free_prefix(self):
        base = re.sub(r'[^A-Z]', '', self.slug.upper())[:4] or 'ISP'
        candidate, n = base, 1
        while Tenant.objects.filter(account_prefix=candidate).exclude(pk=self.pk).exists():
            n += 1
            candidate = f'{base[:3]}{n}'
        return candidate

    @property
    def project(self):
        return f'saas-{self.slug}'

    @property
    def env_path(self):
        return settings.SAAS_TENANT_ENV_DIR / f'{self.slug}.env'

    @property
    def backend_url(self):
        return settings.SAAS_TENANT_BACKEND_URL.format(slug=self.slug)

    @property
    def url(self):
        if not self.port:
            return ''
        from cloud.core.models import PlatformSettings
        cfg = PlatformSettings.load()
        return cfg.tenant_url_template.format(host=cfg.tenant_host, port=self.port, slug=self.slug)

    @property
    def is_live(self):
        return self.status in self.LIVE

    @property
    def trial_seconds_left(self):
        if self.status != 'trial' or not self.trial_ends_at:
            return None
        return max(0, int((self.trial_ends_at - timezone.now()).total_seconds()))

    def effective_plan(self):
        from cloud.pricing.models import PricingPlan
        return self.plan or PricingPlan.default()


class TenantEvent(models.Model):
    """Activity log for a tenant: what happened, who did it."""
    KINDS = [('signup', 'Sign-up'), ('provision', 'Provisioning'), ('lifecycle', 'Lifecycle'), ('instance', 'Instance'),
             ('billing', 'Billing'), ('payment', 'Payment'), ('settlement', 'Settlement'), ('note', 'Note'),
             ('error', 'Error')]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='events')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=12, choices=KINDS)
    message = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'tenant_events'
        ordering = ['-created_at']


class UsageSnapshot(models.Model):
    """
    One row per tenant per day: the highest and the latest subscriber counts
    seen that day, per service type -- {"active": {"pppoe": 40, ...},
    "all": {...}}. Invoices are computed from these, so a count is never
    re-read from the ISP's (editable) database after the fact.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='snapshots')
    date = models.DateField()
    peak = models.JSONField(default=dict)
    latest = models.JSONField(default=dict)
    samples = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'usage_snapshots'
        unique_together = [('tenant', 'date')]
        ordering = ['-date']
