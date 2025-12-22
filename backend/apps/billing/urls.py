from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.billing import views

app_name = 'billing'

router = DefaultRouter()
router.register('plans', views.BillingPlanViewSet, basename='plans')
router.register('subscriptions', views.SubscriptionViewSet, basename='subscriptions')
router.register('transactions', views.TransactionViewSet, basename='transactions')
router.register('usage', views.UsageRecordViewSet, basename='usage')

urlpatterns = [
    path('', include(router.urls)),
]
