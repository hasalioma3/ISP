from django.urls import path

from apps.notifications import views

urlpatterns = [
    path('telegram/webhook/', views.telegram_webhook, name='telegram-webhook'),
    path('test/', views.send_test, name='notification-test'),
]
