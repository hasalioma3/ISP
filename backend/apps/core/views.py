from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from .models import TenantConfig
from .serializers import TenantConfigSerializer, TenantBrandingSerializer

class TenantConfigView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update tenant configuration.
    Only authenticated users (admins) can update.
    """
    serializer_class = TenantConfigSerializer
    permission_classes = [permissions.IsAuthenticated] # Or IsAdminUser
    parser_classes = (MultiPartParser, FormParser)

    def get_object(self):
        return TenantConfig.load()

class TenantBrandingView(APIView):
    """
    Public view for branding items (Logo, Name, etc.)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        config = TenantConfig.load()
        serializer = TenantBrandingSerializer(config, context={'request': request})
        return Response(serializer.data)
