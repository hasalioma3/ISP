from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.network import views
from apps.network.api.views import HotspotStatusView

router = DefaultRouter()
router.register(r'routers', views.RouterViewSet, basename='routers')

urlpatterns = [
    path('', include(router.urls)),
    path('hotspot/status/', HotspotStatusView.as_view(), name='hotspot-status'),
]
