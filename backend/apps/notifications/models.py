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
    ]

    EVENT_TYPE_CHOICES = [
        ('expiry_reminder_3day', 'Expiry Reminder (3 days out)'),
        ('expiry_reminder_dayof', 'Expiry Reminder (day of)'),
        ('payment_confirmation', 'Payment Confirmation'),
        ('balance_credit', 'Balance Credit (payment applied to balance, no plan)'),
        ('welcome', 'Welcome Message'),
        ('payment_failed', 'Payment Failed'),
        ('suspension', 'Post-Expiry Suspension'),
        ('promo_broadcast', 'Promo Broadcast'),
        ('voucher_send', 'Voucher Code Sent'),
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
