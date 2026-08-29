from django.db import models

from apps.customers.models import Customer


class NotificationLog(models.Model):
    """
    Audit trail for every outbound notification attempt (SMS for now).
    Also doubles as the dedup key for expiry reminders -- see
    apps.notifications.tasks.send_expiry_reminders -- rather than a boolean
    flag on Subscription, so there's a real record of what was sent, when,
    and to what number, useful for support ("did we text me?") and safe
    across renewals without needing a manual reset step.
    """
    CHANNEL_CHOICES = [
        ('sms', 'SMS'),
    ]

    EVENT_TYPE_CHOICES = [
        ('expiry_reminder_3day', 'Expiry Reminder (3 days out)'),
        ('expiry_reminder_dayof', 'Expiry Reminder (day of)'),
        ('payment_confirmation', 'Payment Confirmation'),
        ('balance_credit', 'Balance Credit (payment applied to balance, no plan)'),
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
    recipient_phone = models.CharField(max_length=15)
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
        return f"{self.event_type} to {self.recipient_phone} ({self.status})"
