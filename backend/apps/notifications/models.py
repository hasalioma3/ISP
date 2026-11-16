from django.db import models

from apps.customers.models import Customer
from apps.notifications.fields import EncryptedCharField


class NotificationSettings(models.Model):
    """
    Singleton (always pk=1), mirroring apps.sitesettings.models.SiteSettings.
    Holds credentials for the SMS and Telegram channels. WhatsApp has no
    credential fields here -- Baileys' paired session lives entirely in the
    whatsapp-service sidecar's own volume, not in this database.
    """
    AT_ENVIRONMENT_CHOICES = [
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ]

    # --- Africa's Talking (SMS) ---
    at_username = models.CharField(max_length=100, blank=True)
    at_api_key = EncryptedCharField(max_length=500, blank=True)
    at_sender_id = models.CharField(max_length=20, blank=True)
    at_environment = models.CharField(max_length=10, choices=AT_ENVIRONMENT_CHOICES, default='sandbox')

    # --- WhatsApp (Baileys sidecar) -- display/toggle state only ---
    whatsapp_enabled = models.BooleanField(default=False)
    whatsapp_sender_number = models.CharField(max_length=20, blank=True)
    # 'baileys' = QR-paired sidecar; 'africastalking' = official WhatsApp
    # Business API via Africa's Talking (reuses the AT username/API key).
    WHATSAPP_PROVIDER_CHOICES = [
        ('baileys', 'QR-paired (Baileys)'),
        ('africastalking', "Africa's Talking WhatsApp API"),
    ]
    whatsapp_provider = models.CharField(max_length=20, choices=WHATSAPP_PROVIDER_CHOICES, default='baileys')
    whatsapp_at_number = models.CharField(max_length=20, blank=True)

    # --- Telegram ---
    telegram_bot_token = EncryptedCharField(max_length=500, blank=True)
    telegram_webhook_secret = EncryptedCharField(max_length=200, blank=True)
    telegram_bot_username = models.CharField(max_length=100, blank=True)

    # --- Email (SMTP) ---
    # Gmail by default: smtp.gmail.com:587 with STARTTLS, logging in with a
    # Gmail address and a Google *App Password* (Google rejects the normal
    # account password over SMTP). 'custom' uses the host/port/encryption
    # below for any other mail server.
    SMTP_PROVIDER_CHOICES = [('gmail', 'Gmail'), ('custom', 'Custom SMTP')]
    SMTP_SECURITY_CHOICES = [('starttls', 'STARTTLS'), ('ssl', 'SSL/TLS'), ('none', 'None')]
    GMAIL_HOST = 'smtp.gmail.com'
    GMAIL_PORT = 587

    email_enabled = models.BooleanField(default=False)
    smtp_provider = models.CharField(max_length=10, choices=SMTP_PROVIDER_CHOICES, default='gmail')
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_security = models.CharField(max_length=10, choices=SMTP_SECURITY_CHOICES, default='starttls')
    smtp_username = models.CharField(max_length=255, blank=True)
    smtp_password = EncryptedCharField(max_length=500, blank=True)
    email_from_address = models.EmailField(blank=True)
    email_from_name = models.CharField(max_length=100, blank=True)

    def smtp_connection_settings(self):
        """(host, port, security) actually used -- Gmail's are fixed."""
        if self.smtp_provider == 'gmail':
            return self.GMAIL_HOST, self.GMAIL_PORT, 'starttls'
        return self.smtp_host, self.smtp_port, self.smtp_security

    # --- Confirmations ---
    # Which customers get payment/activation confirmation messages (incl.
    # staff recharge/extend/cash notices), as a comma list of service types.
    # Default PPPoE only: hotspot buyers already see the result on the
    # captive portal, and texting every KES 10 voucher-sized purchase costs
    # more in SMS than it's worth. 'both' counts as PPPoE.
    confirmation_service_types = models.CharField(max_length=50, default='pppoe', blank=True)
    # How confirmations go out (comma list of sms/whatsapp/email). WhatsApp
    # by default; when every chosen channel fails (e.g. WhatsApp not paired)
    # and the fallback is on, SMS is tried so the customer still hears back.
    confirmation_channels = models.CharField(max_length=30, default='whatsapp', blank=True)
    confirmation_sms_fallback = models.BooleanField(default=True)

    # --- Renewal (expiry) reminders ---
    # First reminder `reminder_days_before` days before expiry, then every
    # `reminder_every_days` days, plus one on the expiry day if enabled --
    # the defaults (3, 3, day-of) are the original "3 days out + day of".
    # Checked hourly; sent at `reminder_hour` (Nairobi time).
    reminder_enabled = models.BooleanField(default=True)
    reminder_days_before = models.PositiveSmallIntegerField(default=3)
    reminder_every_days = models.PositiveSmallIntegerField(default=3)
    reminder_on_expiry_day = models.BooleanField(default=True)
    reminder_hour = models.PositiveSmallIntegerField(default=8)
    reminder_service_types = models.CharField(max_length=50, default='pppoe,static', blank=True)
    reminder_channels = models.CharField(max_length=30, default='whatsapp', blank=True)
    reminder_sms_fallback = models.BooleanField(default=True)

    def reminder_offsets(self):
        """Days-before-expiry that get a reminder, e.g. [3, 0] or [7, 5, 3, 1, 0]."""
        every = max(1, self.reminder_every_days or 1)
        days = set(range(self.reminder_days_before, -1, -every)) if self.reminder_days_before else set()
        if self.reminder_on_expiry_day:
            days.add(0)
        return sorted(days, reverse=True)

    def reminder_channel_list(self):
        chosen = [c.strip() for c in (self.reminder_channels or '').split(',') if c.strip()]
        return [c for c in chosen if c in ('sms', 'whatsapp', 'email')] or ['sms']

    def reminder_service_type_list(self):
        types = [t.strip() for t in (self.reminder_service_types or '').split(',') if t.strip()]
        return types + (['both'] if 'pppoe' in types or 'hotspot' in types else [])

    def confirmation_channel_list(self):
        chosen = [c.strip() for c in (self.confirmation_channels or '').split(',') if c.strip()]
        return [c for c in chosen if c in ('sms', 'whatsapp', 'email')] or ['sms']

    def confirmations_enabled_for(self, service_type):
        allowed = {t.strip() for t in (self.confirmation_service_types or '').split(',') if t.strip()}
        if service_type == 'both':
            return bool(allowed & {'pppoe', 'hotspot'})
        return service_type in allowed

    # --- Superadmin emails (to every superuser with an email address) ---
    # Event emails: vouchers generated, new PPPoE customer, manual top-up.
    admin_event_emails = models.BooleanField(default=True)
    # Daily sales & revenue report, sent at 23:00 EAT.
    daily_report_enabled = models.BooleanField(default=True)

    # --- Staff alerts ---
    # A manager's number that gets a message whenever staff extend a
    # subscription or record cash on an account, so money-affecting manual
    # actions never happen unnoticed. Blank = off.
    # Admin contacts: everyone here gets every admin notification -- staff
    # alerts (extensions, cash), the daily report and the event notices.
    # Phones get a short text on each channel in admin_phone_channels;
    # emails get the full email. One entry per line (commas also accepted).
    # Superadmins' profile emails are always included as well.
    admin_phones = models.TextField(blank=True)
    admin_emails = models.TextField(blank=True)
    admin_phone_channels = models.CharField(max_length=30, default='sms', blank=True)

    @staticmethod
    def _split(value):
        import re
        return [v for v in (x.strip() for x in re.split(r'[\n,;]+', value or '')) if v]

    def phone_list(self):
        return list(dict.fromkeys(self._split(self.admin_phones)))

    def email_list(self):
        return list(dict.fromkeys(e.lower() for e in self._split(self.admin_emails)))

    def phone_channels(self):
        return [c for c in self._split(self.admin_phone_channels) if c in ('sms', 'whatsapp')]

    # Sales contacts: only get the "expired today" follow-up list (below), not
    # every admin notice. Same format as the admin contacts; phones use the
    # admin phone channels.
    sales_phones = models.TextField(blank=True)
    sales_emails = models.TextField(blank=True)
    # Daily list of customers whose plan ran out today and who haven't
    # renewed, sent to admin and sales contacts at expired_followup_hour.
    expired_followup_enabled = models.BooleanField(default=True)
    expired_followup_hour = models.PositiveSmallIntegerField(default=20)

    def sales_phone_list(self):
        return list(dict.fromkeys(self._split(self.sales_phones)))

    def sales_email_list(self):
        return list(dict.fromkeys(e.lower() for e in self._split(self.sales_emails)))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_settings'
        verbose_name = 'Notification Settings'
        verbose_name_plural = 'Notification Settings'

    def __str__(self):
        return 'Notification Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class NotificationLog(models.Model):
    """
    Audit trail for every outbound notification attempt across all
    channels. Also doubles as the dedup key for expiry reminders -- see
    apps.notifications.tasks.send_expiry_reminders -- rather than a boolean
    flag on Subscription, so there's a real record of what was sent, when,
    and to whom, useful for support ("did we text me?") and safe across
    renewals without needing a manual reset step.
    """
    CHANNEL_CHOICES = [
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('telegram', 'Telegram'),
        ('email', 'Email'),
    ]

    EVENT_TYPE_CHOICES = [
        ('expiry_reminder_3day', 'Expiry Reminder (3 days out)'),
        ('expiry_reminder_dayof', 'Expiry Reminder (day of)'),
        ('expiry_reminder', 'Renewal Reminder'),
        ('expired_followup', 'Expired Today (follow-up list)'),
        ('payment_confirmation', 'Payment Confirmation'),
        ('balance_credit', 'Balance Credit (payment applied to balance, no plan)'),
        ('welcome', 'Welcome Message'),
        ('payment_failed', 'Payment Failed'),
        ('suspension', 'Post-Expiry Suspension'),
        ('promo_broadcast', 'Promo Broadcast'),
        ('voucher_send', 'Voucher Code Sent'),
        ('staff_alert', 'Staff Alert (manual extension / cash)'),
        ('subscription_extended', 'Subscription Extended by Staff'),
        ('payment_reminder', 'Payment Reminder (sent by staff)'),
        ('daily_report', 'Daily Sales Report (superadmins)'),
        ('admin_event', 'Superadmin Event Email'),
        ('voucher_batch_sent', 'Vouchers sent to sales'),
        ('custom_message', 'Message sent by staff'),
    ]

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('error', 'Error'),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notification_logs'
    )
    subscription = models.ForeignKey(
        'billing.Subscription', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notification_logs'
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default='sms')
    event_type = models.CharField(max_length=25, choices=EVENT_TYPE_CHOICES)
    # Phone number (SMS/WhatsApp) or Telegram chat id -- recipient_phone's
    # max_length=15 was too narrow for the latter, so this superseded it
    # (see migration 0003, which copies existing values across and drops
    # the old column -- nothing in the frontend reads it directly).
    recipient = models.CharField(max_length=100, blank=True)
    message = models.TextField()

    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    provider_message_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    raw_response = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['subscription', 'event_type', 'created_at']),
            models.Index(fields=['customer', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.event_type} to {self.recipient} ({self.status})"



class MessageTemplate(models.Model):
    """
    Admin-editable wording. kind='system' rows override a built-in message
    (key = one of apps.notifications.templates.DEFAULTS; deleting the row
    restores the default). kind='promo' rows are saved promotional texts the
    broadcast form can start from. Bodies use {placeholders}; see
    apps.notifications.templates for the ones each message offers.
    """
    KIND_CHOICES = [('system', 'System message'), ('promo', 'Promotional')]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    key = models.CharField(max_length=40, blank=True)
    name = models.CharField(max_length=100)
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'message_templates'
        ordering = ['kind', 'name']
        constraints = [
            models.UniqueConstraint(fields=['key'], condition=models.Q(kind='system'), name='unique_system_template_key'),
        ]

    def __str__(self):
        return self.name
