from django.urls import path
from apps.network.views import SyncMikroTikView

urlpatterns = [
    # No manual sync endpoint needed as it moved to Django Admin
]
