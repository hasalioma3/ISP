from django.contrib import admin
from .models import PaymentRequest, PaymentCallback


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'amount', 'status', 'merchant_request_id', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['phone_number', 'merchant_request_id', 'checkout_request_id']
    raw_id_fields = ['customer', 'plan']


@admin.register(PaymentCallback)
class PaymentCallbackAdmin(admin.ModelAdmin):
    list_display = ['merchant_request_id', 'result_code', 'mpesa_receipt_number', 'processed', 'created_at']
    list_filter = ['processed', 'result_code', 'created_at']
    search_fields = ['merchant_request_id', 'checkout_request_id', 'mpesa_receipt_number']
    raw_id_fields = ['payment_request']
