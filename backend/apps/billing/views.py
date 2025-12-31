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
    permission_classes = [IsAdminUser]


class VoucherGenerationView(APIView):
    """
    Generate bulk vouchers (Admin only)
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        serializer = VoucherGenerationSerializer(data=request.data)
        if serializer.is_valid():
            quantity = serializer.validated_data['quantity']
            value = serializer.validated_data['value']
            note = serializer.validated_data.get('note', '')
            
            # Create Batch
            with transaction.atomic():
                batch = VoucherBatch.objects.create(
                    quantity=quantity,
                    value=value,
                    generated_by=request.user,
                    note=note
                )
                
                vouchers_to_create = []
                for _ in range(quantity):
                    # Generate 12-digit code
                    code = ''.join(random.choices(string.digits, k=12))
                    # Ensure uniqueness (simple check, colliding is rare for 12 digits but possible)
                    while Voucher.objects.filter(code=code).exists():
                        code = ''.join(random.choices(string.digits, k=12))
                        
                    vouchers_to_create.append(Voucher(
                        batch=batch,
                        code=code,
                        amount=value,
                        status='active'
                    ))
                
                Voucher.objects.bulk_create(vouchers_to_create)
            
            return Response(
                VoucherBatchSerializer(batch).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VoucherRedeemView(APIView):
    """
    Redeem a voucher code
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = VoucherRedeemSerializer(data=request.data)
        if serializer.is_valid():
            code = serializer.validated_data['code']
            
            try:
                voucher = Voucher.objects.get(code=code)
            except Voucher.DoesNotExist:
                return Response({'error': 'Invalid voucher code'}, status=status.HTTP_400_BAD_REQUEST)
            
            if voucher.status != 'active':
                return Response({'error': 'Voucher has already been used'}, status=status.HTTP_400_BAD_REQUEST)
            
            if voucher.expiry_date and voucher.expiry_date < timezone.now():
                return Response({'error': 'Voucher has expired'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Redeem
            with transaction.atomic():
                # Lock voucher row
                voucher = Voucher.objects.select_for_update().get(id=voucher.id)
                
                if voucher.status != 'active':
                     return Response({'error': 'Voucher already used'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Update voucher
                voucher.status = 'used'
                voucher.used_by = request.user
                voucher.used_at = timezone.now()
                voucher.save()
                
                # Update user balance
                request.user.account_balance += voucher.amount
                request.user.save()
            
            return Response({
                'success': True,
                'message': f'Voucher redeemed! KES {voucher.amount} added to your balance.',
                'new_balance': request.user.account_balance
            })
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
