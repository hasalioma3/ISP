from django.urls import path
from .views import TenantConfigView, TenantBrandingView

urlpatterns = [
    path('config/', TenantConfigView.as_view(), name='tenant-config'),
    path('branding/', TenantBrandingView.as_view(), name='tenant-branding'),
]
