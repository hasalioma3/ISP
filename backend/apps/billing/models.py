from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.customers.models import Customer


class BillingPlan(models.Model):
    """
    Billing plans for PPPoE and Hotspot services
    """
    SERVICE_TYPE_CHOICES = [
        ('pppoe', 'PPPoE'),
        ('hotspot', 'Hotspot'),
    ]
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    service_type = models.CharField(max_length=10, choices=SERVICE_TYPE_CHOICES)
    
    # Speed Configuration (in Mbps)
    download_speed = models.IntegerField(help_text="Download speed in Mbps")
    upload_speed = models.IntegerField(help_text="Upload speed in Mbps")
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='KES')
    
    # Duration
    # Duration
    duration_value = models.IntegerField(default=30, help_text="Duration value (e.g., 30 for 30 days)")
    DURATION_UNIT_CHOICES = [
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('months', 'Months'),
    ]
    duration_unit = models.CharField(
        max_length=10, 
        choices=DURATION_UNIT_CHOICES, 
        default='days',
        help_text="Unit of time for the duration"
    )
    
    # Legacy field - keeping for backward compatibility in codebase until fully migrated
    duration_days = models.IntegerField(default=30, help_text="Legacy: Subscription duration in days")
    
    # Data Limits (Optional)
    data_limit_gb = models.IntegerField(
        null=True,
        blank=True,
        help_text="Data limit in GB (null for unlimited)"
    )
    
    # MikroTik Profile Names
    mikrotik_profile = models.CharField(
        max_length=100,
        help_text="MikroTik profile name for this plan"
    )
    
    # Associated Routers
    routers = models.ManyToManyField(
        'network.Router', 
        blank=True,
        related_name='billing_plans',
        help_text="Routers where this plan should be provisioned"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'billing_plans'
        ordering = ['price']
        verbose_name = _('Billing Plan')
        verbose_name_plural = _('Billing Plans')
    
    def __str__(self):
        return f"{self.name} - {self.download_speed}/{self.upload_speed} Mbps - KES {self.price}"


class Subscription(models.Model):
    """
    Customer subscriptions to billing plans
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    plan = models.ForeignKey(
        BillingPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )
    
    # Subscription Period
    start_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField()
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    # Auto-renewal
    auto_renew = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'subscriptions'
        ordering = ['-created_at']
        verbose_name = _('Subscription')
        verbose_name_plural = _('Subscriptions')
    
    def __str__(self):
        return f"{self.customer.username} - {self.plan.name} - {self.status}"
    
    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expiry_date
    
    @property
    def days_remaining(self):
        from django.utils import timezone
        delta = self.expiry_date - timezone.now()
        return max(0, delta.days)


class Transaction(models.Model):
    """
    Payment transactions
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('other', 'Other'),
    ]
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    
    # Transaction Details
    transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='KES')
    
    # Payment Method
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        default='mpesa'
    )
    
    # M-Pesa Specific Fields
    mpesa_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    mpesa_phone_number = models.CharField(max_length=15, blank=True, null=True)
    mpesa_transaction_date = models.DateTimeField(blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']
        verbose_name = _('Transaction')
        verbose_name_plural = _('Transactions')
    
    def __str__(self):
        return f"{self.transaction_id} - {self.customer.username} - KES {self.amount}"


class UsageRecord(models.Model):
    """
    Track customer data and time usage
    """
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='usage_records'
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name='usage_records'
    )
    
    # Usage Data
    upload_bytes = models.BigIntegerField(default=0)
    download_bytes = models.BigIntegerField(default=0)
    session_time_seconds = models.IntegerField(default=0)
    
    # Real-time Speed (Snapshot)
    upload_speed_mbps = models.FloatField(default=0.0)
    download_speed_mbps = models.FloatField(default=0.0)
    
    # Session Information
    session_id = models.CharField(max_length=100, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    
    # Network Information
    nas_ip_address = models.GenericIPAddressField(blank=True, null=True)
    framed_ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'usage_records'
        ordering = ['-start_time']
        verbose_name = _('Usage Record')
        verbose_name_plural = _('Usage Records')
    
    def __str__(self):
        return f"{self.customer.username} - {self.start_time}"
    
    @property
    def total_bytes(self):
        return self.upload_bytes + self.download_bytes
    
    @property
    def total_gb(self):
        return round(self.total_bytes / (1024 ** 3), 2)


class VoucherBatch(models.Model):
    """
    Groups of generated vouchers
    """
    created_at = models.DateTimeField(auto_now_add=True)
    quantity = models.IntegerField()
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    plan = models.ForeignKey(
        'billing.BillingPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voucher_batches'
    )
    generated_by = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_batches'
    )
    note = models.CharField(max_length=255, blank=True)
    
    class Meta:
        db_table = 'voucher_batches'
        ordering = ['-created_at']
        verbose_name = _('Voucher Batch')
        verbose_name_plural = _('Voucher Batches')
    
    def __str__(self):
        return f"Batch #{self.id} - {self.quantity} x {self.value}"


class Voucher(models.Model):
    """
    Prepaid vouchers for account top-up
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('used', 'Used'),
        ('expired', 'Expired'),
    ]
    
    batch = models.ForeignKey(
        VoucherBatch,
        on_delete=models.CASCADE,
        related_name='vouchers'
    )
    plan = models.ForeignKey(
        'billing.BillingPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vouchers'
    )
    code = models.CharField(max_length=20, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='active'
    )
    
    # Redemption Details
    used_by = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_vouchers'
    )
    used_at = models.DateTimeField(null=True, blank=True)
    
    expiry_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'vouchers'
        ordering = ['-created_at']
        verbose_name = _('Voucher')
        verbose_name_plural = _('Vouchers')
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.amount}"
