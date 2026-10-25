from django.db import models

from apps.customers.models import Customer


class CPEDevice(models.Model):
    """
    A customer-premises router (Huawei/Tenda/TP-Link) managed remotely via
    TR-069/CWMP through the GenieACS sidecar (see
    apps.tr069.services.acs_service). Mirrors the shape of
    apps.network.models.PPPoESecret/HotspotUser -- a customer's thing on an
    external device, with sync bookkeeping -- except there's no FK to
    Router: a CPE device is reached directly via the ACS, not through a
    MikroTik router.

    `customer` is nullable because a device can appear here (via GenieACS
    INFORM) before being matched to a customer -- see the two registration
    paths in apps.tr069.views (pre-register by serial number, or discover
    then link).
    """
    BRAND_CHOICES = [
        ('huawei', 'Huawei'),
        ('tenda', 'Tenda'),
        ('tplink', 'TP-Link'),
        ('other', 'Other'),
    ]

    customer = models.OneToOneField(
        Customer, on_delete=models.CASCADE, null=True, blank=True,
        related_name='cpe_device'
    )

    # GenieACS's own device ID (typically OUI-ProductClass-SerialNumber) --
    # the key used for every NBI call, so this is required and unique the
    # moment a device is known to us at all (pre-registered or discovered).
    genieacs_device_id = models.CharField(max_length=255, unique=True)
    serial_number = models.CharField(max_length=100, db_index=True)
    brand = models.CharField(max_length=20, choices=BRAND_CHOICES, default='other')
    manufacturer = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    software_version = models.CharField(max_length=100, blank=True)
    mac_address = models.CharField(max_length=17, blank=True)

    # Cached from the last successful parameter read -- not live. Treat as
    # "as of last_inform", same staleness caveat as MikroTik ActiveSession.
    wifi_ssid = models.CharField(max_length=100, blank=True)

    last_inform = models.DateTimeField(null=True, blank=True)
    # Derived by apps.tr069.tasks.sync_cpe_devices from last_inform
    # recency, not written anywhere else.
    is_online = models.BooleanField(default=False)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cpe_devices'
        ordering = ['-last_inform']

    def __str__(self):
        who = self.customer.username if self.customer_id else 'unlinked'
        return f"{self.get_brand_display()} {self.serial_number} ({who})"
