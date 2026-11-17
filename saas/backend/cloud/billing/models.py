"""
Money. Every shilling an ISP's customers pay lands on the platform's
shortcode, so this app keeps a ledger per ISP of what we hold for them:

    + collection          a customer payment (STK verified, or C2B)
    - collection_fee      the platform's cut of a payment (if configured)
    - invoice             the monthly platform bill, paid from the balance
    - settlement          money sent to the ISP (B2B/B2C), held when submitted
    - settlement_fee      the payout charge
    + settlement_reversal a failed payout, put back
    +/- adjustment        manual corrections by a platform admin

The balance is the sum. Entries are append-only and idempotent on
(kind, reference), so a duplicated callback or a re-run task can never
double-count.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models


class Collection(models.Model):
    """A customer payment received on the platform shortcode for some ISP."""
    SOURCES = [('stk', 'STK push'), ('c2b', 'Paybill / till')]
    receipt = models.CharField(max_length=40, unique=True)  # M-Pesa receipt (TransID)
    tenant = models.ForeignKey('tenants.Tenant', null=True, blank=True, on_delete=models.PROTECT, related_name='collections')
    source = models.CharField(max_length=5, choices=SOURCES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    phone = models.CharField(max_length=100, blank=True)
    account = models.CharField(max_length=100, blank=True)  # BillRefNumber / AccountReference as typed
    payer_name = models.CharField(max_length=150, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    routed_by = models.CharField(max_length=20, blank=True)  # callback / prefix / username / phone / manual
    verified = models.BooleanField(default=False)
    verify_error = models.CharField(max_length=255, blank=True)
    verify_attempts = models.PositiveSmallIntegerField(default=0)
    forwarded = models.BooleanField(default=False)
    forward_error = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'collections'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.receipt} KES {self.amount}'


class Invoice(models.Model):
    STATUSES = [('open', 'Unpaid'), ('paid', 'Paid'), ('void', 'Void')]
    number = models.CharField(max_length=30, unique=True)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT, related_name='invoices')
    period_start = models.DateField()
    period_end = models.DateField()  # inclusive
    plan_name = models.CharField(max_length=100)
    subscriber_count = models.PositiveIntegerField(default=0)
    count_detail = models.JSONField(default=dict, blank=True)
    lines = models.JSONField(default=list)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=5, choices=STATUSES, default='open', db_index=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_via = models.CharField(max_length=10, blank=True)  # balance / mpesa / manual
    payment_ref = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'invoices'
        ordering = ['-issued_at']
        unique_together = [('tenant', 'period_start')]

    def __str__(self):
        return self.number


class Settlement(models.Model):
    STATUSES = [('pending_approval', 'Awaiting approval'), ('queued', 'Queued'), ('processing', 'Sent to M-Pesa'),
                ('succeeded', 'Paid out'), ('failed', 'Failed'), ('cancelled', 'Cancelled')]
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT, related_name='settlements')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    method = models.CharField(max_length=10)
    destination = models.CharField(max_length=20)
    account_ref = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default='pending_approval', db_index=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    originator_id = models.CharField(max_length=64, unique=True)
    conversation_id = models.CharField(max_length=100, blank=True, db_index=True)
    mpesa_receipt = models.CharField(max_length=40, blank=True)
    result_code = models.CharField(max_length=10, blank=True)
    result_desc = models.TextField(blank=True)
    raw_result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'settlements'
        ordering = ['-created_at']


class LedgerEntry(models.Model):
    KINDS = [('collection', 'Customer payment'), ('collection_fee', 'Collection fee'), ('invoice', 'Platform invoice'),
             ('settlement', 'Payout'), ('settlement_fee', 'Payout fee'), ('settlement_reversal', 'Payout reversed'),
             ('adjustment', 'Adjustment')]
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT, related_name='ledger')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=20, choices=KINDS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # signed: + we owe the ISP more
    reference = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    collection = models.ForeignKey(Collection, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    settlement = models.ForeignKey(Settlement, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        db_table = 'ledger_entries'
        ordering = ['-created_at', '-id']
        unique_together = [('kind', 'reference')]


class PlatformPayment(models.Model):
    """An ISP paying a platform invoice directly by STK push."""
    STATUSES = [('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed')]
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    phone = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    checkout_request_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=10, choices=STATUSES, default='pending')
    receipt = models.CharField(max_length=40, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'platform_payments'
        ordering = ['-created_at']
