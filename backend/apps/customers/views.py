from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
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

        # Same reasoning as login(): request.user isn't the new customer yet.
        from types import SimpleNamespace
        serializer_context = {'request': SimpleNamespace(user=customer)}

        return Response({
            'customer': CustomerSerializer(customer, context=serializer_context).data,
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
        from apps.customers.models import LoginActivity
        LoginActivity.objects.create(
            customer=customer,
            ip_address=request.META.get('REMOTE_ADDR')
        )

        refresh = RefreshToken.for_user(customer)

        # request.user is still AnonymousUser here -- authenticate() found a
        # match but nothing has attached it to the request, and no JWT
        # exists yet for DRF's own auth middleware to have run against. The
        # serializer's "is this the customer's own profile" check needs the
        # real customer, so build a minimal stand-in with just the one
        # attribute it reads.
        from types import SimpleNamespace
        serializer_context = {'request': SimpleNamespace(user=customer)}

        return Response({
            'customer': CustomerSerializer(customer, context=serializer_context).data,
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
    serializer = CustomerSerializer(request.user, context={'request': request})
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update the logged-in user's own basic details (name/email/phone) --
    intentionally NOT the full CustomerSerializer, see SelfProfileSerializer.
    """
    from apps.customers.serializers import SelfProfileSerializer

    serializer = SelfProfileSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change the logged-in user's own password (requires the current one).
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    old_password = request.data.get('old_password') or ''
    new_password = request.data.get('new_password') or ''

    if not request.user.check_password(old_password):
        return Response({'error': 'Current password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        validate_password(new_password, user=request.user)
    except ValidationError as e:
        return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

    request.user.set_password(new_password)
    request.user.save(update_fields=['password'])
    return Response({'success': True, 'message': 'Password changed successfully'})


from rest_framework import filters
from rest_framework.permissions import IsAdminUser
from apps.customers.serializers import StaffSerializer
from apps.customers.permissions import RoleAllowed

class StaffViewSet(viewsets.ModelViewSet):
    """
    Manage staff members -- admins only, since this controls who else gets
    admin-portal access and with what role.
    """
    queryset = Customer.objects.filter(is_staff=True)
    serializer_class = StaffSerializer
    permission_classes = [RoleAllowed('admin')]


class SubscriberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


class SubscriberViewSet(
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet
):
    """
    View and edit subscribers (Admin only). No create/delete here --
    registration has its own flow, and deleting a customer is not exposed
    through this generic endpoint.
    """
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser]
    pagination_class = SubscriberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'phone_number', 'first_name', 'last_name', 'pppoe_username']
    ordering_fields = ['account_balance', 'calculated_expiry', 'created_at', 'username']
    ordering = ['-created_at']

    def get_queryset(self):
        from django.db.models import OuterRef, Subquery, CharField, Q
        from django.db.models.functions import Coalesce
        from django.utils import timezone
        from apps.billing.models import Subscription, UsageRecord

        latest_active_expiry = Subscription.objects.filter(
            customer=OuterRef('pk'), status='active'
        ).order_by('-created_at').values('expiry_date')[:1]

        latest_subscription = Subscription.objects.filter(
            customer=OuterRef('pk')
        ).order_by('-created_at')

        latest_usage = UsageRecord.objects.filter(
            customer=OuterRef('pk')
        ).order_by('-created_at').values('framed_ip_address')[:1]

        qs = Customer.objects.annotate(
            calculated_expiry=Subquery(latest_active_expiry),
            current_plan_name=Subquery(latest_subscription.values('plan__name')[:1]),
            current_plan_status=Subquery(latest_subscription.values('status')[:1]),
            router_name=Coalesce(
                'pppoe_secret__router__name', 'hotspot_user__router__name',
                output_field=CharField()
            ),
            last_ip=Subquery(latest_usage),
        )

        service_type = self.request.query_params.get('service_type')
        if service_type:
            qs = qs.filter(service_type=service_type)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        router_param = self.request.query_params.get('router')
        if router_param:
            qs = qs.filter(
                Q(pppoe_secret__router_id=router_param) | Q(hotspot_user__router_id=router_param)
            )

        if self.request.query_params.get('is_new') == 'true':
            qs = qs.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7))

        return qs

    @action(detail=True, methods=['get'])
    def usage(self, request, pk=None):
        """
        Usage records, subscriptions and transactions for one subscriber,
        for the admin subscriber-detail view.
        """
        from apps.billing.models import UsageRecord, Subscription, Transaction
        from apps.billing.serializers import (
            UsageRecordSerializer, SubscriptionSerializer, TransactionSerializer
        )
        from apps.billing.usage_stats import build_usage_chart
        from django.db.models import Sum

        customer = self.get_object()

        customer_records = UsageRecord.objects.filter(customer=customer)
        usage_records = customer_records.order_by('-created_at')[:60]
        totals = customer_records.aggregate(
            total_up=Sum('upload_bytes'), total_down=Sum('download_bytes')
        )
        total_up = totals['total_up'] or 0
        total_down = totals['total_down'] or 0

        return Response({
            'chart': build_usage_chart(customer_records),
            'usage_records': UsageRecordSerializer(usage_records, many=True).data,
            'subscriptions': SubscriptionSerializer(
                Subscription.objects.filter(customer=customer).order_by('-created_at')[:20], many=True
            ).data,
            'transactions': TransactionSerializer(
                Transaction.objects.filter(customer=customer).order_by('-created_at')[:20], many=True
            ).data,
            'totals': {
                'upload_gb': round(total_up / (1024 ** 3), 2),
                'download_gb': round(total_down / (1024 ** 3), 2),
                'total_gb': round((total_up + total_down) / (1024 ** 3), 2),
            }
        })

    @action(detail=True, methods=['post'])
    def topup(self, request, pk=None):
        """
        Manually assign/renew a plan for this subscriber: creates a new
        Subscription (activation is handled by the existing post_save
        signal) and records a completed cash Transaction for it.
        """
        import random
        import string
        from django.utils import timezone
        from apps.billing.models import BillingPlan, Subscription, Transaction

        customer = self.get_object()
        plan_id = request.data.get('plan_id')

        try:
            plan = BillingPlan.objects.get(id=plan_id)
        except (BillingPlan.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)

        if plan.service_type == 'static' and not customer.static_ip_address:
            static_ip = (request.data.get('static_ip_address') or '').strip()
            if not static_ip:
                return Response(
                    {'error': 'static_ip_address is required to assign a Static IP plan to this customer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            customer.static_ip_address = static_ip
            customer.service_type = 'static'
            customer.save(update_fields=['static_ip_address', 'service_type'])

        expiry_date = timezone.now() + timezone.timedelta(days=plan.duration_days)
        subscription = Subscription.objects.create(
            customer=customer,
            plan=plan,
            expiry_date=expiry_date,
            status='active'
        )

        Transaction.objects.create(
            customer=customer,
            subscription=subscription,
            transaction_id='TOPUP-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=plan.price,
            payment_method='cash',
            status='completed',
            notes=f"Manual top-up by {request.user.username}"
        )

        return Response({
            'success': True,
            'message': f'{plan.name} assigned to {customer.username}',
            'subscription': self.get_serializer(customer).data,
        })
