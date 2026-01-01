from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from apps.network.services.network_automation import network_automation

from rest_framework_simplejwt.authentication import JWTAuthentication

from rest_framework import viewsets
from apps.network.models import Router
from apps.network.serializers.router import RouterSerializer

class RouterViewSet(viewsets.ModelViewSet):
    """
    Manage routers
    """
    queryset = Router.objects.all()
    serializer_class = RouterSerializer
    permission_classes = [IsAdminUser]
