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
