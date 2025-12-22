from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.payments import views

app_name = 'payments'

router = DefaultRouter()
router.register('requests', views.PaymentRequestViewSet, basename='payment-requests')

urlpatterns = [
    path('initiate/', views.initiate_payment, name='initiate'),
    path('callback/', views.mpesa_callback, name='callback'),
    path('status/<int:payment_request_id>/', views.payment_status, name='status'),
    path('', include(router.urls)),
]
