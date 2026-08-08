"""
Payment Processing Service
Handles payment callback processing and account crediting
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction as db_transaction
from apps.payments.models import PaymentRequest, PaymentCallback, C2BPayment
from apps.billing.models import Transaction, BillingPlan
from apps.billing.services import apply_subscription
from apps.customers.models import Customer
from apps.network.services.network_automation import network_automation
from apps.payments.services.phone_hash import is_msisdn_hash

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
        
        # Get-or-renew-or-switch the customer's one active subscription for
        # this service_type (see apps.billing.services -- never creates a
        # second concurrently-active row; a plan switch prorates the old
        # plan's unused value into account_balance instead of losing it).
        subscription, credited = apply_subscription(customer, plan)
        if credited:
            logger.info(f"Prorated KES {credited} credited to {customer.username}'s balance from a plan switch")

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
    
    def process_c2b_confirmation(self, data):
        """
        Process a Safaricom C2B Confirmation callback -- a customer paid the
        Buy Goods till directly from their M-Pesa menu (not through the
        portal/STK push). The money has already moved by the time this
        arrives, so we always record it; matching to a customer and
        auto-activation are best-effort on top of that.

        Matching: Safaricom hashes the paying MSISDN on C2B confirmations
        (SHA-256 of 254XXXXXXXXX, data-minimization rollout complete since
        2026-03-24) rather than sending the real number, so we match by
        hashing our own customers' numbers the same way and comparing --
        see apps.payments.services.phone_hash. We never attempt to reverse
        Safaricom's hash: for a non-customer payer that's someone else's
        personal data we'd be reconstructing without consent, which is the
        merchant's liability to avoid under the Data Protection Act 2019.
        Falls back to BillRefNumber against Customer.username, though that's
        rarely populated -- this shortcode is a Buy Goods till, and the
        standard "Buy Goods" M-Pesa flow never prompts for an account number
        at all. Auto-activation only fires if the paid amount exactly
        matches an active plan's price for a matched customer.
        """
        trans_id = data.get('TransID')

        # Safaricom retries confirmations that don't get a clean response --
        # if we've already recorded this TransID, just acknowledge it again
        # rather than double-processing (and hitting the unique constraint).
        existing = C2BPayment.objects.filter(transaction_id=trans_id).first()
        if existing:
            return {'success': True, 'message': 'Already processed', 'payment': existing}

        bill_ref_number = (data.get('BillRefNumber') or '').strip()
        msisdn = data.get('MSISDN', '')
        amount = data.get('TransAmount')

        # This shortcode is a Buy Goods till, not a Paybill -- the standard
        # Lipa na M-Pesa "Buy Goods" flow never prompts for an account
        # number at all, so BillRefNumber essentially never carries a real
        # customer identifier here. MSISDN (the paying phone) is the only
        # signal customers actually provide, so it's the primary match --
        # via phone_hash when Safaricom sent a hash (the normal case now),
        # or the older trailing-digits match on the rare occasion a real
        # number still comes through.
        customer = None
        if msisdn:
            if is_msisdn_hash(msisdn):
                customer = Customer.objects.filter(phone_hash=msisdn.lower()).first()
            else:
                customer = Customer.objects.filter(phone_number__endswith=msisdn[-9:]).first()
        if not customer and bill_ref_number:
            customer = Customer.objects.filter(username__iexact=bill_ref_number).first()

        payment = C2BPayment.objects.create(
            transaction_id=trans_id,
            transaction_type=data.get('TransactionType', ''),
            transaction_time=self._parse_mpesa_date(data.get('TransTime')),
            amount=amount,
            business_short_code=data.get('BusinessShortCode', ''),
            bill_ref_number=bill_ref_number,
            invoice_number=data.get('InvoiceNumber', ''),
            org_account_balance=data.get('OrgAccountBalance', ''),
            third_party_trans_id=data.get('ThirdPartyTransID', ''),
            msisdn=msisdn,
            first_name=data.get('FirstName', ''),
            middle_name=data.get('MiddleName', ''),
            last_name=data.get('LastName', ''),
            matched_customer=customer,
            raw_data=data,
            status='unmatched',
        )

        if not customer:
            logger.warning(
                f"C2B payment {trans_id}: no customer matched for "
                f"BillRefNumber={bill_ref_number!r} MSISDN={msisdn}"
            )
            return {'success': True, 'message': 'Recorded, no customer match', 'payment': payment}

        # Static IP plans require a technician to configure the fixed IP
        # manually (see initiate_payment's same restriction for STK push),
        # so they're never eligible for auto-activation here. When multiple
        # remaining active plans share the same price -- a real case in
        # this deployment's data -- prefer whichever matches the customer's
        # own configured service_type before falling back to any match.
        plan_candidates = BillingPlan.objects.filter(price=amount, is_active=True).exclude(service_type='static')
        plan = plan_candidates.filter(service_type=customer.service_type).first() or plan_candidates.first()
        if not plan:
            payment.status = 'matched_no_plan'
            payment.notes = f"Matched {customer.username} but no active plan costs KES {amount}"
            payment.save(update_fields=['status', 'notes'])
            logger.warning(
                f"C2B payment {trans_id}: matched {customer.username} but "
                f"amount {amount} matches no active plan"
            )
            return {'success': True, 'message': 'Recorded, no plan match', 'payment': payment}

        # Note: Subscription.save() below triggers sync_subscription_on_save
        # (apps/billing/signals.py), which itself calls
        # network_automation.activate_customer and raises on failure -- same
        # as ManualSubscriptionView/topup, no separate activation call here.
        try:
            with db_transaction.atomic():
                transaction = Transaction.objects.create(
                    customer=customer,
                    transaction_id=trans_id,
                    amount=amount,
                    currency='KES',
                    payment_method='mpesa',
                    mpesa_receipt_number=trans_id,
                    mpesa_phone_number=msisdn,
                    mpesa_transaction_date=payment.transaction_time,
                    status='completed'
                )

                subscription, credited = apply_subscription(customer, plan)
                if credited:
                    logger.info(f"Prorated KES {credited} credited to {customer.username}'s balance from a plan switch")

                transaction.subscription = subscription
                transaction.save()

                customer.status = 'active'
                customer.save()

                payment.subscription = subscription
                payment.linked_transaction = transaction
                payment.status = 'activated'
                payment.save()
        except Exception as e:
            payment.status = 'error'
            payment.notes = f"Matched {customer.username}/{plan.name} but failed to activate: {e}"
            payment.save(update_fields=['status', 'notes'])
            logger.error(f"C2B payment {trans_id}: activation failed: {e}", exc_info=True)
            return {'success': True, 'message': 'Recorded, activation failed', 'payment': payment}

        logger.info(f"C2B payment {trans_id}: activated {customer.username} on {plan.name}")
        return {'success': True, 'message': 'Payment matched and activated', 'payment': payment}

    def _parse_mpesa_date(self, date_value):
        """
        Parse M-Pesa date format (YYYYMMDDHHmmss) to datetime
        """
        if not date_value:
            return None
        
        try:
            from datetime import datetime
            date_str = str(date_value)
            naive = datetime.strptime(date_str, '%Y%m%d%H%M%S')
            return timezone.make_aware(naive)
        except:
            return None


# Singleton instance
payment_processor = PaymentProcessor()
