from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationLog(models.Model):
    """
    Audit trail of every outbound notification (SMS / WhatsApp / Telegram).
    Rows are created in 'pending' state and updated by the Celery task that
    actually performs the send, so the admin can see failures and retry them.
    """
    CHANNEL_CHOICES = [
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('telegram', 'Telegram'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    AUDIENCE_CHOICES = [
        ('customer', 'Customer'),
        ('admin', 'Admin'),
    ]

    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        help_text="Customer this notification relates to (null for admin broadcasts)"
    )
    audience = models.CharField(max_length=10, choices=AUDIENCE_CHOICES, default='customer')
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    recipient = models.CharField(
        max_length=100,
        help_text="Phone number (SMS/WhatsApp) or chat ID (Telegram)"
    )
    event = models.CharField(max_length=50, db_index=True)
    message = models.TextField()

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', db_index=True)
    error = models.TextField(blank=True)
    provider = models.CharField(max_length=30, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']
        verbose_name = _('Notification Log')
        verbose_name_plural = _('Notification Logs')

    def __str__(self):
        return f"[{self.channel}] {self.event} -> {self.recipient} ({self.status})"
