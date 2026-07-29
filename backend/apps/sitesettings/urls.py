from django.urls import path
from .views import SiteSettingsView

urlpatterns = [
    path('site/', SiteSettingsView.as_view(), name='site-settings'),
]
