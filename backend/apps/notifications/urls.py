from django.urls import path

from . import views

urlpatterns = [
    path('settings/', views.NotificationSettingsView.as_view(), name='notification-settings'),
    path('test-send/', views.TestSendView.as_view(), name='notification-test-send'),
    path('whatsapp/status/', views.WhatsAppStatusView.as_view(), name='whatsapp-status'),
    path('promo-broadcast/', views.PromoBroadcastView.as_view(), name='promo-broadcast'),
    path('telegram/webhook/', views.TelegramWebhookView.as_view(), name='telegram-webhook'),
]
