from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from apps.network.services.network_automation import network_automation

from rest_framework_simplejwt.authentication import JWTAuthentication

# SyncMikroTikView removed - migrated to Django Admin Router actions
