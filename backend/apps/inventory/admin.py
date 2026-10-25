from django.contrib import admin

from .models import InventoryItem, InventoryPurchase, InventoryUsage


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'unit', 'current_stock', 'reorder_level', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'sku']


@admin.register(InventoryPurchase)
class InventoryPurchaseAdmin(admin.ModelAdmin):
    list_display = ['date', 'item', 'quantity', 'unit_cost', 'total_cost', 'supplier', 'recorded_by']
    list_filter = ['date']
    search_fields = ['supplier', 'notes']


@admin.register(InventoryUsage)
class InventoryUsageAdmin(admin.ModelAdmin):
    list_display = ['date', 'item', 'quantity', 'customer', 'reason', 'recorded_by']
    list_filter = ['date', 'reason']
    search_fields = ['notes']
