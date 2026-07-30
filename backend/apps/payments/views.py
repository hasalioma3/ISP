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
@permission_classes([AllowAny])
def initiate_payment(request):
    """
    Initiate M-Pesa STK Push payment
    Supports both Authenticated users and Guest checkout
    """
    serializer = InitiatePaymentSerializer(data=request.data)
    
    if not serializer.is_valid():
        logger.error(f"Validation Error: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    plan_id = serializer.validated_data['plan_id']
    phone_number = serializer.validated_data['phone_number']
    mac_address = serializer.validated_data.get('mac_address')
    
    # Get billing plan
    try:
        plan = BillingPlan.objects.get(id=plan_id, is_active=True)
    except BillingPlan.DoesNotExist:
        return Response({
            'error': 'Billing plan not found'
        }, status=status.HTTP_404_NOT_FOUND)

    # Static IP plans require a technician to configure the fixed IP on the
    # customer's device first, so they can't be bought through self-service.
    if plan.service_type == 'static':
        return Response({
            'error': 'This plan requires setup by our team. Please contact support.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Determine Customer
    if request.user.is_authenticated:
        customer = request.user
    else:
        # GUEST FLOW
        from apps.customers.models import Customer
        import re

        # Generate unique username based on Phone + MAC suffix
        if mac_address:
            # Clean MAC: remove colons/dashes, take last 4 chars
            clean_mac = re.sub(r'[^a-zA-Z0-9]', '', mac_address).upper()
            mac_suffix = clean_mac[-4:] if len(clean_mac) >= 4 else clean_mac
            target_username = f"{phone_number}_{mac_suffix}"
            logger.info(f"Using device-specific username: {target_username}")
        else:
            target_username = phone_number
            logger.info(f"Using phone number as username: {target_username}")

        try:
            # Check if specific user exists (by username, as phone isn't unique anymore)
            customer = Customer.objects.get(username=target_username)
        except Customer.DoesNotExist:
            # Create New Guest Customer
            try:
                # Use generated target_username and phone_number as password
                customer = Customer.objects.create_user(
                    username=target_username,
                    password=phone_number, # Password is the phone number for ease
                    phone_number=phone_number,
                    service_type='hotspot',
                    status='active',
                    is_verified=True,
                    hotspot_mac_address=mac_address # Ensure MAC is linked
                )
                logger.info(f"Auto-created Guest Customer: {target_username}")
            except Exception as e:
                logger.error(f"Failed to create guest user: {e}")
                return Response({
                    'error': 'Failed to create guest account. Please try logging in.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                logger.error(f"Failed to create guest user: {e}")
                return Response({
                    'error': 'Failed to create guest account. Please try logging in.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Update customer MAC if provided
    if mac_address:
        customer.hotspot_mac_address = mac_address
        customer.save()
    
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


@api_view(['POST'])
@permission_classes([AllowAny])
def reactivate_session(request):
    """
    Let a Hotspot user who already paid (but whose session dropped, or who's
    reconnecting on a device the router doesn't currently recognize)
    reconnect using the M-Pesa code from their original payment instead of
    paying again. Looks up the completed Transaction by receipt number,
    confirms the subscription it paid for is still active, rebinds the
    given MAC to that customer, and pushes them back onto the router.
    """
    from django.utils import timezone
    from apps.billing.models import Transaction, Subscription
    from apps.network.services.network_automation import network_automation

    mpesa_code = (request.data.get('mpesa_code') or '').strip()
    mac_address = request.data.get('mac_address')

    if not mpesa_code:
        return Response({'error': 'M-Pesa code is required'}, status=status.HTTP_400_BAD_REQUEST)

    transaction = Transaction.objects.filter(
        mpesa_receipt_number__iexact=mpesa_code, status='completed'
    ).select_related('customer').order_by('-created_at').first()

    if not transaction:
        return Response({
            'error': 'M-Pesa code not found. Double-check the code from your payment SMS.'
        }, status=status.HTTP_404_NOT_FOUND)

    customer = transaction.customer

    subscription = Subscription.objects.filter(
        customer=customer, status='active', expiry_date__gt=timezone.now()
    ).order_by('-expiry_date').first()

    if not subscription:
        return Response({
            'error': 'The subscription from this payment has expired. Please buy a new plan.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if subscription.plan.service_type not in ['hotspot', 'both']:
        return Response({
            'error': 'This payment was for a PPPoE plan, not Hotspot -- log in via your PPPoE client instead.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if mac_address:
        customer.hotspot_mac_address = mac_address
        customer.save(update_fields=['hotspot_mac_address'])

    result = network_automation.activate_customer(customer, subscription.plan)
    if not result.get('success'):
        logger.error(f"Reactivation failed for {customer.username}: {result.get('error')}")
        return Response({
            'error': f"Could not reactivate your session: {result.get('error')}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'success': True,
        'message': f'Session reactivated! You are on {subscription.plan.name}.',
        'username': customer.hotspot_username or customer.username,
        'password': customer.hotspot_password or customer.username,
    })


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
