"""
URL configuration for isp_billing project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API endpoints
    path('api/core/', include('apps.core.urls')),
    path('api/customers/', include('apps.customers.urls')),
    path('api/billing/', include('apps.billing.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/analytics/', include('apps.analytics.urls')),
    path('api/network/', include('apps.network.urls')),

    # React Frontend (Catch-all)
    re_path(r'^.*$', TemplateView.as_view(template_name='index.html')),
]
