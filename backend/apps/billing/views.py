from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.billing.models import BillingPlan, Subscription, Transaction, UsageRecord
from apps.billing.serializers import (
    BillingPlanSerializer, SubscriptionSerializer,
    TransactionSerializer, UsageRecordSerializer
)
from apps.customers.permissions import RoleAllowed


class BillingPlanViewSet(viewsets.ModelViewSet):
    """
    Billing plans. List/retrieve are public (the captive portal and
    customer app need to show plans to unauthenticated users) and only ever
    return active plans for non-staff callers. Create/update/delete are
    admin-only.
    """
    serializer_class = BillingPlanSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [RoleAllowed('admin')()]

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            return BillingPlan.objects.all()
        return BillingPlan.objects.filter(is_active=True)


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
        return UsageRecord.objects.filter(customer=self.request.user)


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
    permission_classes = [RoleAllowed('admin', 'sales')]


class VoucherGenerationView(APIView):
    """
    Generate bulk vouchers (admin/sales only)
    """
    permission_classes = [RoleAllowed('admin', 'sales')]
    
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
            mac_address = serializer.validated_data.get('mac_address') or None
            
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
                    if mac_address:
                        customer.hotspot_mac_address = mac_address

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
    Manually create a customer (PPPoE or Hotspot) -- or renew/assign a plan
    to an existing one, by username -- and activate their subscription.
    When a new customer is created, portal login and PPPoE/Hotspot
    credentials (same username/password, matching the self-service
    registration flow) are issued and returned once so the admin can hand
    them to the customer. (Admin/Sales only)
    """
    permission_classes = [RoleAllowed('admin', 'sales')]

    def post(self, request):
        from apps.customers.models import Customer

        data = request.data
        username = (data.get('username') or '').strip()
        plan_id = data.get('plan_id')
        password = data.get('password') or ''
        service_type = data.get('service_type') or 'pppoe'

        if not username:
            return Response({'error': 'username is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = BillingPlan.objects.get(id=plan_id)
        except (BillingPlan.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)

        created_new = False
        customer = Customer.objects.filter(username=username).first()

        if not customer:
            phone_number = (data.get('phone_number') or '').strip()
            if not phone_number:
                return Response({'error': 'phone_number is required to create a new customer'}, status=status.HTTP_400_BAD_REQUEST)

            if not password:
                password = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

            customer = Customer.objects.create(
                username=username,
                email=data.get('email', ''),
                phone_number=phone_number,
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                service_type=service_type,
                status='pending',
                is_verified=True,
            )
            customer.set_password(password)
            if service_type in ['pppoe', 'both']:
                customer.pppoe_username = username
                customer.pppoe_password = password
            if service_type in ['hotspot', 'both']:
                customer.hotspot_username = username
                customer.hotspot_password = password
            if service_type == 'static':
                static_ip = (data.get('static_ip_address') or '').strip()
                if not static_ip:
                    customer.delete()
                    return Response({'error': 'static_ip_address is required for Static IP customers'}, status=status.HTTP_400_BAD_REQUEST)
                customer.static_ip_address = static_ip
            customer.save()
            created_new = True
        elif plan.service_type == 'static' and not customer.static_ip_address:
            static_ip = (data.get('static_ip_address') or '').strip()
            if not static_ip:
                return Response(
                    {'error': 'static_ip_address is required to assign a Static IP plan to this customer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            customer.static_ip_address = static_ip
            customer.service_type = 'static'
            customer.save(update_fields=['static_ip_address', 'service_type'])

        # Duration calc mirrors payment_processor.py's logic, so manually
        # activated and M-Pesa-activated subscriptions expire consistently.
        duration_value = plan.duration_value
        duration_unit = plan.duration_unit
        if duration_unit == 'minutes':
            expiry_delta = timezone.timedelta(minutes=duration_value)
        elif duration_unit == 'hours':
            expiry_delta = timezone.timedelta(hours=duration_value)
        elif duration_unit == 'days':
            expiry_delta = timezone.timedelta(days=duration_value)
        elif duration_unit == 'months':
            expiry_delta = timezone.timedelta(days=duration_value * 30)
        else:
            expiry_delta = timezone.timedelta(days=plan.duration_days)

        subscription = Subscription.objects.create(
            customer=customer,
            plan=plan,
            expiry_date=timezone.now() + expiry_delta,
            status='active'
        )

        Transaction.objects.create(
            customer=customer,
            subscription=subscription,
            transaction_id='MANUAL-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=plan.price,
            payment_method='cash',
            status='completed',
            notes=f"Manual activation by {request.user.username}"
        )

        response_data = {
            'success': True,
            'message': f'Subscription activated for {customer.username}',
            'subscription_id': subscription.id,
        }
        if created_new:
            response_data['credentials'] = {
                'portal_username': customer.username,
                'portal_password': password,
                'pppoe_username': customer.pppoe_username,
                'pppoe_password': customer.pppoe_password,
                'hotspot_username': customer.hotspot_username,
                'hotspot_password': customer.hotspot_password,
                'static_ip_address': customer.static_ip_address,
            }
        return Response(response_data)
