from django.urls import path

from apps.invoicing import views

urlpatterns = [
    path('settings/', views.InvoiceSettingsView.as_view(), name='invoice-settings'),
    path('settings/etims/', views.EtimsActionView.as_view(), name='invoice-etims'),
    path('templates/preview/', views.TemplatePreviewView.as_view(), name='invoice-template-preview'),
    path('payments/', views.InvoiceablePaymentsView.as_view(), name='invoiceable-payments'),
    path('invoices/', views.InvoiceListView.as_view(), name='invoices'),
    path('invoices/from-transaction/', views.InvoiceFromTransactionView.as_view(), name='invoice-from-transaction'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),
    path('invoices/<int:pk>/pdf/', views.InvoicePdfView.as_view(), name='invoice-pdf'),
    path('invoices/<int:pk>/action/', views.InvoiceActionView.as_view(), name='invoice-action'),
    path('mine/', views.MyInvoicesView.as_view(), name='my-invoices'),
    path('mine/<int:pk>/pdf/', views.MyInvoicePdfView.as_view(), name='my-invoice-pdf'),
]
