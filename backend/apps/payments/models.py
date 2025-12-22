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
