from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Customer(AbstractUser):
    """
    Custom User model for ISP customers
    """
    SERVICE_TYPE_CHOICES = [
        ('pppoe', 'PPPoE'),
        ('hotspot', 'Hotspot'),
        ('both', 'Both'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
        ('pending', 'Pending'),
    ]
    
    # Personal Information
    phone_number = models.CharField(max_length=15, unique=True)
    id_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True)
    
    # Service Information
    service_type = models.CharField(
        max_length=10,
        choices=SERVICE_TYPE_CHOICES,
        default='pppoe'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # PPPoE Credentials
    pppoe_username = models.CharField(max_length=100, unique=True, blank=True, null=True)
    pppoe_password = models.CharField(max_length=100, blank=True, null=True)
    
    # Hotspot Credentials
    hotspot_username = models.CharField(max_length=100, unique=True, blank=True, null=True)
    hotspot_password = models.CharField(max_length=100, blank=True, null=True)
    
    # Account Information
    account_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Metadata
    notes = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'customers'
        ordering = ['-created_at']
        verbose_name = _('Customer')
        verbose_name_plural = _('Customers')
    
    def __str__(self):
        return f"{self.username} - {self.phone_number}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
