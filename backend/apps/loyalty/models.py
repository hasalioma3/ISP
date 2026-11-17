from decimal import Decimal

from django.conf import settings
from django.db import models


class LoyaltySettings(models.Model):
    """
    Singleton (pk=1). Customers earn points on what they pay (M-Pesa, cash,
    bank -- not purchases funded from their account balance, which was
    already earned on when it came in) and redeem them as KES credited to
    their account balance, which then pays for a renewal like any other
    balance. Off until an admin turns it on.
    """
    enabled = models.BooleanField(default=False)
    # Which customers take part: any of pppoe, hotspot, static.
    service_types = models.CharField(max_length=40, default='pppoe,static')
    # 1 point for every `kes_per_point` shillings paid (fractions dropped
    # per payment). E.g. 100 -> a KES 2,500 payment earns 25 points.
    kes_per_point = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('100'))
    # What one point is worth when redeemed, in KES.
    point_value_kes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1'))
    min_redeem_points = models.PositiveIntegerField(default=100)
    # Let customers redeem from their own dashboard (else staff only).
    allow_self_redeem = models.BooleanField(default=True)
    # Points expire this many months after they were earned; 0 = never.
    expiry_months = models.PositiveSmallIntegerField(default=0)
    # Bonus points on a customer's first payment ever (0 = none).
    welcome_bonus = models.PositiveIntegerField(default=0)
    notify_earn = models.BooleanField(default=True)
    notify_redeem = models.BooleanField(default=True)
    channels = models.CharField(max_length=30, default='sms')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loyalty_settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def service_type_list(self):
        types = [t.strip() for t in (self.service_types or '').split(',') if t.strip()]
        return types + (['both'] if 'pppoe' in types or 'hotspot' in types else [])

    def channel_list(self):
        return [c.strip() for c in (self.channels or '').split(',') if c.strip() in ('sms', 'whatsapp', 'email')] or ['sms']


class LoyaltyTransaction(models.Model):
    """Append-only points ledger; a customer's balance is the sum of `points`."""
    KIND_CHOICES = [
        ('earn', 'Earned'),
        ('bonus', 'Bonus'),
        ('redeem', 'Redeemed'),
        ('adjust', 'Adjustment'),
        ('expire', 'Expired'),
    ]

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='loyalty_entries')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    points = models.IntegerField()
    balance_after = models.IntegerField(default=0)
    # The payment it was earned on -- unique, so a re-saved transaction
    # never earns twice.
    transaction = models.OneToOneField('billing.Transaction', null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name='loyalty_entry')
    kes_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'loyalty_transactions'
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['customer', 'created_at'])]
