from django.urls import path
from apps.network.api.views import HotspotStatusView

urlpatterns = [
    path('hotspot/status/', HotspotStatusView.as_view(), name='hotspot-status'),
]
