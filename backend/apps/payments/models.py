from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.customers.models import Customer
from apps.billing.models import BillingPlan


class PaymentRequest(models.Model):
    """
    M-Pesa STK Push payment requests
    """
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
        ('cancelled', 'Cancelled'),
    ]
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='payment_requests'
    )
    plan = models.ForeignKey(
        BillingPlan,
        on_delete=models.PROTECT,
        related_name='payment_requests'
    )
    
    # M-Pesa Request Details
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    account_reference = models.CharField(max_length=100)
    transaction_desc = models.CharField(max_length=100)
    
    # M-Pesa Response Fields
    merchant_request_id = models.CharField(max_length=100, blank=True, null=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, null=True)
    response_code = models.CharField(max_length=10, blank=True, null=True)
    response_description = models.TextField(blank=True, null=True)
    customer_message = models.TextField(blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='initiated')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_requests'
        ordering = ['-created_at']
        verbose_name = _('Payment Request')
        verbose_name_plural = _('Payment Requests')
    
    def __str__(self):
        return f"{self.phone_number} - KES {self.amount} - {self.status}"


class C2BPayment(models.Model):
    """
    M-Pesa C2B (Customer-to-Business) payments -- customers paying the
    paybill directly from their M-Pesa menu, bypassing the portal/STK push
    flow entirely. Safaricom posts these to our ConfirmationURL after the
    money has already moved, so every record here represents a real
    completed payment regardless of whether we could match/activate it.
    """
    STATUS_CHOICES = [
        ('activated', 'Activated'),        # matched customer + plan, subscription created
        ('matched_no_plan', 'Matched, No Plan'),  # matched customer, amount didn't match any plan price
        ('unmatched', 'Unmatched'),        # no customer found for the account number entered
        ('error', 'Error'),                # matched but activation itself failed
    ]

    # Raw Safaricom C2B payload fields (see Daraja C2B Confirmation API)
    transaction_id = models.CharField(max_length=100, unique=True)  # TransID
    transaction_type = models.CharField(max_length=50, blank=True)
    transaction_time = models.DateTimeField(blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    business_short_code = models.CharField(max_length=20, blank=True)
    bill_ref_number = models.CharField(max_length=100, blank=True)  # account number entered
    invoice_number = models.CharField(max_length=100, blank=True)
    org_account_balance = models.CharField(max_length=50, blank=True)
    third_party_trans_id = models.CharField(max_length=100, blank=True)
    msisdn = models.CharField(max_length=15, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    # Matching/activation outcome
    matched_customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='c2b_payments'
    )
    subscription = models.ForeignKey(
        'billing.Subscription', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='c2b_payments'
    )
    linked_transaction = models.ForeignKey(
        'billing.Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='c2b_payment'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unmatched')
    notes = models.TextField(blank=True)

    raw_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'c2b_payments'
        ordering = ['-created_at']
        verbose_name = _('C2B Payment')
        verbose_name_plural = _('C2B Payments')

    def __str__(self):
        return f"{self.msisdn} - KES {self.amount} - {self.status}"


class PaymentCallback(models.Model):
    """
    M-Pesa payment callbacks
    """
    payment_request = models.ForeignKey(
        PaymentRequest,
        on_delete=models.CASCADE,
        related_name='callbacks',
        null=True,
        blank=True
    )
    
    # Callback Data
    merchant_request_id = models.CharField(max_length=100)
    checkout_request_id = models.CharField(max_length=100)
    result_code = models.CharField(max_length=10)
    result_desc = models.TextField()
    
    # Transaction Details (if successful)
    mpesa_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    transaction_date = models.DateTimeField(blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Raw callback data
    raw_data = models.JSONField()
    
    # Processing Status
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_callbacks'
        ordering = ['-created_at']
        verbose_name = _('Payment Callback')
        verbose_name_plural = _('Payment Callbacks')
    
    def __str__(self):
        return f"{self.merchant_request_id} - {self.result_code}"
