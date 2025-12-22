from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import logging
import uuid

from apps.payments.models import PaymentRequest, PaymentCallback
from apps.payments.serializers import (
    PaymentRequestSerializer, InitiatePaymentSerializer, PaymentCallbackSerializer
)
from apps.payments.services.mpesa_service import mpesa_service
from apps.payments.services.payment_processor import payment_processor
from apps.billing.models import BillingPlan

logger = logging.getLogger('mpesa')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    Initiate M-Pesa STK Push payment
    """
    serializer = InitiatePaymentSerializer(data=request.data)
    
    if not serializer.is_valid():
        logger.error(f"Validation Error: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    plan_id = serializer.validated_data['plan_id']
    phone_number = serializer.validated_data['phone_number']
    
    # Get billing plan
    try:
        plan = BillingPlan.objects.get(id=plan_id, is_active=True)
    except BillingPlan.DoesNotExist:
        return Response({
            'error': 'Billing plan not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    customer = request.user
    
    # Create payment request record
    payment_request = PaymentRequest.objects.create(
        customer=customer,
        plan=plan,
        phone_number=phone_number,
        amount=plan.price,
        account_reference=customer.username,
        transaction_desc=f"{plan.name} subscription",
        status='initiated'
    )
    
    # Initiate STK Push
    result = mpesa_service.initiate_stk_push(
        phone_number=phone_number,
        amount=plan.price,
        account_reference=customer.username,
        transaction_desc=f"{plan.name} subscription"
    )
    
    if result['success']:
        data = result['data']
        
        # Update payment request with M-Pesa response
        payment_request.merchant_request_id = data.get('MerchantRequestID')
        payment_request.checkout_request_id = data.get('CheckoutRequestID')
        payment_request.response_code = data.get('ResponseCode')
        payment_request.response_description = data.get('ResponseDescription')
        payment_request.customer_message = data.get('CustomerMessage')
        payment_request.status = 'pending'
        payment_request.save()
        
        return Response({
            'success': True,
            'message': 'STK Push sent to your phone',
            'payment_request_id': payment_request.id,
            'checkout_request_id': payment_request.checkout_request_id
        }, status=status.HTTP_200_OK)
    else:
        payment_request.status = 'failed'
        payment_request.response_description = result.get('error')
        payment_request.save()
        
        error_msg = result.get('error', 'Failed to initiate payment')
        logger.error(f"M-Pesa Initiation Failed: {error_msg}")
        return Response({
            'success': False,
            'error': error_msg
        }, status=status.HTTP_400_BAD_REQUEST)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_callback(request):
    """
    M-Pesa payment callback endpoint
    This endpoint receives payment notifications from Safaricom
    """
    logger.info(f"Received M-Pesa callback: {request.data}")
    
    try:
        # Process the callback
        result = payment_processor.process_callback(request.data)
        
        return Response({
            'ResultCode': 0,
            'ResultDesc': 'Success'
        })
    
    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}", exc_info=True)
        return Response({
            'ResultCode': 1,
            'ResultDesc': 'Failed'
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_status(request, payment_request_id):
    """
    Check payment status
    """
    try:
        payment_request = PaymentRequest.objects.get(
            id=payment_request_id,
            customer=request.user
        )
        
        serializer = PaymentRequestSerializer(payment_request)
        return Response(serializer.data)
    
    except PaymentRequest.DoesNotExist:
        return Response({
            'error': 'Payment request not found'
        }, status=status.HTTP_404_NOT_FOUND)


class PaymentRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View payment requests
    """
    serializer_class = PaymentRequestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return PaymentRequest.objects.filter(customer=self.request.user)
