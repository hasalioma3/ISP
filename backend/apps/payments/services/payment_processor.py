"""
Payment Processing Service
Handles payment callback processing and account crediting
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction as db_transaction
from apps.payments.models import PaymentRequest, PaymentCallback
from apps.billing.models import Transaction, Subscription
from apps.network.services.network_automation import network_automation

logger = logging.getLogger('mpesa')


class PaymentProcessor:
    """
    Process M-Pesa payment callbacks and activate services
    """
    
    def process_callback(self, callback_data):
        """
        Process M-Pesa callback and activate network access
        
        Args:
            callback_data: Raw callback data from M-Pesa
            
        Returns:
            dict: Processing result
        """
        try:
            # Extract callback information
            body = callback_data.get('Body', {}).get('stkCallback', {})
            
            merchant_request_id = body.get('MerchantRequestID')
            checkout_request_id = body.get('CheckoutRequestID')
            result_code = str(body.get('ResultCode', ''))
            result_desc = body.get('ResultDesc', '')
            
            logger.info(f"Processing callback for {merchant_request_id}, result: {result_code}")
            
            # Find the payment request
            try:
                payment_request = PaymentRequest.objects.get(
                    checkout_request_id=checkout_request_id
                )
            except PaymentRequest.DoesNotExist:
                logger.error(f"Payment request not found for checkout ID: {checkout_request_id}")
                return {
                    'success': False,
                    'error': 'Payment request not found'
                }
            
            # Create callback record
            callback_metadata = body.get('CallbackMetadata', {}).get('Item', [])
            callback_dict = {item['Name']: item.get('Value') for item in callback_metadata}
            
            payment_callback = PaymentCallback.objects.create(
                payment_request=payment_request,
                merchant_request_id=merchant_request_id,
                checkout_request_id=checkout_request_id,
                result_code=result_code,
                result_desc=result_desc,
                mpesa_receipt_number=callback_dict.get('MpesaReceiptNumber'),
                transaction_date=self._parse_mpesa_date(callback_dict.get('TransactionDate')),
                phone_number=callback_dict.get('PhoneNumber'),
                amount=callback_dict.get('Amount'),
                raw_data=callback_data
            )
            
            # Check if payment was successful
            if result_code == '0':
                # Payment successful
                with db_transaction.atomic():
                    self._process_successful_payment(payment_request, payment_callback)
                
                logger.info(f"Payment processed successfully: {merchant_request_id}")
                return {
                    'success': True,
                    'message': 'Payment processed successfully'
                }
            else:
                # Payment failed
                payment_request.status = 'failed'
                payment_request.save()
                
                logger.warning(f"Payment failed: {merchant_request_id}, reason: {result_desc}")
                return {
                    'success': False,
                    'error': result_desc
                }
                
        except Exception as e:
            logger.error(f"Error processing callback: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _process_successful_payment(self, payment_request, payment_callback):
        """
        Process successful payment: create transaction, update subscription, activate network
        """
        customer = payment_request.customer
        plan = payment_request.plan
        
        # Update payment request status
        payment_request.status = 'completed'
        payment_request.save()
        
        # Create transaction record
        transaction = Transaction.objects.create(
            customer=customer,
            transaction_id=payment_callback.mpesa_receipt_number,
            amount=payment_callback.amount,
            currency='KES',
            payment_method='mpesa',
            mpesa_receipt_number=payment_callback.mpesa_receipt_number,
            mpesa_phone_number=payment_callback.phone_number,
            mpesa_transaction_date=payment_callback.transaction_date,
            status='completed'
        )
        
        # Get or create subscription
        try:
            subscription = Subscription.objects.filter(
                customer=customer,
                plan=plan
            ).latest('created_at')
            
            # Calculate duration delta
            duration_value = plan.duration_value
            duration_unit = plan.duration_unit
            
            if duration_unit == 'minutes':
                expiry_delta = timedelta(minutes=duration_value)
            elif duration_unit == 'hours':
                expiry_delta = timedelta(hours=duration_value)
            elif duration_unit == 'days':
                expiry_delta = timedelta(days=duration_value)
            elif duration_unit == 'months':
                expiry_delta = timedelta(days=duration_value * 30) # Approx
            else:
                expiry_delta = timedelta(days=plan.duration_days) # Fallback

            # Check if subscription is expired or about to expire
            if subscription.is_expired or subscription.days_remaining <= 0:
                # Renew from now
                subscription.start_date = timezone.now()
                subscription.expiry_date = timezone.now() + expiry_delta
            else:
                # Extend existing subscription
                subscription.expiry_date += expiry_delta
            
            subscription.status = 'active'
            subscription.save()
            
        except Subscription.DoesNotExist:
            # Calculate duration delta for new subscription
            duration_value = plan.duration_value
            duration_unit = plan.duration_unit
            
            if duration_unit == 'minutes':
                expiry_delta = timedelta(minutes=duration_value)
            elif duration_unit == 'hours':
                expiry_delta = timedelta(hours=duration_value)
            elif duration_unit == 'days':
                expiry_delta = timedelta(days=duration_value)
            elif duration_unit == 'months':
                expiry_delta = timedelta(days=duration_value * 30)
            else:
                expiry_delta = timedelta(days=plan.duration_days)

            # Create new subscription
            subscription = Subscription.objects.create(
                customer=customer,
                plan=plan,
                start_date=timezone.now(),
                expiry_date=timezone.now() + expiry_delta,
                status='active'
            )
        
        # Link transaction to subscription
        transaction.subscription = subscription
        transaction.save()
        
        # Update customer status
        customer.status = 'active'
        customer.save()
        
        # Mark callback as processed
        payment_callback.processed = True
        payment_callback.processed_at = timezone.now()
        payment_callback.save()
        
        # Activate network access
        try:
            network_automation.activate_customer(customer, plan)
            logger.info(f"Network access activated for {customer.username}")
        except Exception as e:
            logger.error(f"Failed to activate network for {customer.username}: {str(e)}")
            # Don't fail the payment processing if network activation fails
            # This can be retried manually
    
    def _parse_mpesa_date(self, date_value):
        """
        Parse M-Pesa date format (YYYYMMDDHHmmss) to datetime
        """
        if not date_value:
            return None
        
        try:
            from datetime import datetime
            date_str = str(date_value)
            return datetime.strptime(date_str, '%Y%m%d%H%M%S')
        except:
            return None


# Singleton instance
payment_processor = PaymentProcessor()
