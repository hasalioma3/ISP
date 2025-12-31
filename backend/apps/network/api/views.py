from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.utils import timezone
from apps.network.models import HotspotUser
from apps.billing.models import Subscription

class HotspotStatusView(APIView):
    """
    Check if a MAC address has an active subscription and return login credentials.
    Public endpoint (allowed in Walled Garden).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        mac_address = request.query_params.get('mac')
        if not mac_address:
            return Response({'error': 'MAC address required'}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize MAC
        mac_address = mac_address.upper()

        # Find HotspotUser by MAC (assuming we store the MAC somewhere, usually in HotspotUser or Customer)
        # In our model HotspotUser has mac_address field? Let's check models.py
        # Current HotspotUser model (from previous file views): 
        # class HotspotUser(models.Model): ... mac_address = models.CharField(...)
        
        user = HotspotUser.objects.filter(mac_address=mac_address).first()
        
        if not user:
            # Try to find by customer subscription history? 
            # Or maybe they are a new user.
            return Response({'active': False, 'message': 'User not found'}, status=status.HTTP_200_OK)

        # Check for active subscription
        # This assumes HotspotUser is linked to a Customer who has Subscriptions
        active_sub = Subscription.objects.filter(
            customer=user.customer,
            status='active',
            expiry_date__gt=timezone.now()
        ).exists()

        if active_sub:
            return Response({
                'active': True,
                'username': user.username,
                'password': user.password, # In a real app, maybe send a token or use CHAP? But standard Hotspot uses cleartext/CHAP.
                'profile': user.profile
            })
        else:
            return Response({'active': False, 'message': 'No active subscription'}, status=status.HTTP_200_OK)
