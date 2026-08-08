from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.payments import views

app_name = 'payments'

router = DefaultRouter()
router.register('requests', views.PaymentRequestViewSet, basename='payment-requests')

urlpatterns = [
    path('initiate/', views.initiate_payment, name='initiate'),
    path('reactivate/', views.reactivate_session, name='reactivate'),
    path('callback/', views.mpesa_callback, name='callback'),
    path('c2b/<str:token>/validation/', views.c2b_validation, name='c2b-validation'),
    path('c2b/<str:token>/confirmation/', views.c2b_confirmation, name='c2b-confirmation'),
    path('status/<int:payment_request_id>/', views.payment_status, name='status'),
    path('c2b/<int:payment_id>/assign/', views.assign_c2b_payment, name='c2b-assign'),
    path('', include(router.urls)),
]
