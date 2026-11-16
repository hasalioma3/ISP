from django.urls import path

from . import views

urlpatterns = [
    path('settings/', views.NotificationSettingsView.as_view(), name='notification-settings'),
    path('test-send/', views.TestSendView.as_view(), name='notification-test-send'),
    path('whatsapp/status/', views.WhatsAppStatusView.as_view(), name='whatsapp-status'),
    path('promo-broadcast/', views.PromoBroadcastView.as_view(), name='promo-broadcast'),
    path('telegram/webhook/', views.TelegramWebhookView.as_view(), name='telegram-webhook'),
    path('templates/', views.MessageTemplatesView.as_view(), name='message-templates'),
    path('report/', views.NotificationReportView.as_view(), name='notification-report'),
    path('log/<int:pk>/resend/', views.NotificationResendView.as_view(), name='notification-resend'),
    path('daily-report/send-now/', views.DailyReportSendNowView.as_view(), name='daily-report-send-now'),
    path('templates/preview/', views.TemplatePreviewView.as_view(), name='message-template-preview'),
    path('templates/system/<str:key>/', views.SystemTemplateView.as_view(), name='system-template'),
    path('templates/promo/', views.PromoTemplateView.as_view(), name='promo-template-create'),
    path('templates/promo/<int:pk>/', views.PromoTemplateView.as_view(), name='promo-template'),
]
