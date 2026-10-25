from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'tr069'

router = DefaultRouter()
router.register('devices', views.CPEDeviceViewSet, basename='cpe-device')

urlpatterns = [
    path('', include(router.urls)),
]
