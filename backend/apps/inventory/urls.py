from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('items', views.InventoryItemViewSet, basename='inventory-items')
router.register('purchases', views.InventoryPurchaseViewSet, basename='inventory-purchases')
router.register('usages', views.InventoryUsageViewSet, basename='inventory-usages')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', views.InventoryDashboardView.as_view(), name='inventory-dashboard'),
]
