from django.contrib import admin

from .models import CPEDevice


@admin.register(CPEDevice)
class CPEDeviceAdmin(admin.ModelAdmin):
    list_display = ['serial_number', 'brand', 'customer', 'is_online', 'last_inform']
    list_filter = ['brand', 'is_online']
    search_fields = ['serial_number', 'genieacs_device_id', 'customer__username']
    raw_id_fields = ['customer']
