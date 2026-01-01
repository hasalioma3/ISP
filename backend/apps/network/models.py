from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.customers.models import Customer


class Router(models.Model):
    """
    MikroTik Router inventory
    """
    name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(unique=True)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    port = models.IntegerField(default=8728)
    use_ssl = models.BooleanField(default=False)
    
    # Status
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(blank=True, null=True)
    
    # Metadata
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'routers'
        ordering = ['name']
        verbose_name = _('Router')
        verbose_name_plural = _('Routers')
    
    def __str__(self):
        return f"{self.name} - {self.ip_address}"


class PPPoESecret(models.Model):
    """
    PPPoE user credentials on MikroTik
    """
    STATUS_CHOICES = [
        ('enabled', 'Enabled'),
        ('disabled', 'Disabled'),
    ]
    
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name='pppoe_secret'
    )
    router = models.ForeignKey(
        Router,
        on_delete=models.CASCADE,
        related_name='pppoe_secrets'
    )
    
    # PPPoE Credentials
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=100)
    
    # Profile & Speed
    profile = models.CharField(max_length=100)
    local_address = models.GenericIPAddressField(blank=True, null=True)
    remote_address = models.GenericIPAddressField(blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='enabled')
    
    # Sync Status
    synced_to_router = models.BooleanField(default=False)
    last_sync = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'pppoe_secrets'
        ordering = ['username']
        verbose_name = _('PPPoE Secret')
        verbose_name_plural = _('PPPoE Secrets')
    
    def __str__(self):
        return f"{self.username} - {self.profile}"


class HotspotUser(models.Model):
    """
    Hotspot user credentials on MikroTik
    """
    STATUS_CHOICES = [
        ('enabled', 'Enabled'),
        ('disabled', 'Disabled'),
    ]
    
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name='hotspot_user'
    )
    router = models.ForeignKey(
        Router,
        on_delete=models.CASCADE,
        related_name='hotspot_users'
    )
    
    # Hotspot Credentials
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=100)
    
    # Profile & Limits
    profile = models.CharField(max_length=100)
    mac_address = models.CharField(max_length=17, blank=True, null=True)
    
    # Time & Data Limits
    uptime_limit = models.CharField(max_length=50, blank=True, null=True)
    bytes_limit = models.BigIntegerField(blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='enabled')
    
    # Sync Status
    synced_to_router = models.BooleanField(default=False)
    last_sync = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hotspot_users'
        ordering = ['username']
        verbose_name = _('Hotspot User')
        verbose_name_plural = _('Hotspot Users')
    
    def __str__(self):
        return f"{self.username} - {self.profile}"


class ActiveSession(models.Model):
    """
    Current active network sessions
    """
    SESSION_TYPE_CHOICES = [
        ('pppoe', 'PPPoE'),
        ('hotspot', 'Hotspot'),
    ]
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='active_sessions'
    )
    router = models.ForeignKey(
        Router,
        on_delete=models.CASCADE,
        related_name='active_sessions'
    )
    
    # Session Details
    session_type = models.CharField(max_length=10, choices=SESSION_TYPE_CHOICES)
    session_id = models.CharField(max_length=100)
    username = models.CharField(max_length=100)
    
    # Network Information
    ip_address = models.GenericIPAddressField()
    mac_address = models.CharField(max_length=17, blank=True, null=True)
    
    # Usage Statistics
    upload_bytes = models.BigIntegerField(default=0)
    download_bytes = models.BigIntegerField(default=0)
    uptime_seconds = models.IntegerField(default=0)
    
    # Timestamps
    start_time = models.DateTimeField()
    last_update = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'active_sessions'
        ordering = ['-start_time']
        verbose_name = _('Active Session')
        verbose_name_plural = _('Active Sessions')
        unique_together = ['router', 'session_id']
    
    def __str__(self):
        return f"{self.username} - {self.ip_address} - {self.session_type}"
    
    @property
    def total_bytes(self):
        return self.upload_bytes + self.download_bytes
    
    @property
    def total_gb(self):
        return round(self.total_bytes / (1024 ** 3), 2)


class RouterInterfaceStat(models.Model):
    """
    Real-time interface statistics (e.g., bridge counters)
    """
    router = models.ForeignKey(
        Router,
        on_delete=models.CASCADE,
        related_name='interface_stats'
    )
    interface_name = models.CharField(max_length=100)
    
    # Real-time Rates (bps)
    tx_bps = models.BigIntegerField(default=0)  # Transmit (Download for clients mostly)
    rx_bps = models.BigIntegerField(default=0)  # Receive (Upload for clients mostly)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'router_interface_stats'
        unique_together = ['router', 'interface_name']
        verbose_name = _('Router Interface Stat')
        verbose_name_plural = _('Router Interface Stats')

    def __str__(self):
        return f"{self.router.name} - {self.interface_name}"
