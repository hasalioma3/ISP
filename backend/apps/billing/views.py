from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.billing.models import BillingPlan, Subscription, Transaction, UsageRecord
from apps.billing.serializers import (
    BillingPlanSerializer, SubscriptionSerializer,
    TransactionSerializer, UsageRecordSerializer
)


class BillingPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve billing plans
    Public endpoint - no authentication required
    """
    queryset = BillingPlan.objects.filter(is_active=True)
    serializer_class = BillingPlanSerializer
    permission_classes = [AllowAny]


class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View customer subscriptions
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Subscription.objects.filter(customer=self.request.user)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """
        Get current active subscription
        """
        subscription = Subscription.objects.filter(
            customer=request.user,
            status='active'
        ).first()
        
        if subscription:
            serializer = self.get_serializer(subscription)
            return Response(serializer.data)
        
        return Response({
            'message': 'No active subscription'
        }, status=status.HTTP_404_NOT_FOUND)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View payment transactions
    """
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Transaction.objects.filter(customer=self.request.user)


class UsageRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View usage records
    """
    serializer_class = UsageRecordSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        import logging
        logger = logging.getLogger('apps.billing')
        qs = UsageRecord.objects.filter(customer=self.request.user)
        logger.info(f"Usage Request by {self.request.user.username}: Found {qs.count()} records.")
        return qs


from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.db import transaction
import random
import string
from apps.billing.models import Voucher, VoucherBatch
from apps.billing.serializers import (
    VoucherBatchSerializer, VoucherGenerationSerializer, VoucherRedeemSerializer
)


class VoucherBatchViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List voucher batches
    """
    queryset = VoucherBatch.objects.all()
    serializer_class = VoucherBatchSerializer
    permission_classes = [IsAdminUser]

    @action(detail=True, methods=['get'])
    def vouchers(self, request, pk=None):
        batch = self.get_object()
        vouchers = batch.vouchers.all()
        
        # Use serializer for consistency
        from apps.billing.serializers import VoucherSerializer
        serializer = VoucherSerializer(vouchers, many=True)
        return Response(serializer.data)


