from django.contrib import admin
from .models import BillingPlan, Subscription, Transaction, UsageRecord


@admin.register(BillingPlan)
class BillingPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'service_type', 'download_speed', 'upload_speed', 'price', 'duration_days', 'is_active']
    list_filter = ['service_type', 'is_active']
    search_fields = ['name', 'description']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['customer', 'plan', 'start_date', 'expiry_date', 'status', 'auto_renew']
    list_filter = ['status', 'auto_renew', 'created_at']
    search_fields = ['customer__username', 'customer__phone_number']
    raw_id_fields = ['customer', 'plan']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'customer', 'amount', 'payment_method', 'status', 'created_at']
    list_filter = ['payment_method', 'status', 'created_at']
    search_fields = ['transaction_id', 'customer__username', 'mpesa_receipt_number']
    raw_id_fields = ['customer', 'subscription']


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ['customer', 'start_time', 'end_time', 'total_gb', 'session_time_seconds']
    list_filter = ['start_time']
    search_fields = ['customer__username', 'session_id']
    raw_id_fields = ['customer', 'subscription']


from .models import Voucher, VoucherBatch


@admin.register(VoucherBatch)
class VoucherBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'quantity', 'value', 'generated_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['note']


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ['code', 'amount', 'status', 'batch', 'used_by', 'used_at', 'expiry_date']
    list_filter = ['status', 'created_at', 'amount']
    search_fields = ['code', 'batch__id']
    raw_id_fields = ['batch', 'used_by']
