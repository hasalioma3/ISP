from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from apps.customers.models import Customer
from apps.customers.serializers import CustomerRegistrationSerializer, CustomerSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    Register a new customer
    """
    serializer = CustomerRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        customer = serializer.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(customer)
        
        return Response({
            'customer': CustomerSerializer(customer).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Login customer
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    customer = authenticate(username=username, password=password)
    
    if customer:
        refresh = RefreshToken.for_user(customer)
        
        return Response({
            'customer': CustomerSerializer(customer).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        })
    
    return Response({
        'error': 'Invalid credentials'
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    Get customer profile
    """
    serializer = CustomerSerializer(request.user)
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update customer profile
    """
    serializer = CustomerSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


from rest_framework import filters
from rest_framework.permissions import IsAdminUser
from apps.customers.serializers import StaffSerializer

class StaffViewSet(viewsets.ModelViewSet):
    """
    Manage staff members
    """
    queryset = Customer.objects.filter(is_staff=True)
    serializer_class = StaffSerializer
    permission_classes = [IsAdminUser]


class SubscriberViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View all subscribers (Admin only)
    """
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'phone_number', 'first_name', 'last_name', 'pppoe_username']