class VoucherGenerationView(APIView):
    """
    Generate bulk vouchers (Admin only)
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        serializer = VoucherGenerationSerializer(data=request.data)
        if serializer.is_valid():
            quantity = serializer.validated_data['quantity']
            value = serializer.validated_data.get('value')
            plan_id = serializer.validated_data.get('plan_id')
            note = serializer.validated_data.get('note', '')
            
            plan = None
            if plan_id:
                try:
                    plan = BillingPlan.objects.get(id=plan_id)
                    value = plan.price # Use plan price as value if not explicit
                except BillingPlan.DoesNotExist:
                     return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Create Batch
            with transaction.atomic():
                batch = VoucherBatch.objects.create(
                    quantity=quantity,
                    value=value or 0,
                    plan=plan,
                    generated_by=request.user,
                    note=note
                )
                
                vouchers_to_create = []
                # Use uppercase and digits for 6-char codes to ensure enough entropy
                chars = string.ascii_uppercase + string.digits
                
                for _ in range(quantity):
                    # Generate 6-char alphanumeric code
                    code = ''.join(random.choices(chars, k=6))
                    # Ensure uniqueness
                    while Voucher.objects.filter(code=code).exists():
                        code = ''.join(random.choices(chars, k=6))
                        
                    vouchers_to_create.append(Voucher(
                        batch=batch,
                        code=code,
                        amount=value or 0,
                        plan=plan,
                        status='active'
                    ))
                
                Voucher.objects.bulk_create(vouchers_to_create)
            
            # Refetch batch to include vouchers in serialization
            batch = VoucherBatch.objects.prefetch_related('vouchers').get(id=batch.id)
            
            return Response(
                VoucherBatchSerializer(batch).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VoucherRedeemView(APIView):
    """
    Redeem a voucher code
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = VoucherRedeemSerializer(data=request.data)
        if serializer.is_valid():
            code = serializer.validated_data['code']
            
            try:
                voucher = Voucher.objects.select_related('plan').get(code=code)
            except Voucher.DoesNotExist:
                return Response({'error': 'Invalid voucher code'}, status=status.HTTP_400_BAD_REQUEST)
            
            if voucher.status != 'active':
                return Response({'error': 'Voucher has already been used'}, status=status.HTTP_400_BAD_REQUEST)
            
            if voucher.expiry_date and voucher.expiry_date < timezone.now():
                return Response({'error': 'Voucher has expired'}, status=status.HTTP_400_BAD_REQUEST)

            # Check if voucher has a plan associated (REQUIRED for auto-account creation)
            if not voucher.plan:
                 return Response({'error': 'This voucher is not linked to a plan. Cannot auto-redeem.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Redeem logic
            with transaction.atomic():
                # Lock voucher row
                voucher = Voucher.objects.select_for_update().get(id=voucher.id)
                
                if voucher.status != 'active':
                     return Response({'error': 'Voucher already used'}, status=status.HTTP_400_BAD_REQUEST)
                
                # 1. Create Customer
                # Check if user already exists
                from apps.customers.models import Customer
                
                username = voucher.code
                if Customer.objects.filter(username=username).exists():
                     # User exists, append random 3 digits to ensure unique new user record
                     import random
                     suffix = ''.join(random.choices('0123456789', k=3))
                     username = f"{voucher.code}{suffix}"
                
                customer = Customer.objects.create(
                    username=username,
                    # Inherit service type from the plan
                    service_type=voucher.plan.service_type,
                    status='active',
                    phone_number='',
                    first_name='',
                    last_name='',
                )
                
                customer.set_password(voucher.code) # Password = Voucher Code
                
                # Set credentials based on plan service type
                if voucher.plan.service_type in ['pppoe', 'both']:
                    customer.pppoe_username = customer.username
                    customer.pppoe_password = voucher.code
                
                if voucher.plan.service_type in ['hotspot', 'both']:
                    customer.hotspot_username = customer.username
                    customer.hotspot_password = voucher.code
                    
                customer.save()
                
                # Logic used to vary if using get_or_create, now significantly simplified for "always create new" logic requested
                created = True
                
                # 2. Update Voucher
                voucher.status = 'used'
                voucher.used_by = customer
                voucher.used_at = timezone.now()
                voucher.save()
                
                # 3. Create Subscription
                from apps.billing.models import Subscription
                
                # Calculate expiry
                expiry_date = timezone.now() + timezone.timedelta(days=voucher.plan.duration_days)
                
                Subscription.objects.create(
                    customer=customer,
                    plan=voucher.plan,
                    expiry_date=expiry_date,
                    status='active'
                )
                
                # 4. Generate Tokens
                from rest_framework_simplejwt.tokens import RefreshToken
                from apps.customers.serializers import CustomerSerializer
                
                refresh = RefreshToken.for_user(customer)

            return Response({
                'success': True,
                'message': f'Voucher redeemed! Subscribed to {voucher.plan.name}.',
                'customer': CustomerSerializer(customer).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            })
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManualSubscriptionView(APIView):
    """
    Manually create a subscription along with user if needed (Admin only)
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        # 1. Create or Get Customer
        # 2. Assign Plan
        # 3. Process 'Cash' Payment transaction
        # 4. Activate (via signal)
        
        from apps.customers.models import Customer
        from apps.customers.serializers import CustomerRegistrationSerializer
        
        data = request.data
        username = data.get('username')
        plan_id = data.get('plan_id')
        
        # Check if customer exists
        customer = Customer.objects.filter(username=username).first()
        if not customer:
            # Create new customer
            serializer = CustomerRegistrationSerializer(data=data)
            if serializer.is_valid():
                customer = serializer.save()
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get Plan
        try:
            plan = BillingPlan.objects.get(id=plan_id)
        except BillingPlan.DoesNotExist:
            return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Create Subscription
        expiry_date = timezone.now() + timezone.timedelta(days=plan.duration_days) # Simplified duration logic
        
        subscription = Subscription.objects.create(
            customer=customer,
            plan=plan,
            expiry_date=expiry_date,
            status='active'
        )
        
        # Record Transaction
        Transaction.objects.create(
            customer=customer,
            subscription=subscription,
            transaction_id='MANUAL-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=plan.price,
            payment_method='cash', # Or 'manual'
            status='completed',
            notes=f"Manual activation by {request.user.username}"
        )
        
        return Response({
            'success': True,
            'message': f'Subscription activated for {customer.username}',
            'subscription_id': subscription.id
        })
