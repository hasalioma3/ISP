import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from apps.notifications.models import NotificationLog
from apps.notifications.services.africastalking_service import africastalking_service

logger = logging.getLogger('notifications')


def _log(*, customer, subscription, event_type, phone, message, result):
    NotificationLog.objects.create(
        customer=customer,
        subscription=subscription,
        event_type=event_type,
        recipient_phone=phone,
        message=message,
        status='sent' if result['success'] else 'failed',
        provider_message_id=(
            result.get('data', {}).get('SMSMessageData', {}).get('Recipients', [{}])[0].get('messageId', '')
            if result['success'] else ''
        ),
        error='' if result['success'] else str(result.get('error', '')),
        raw_response=result.get('data'),
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_confirmation_sms(self, customer_id, event_type, amount, subscription_id=None):
    """
    Confirms a completed M-Pesa payment by SMS -- enqueued from
    payment_processor.py after a successful STK/C2B payment, via
    transaction.on_commit so the Subscription/Transaction rows it
    references are guaranteed visible by the time this runs.

    event_type is 'payment_confirmation' (a plan was activated/renewed) or
    'balance_credit' (the payment didn't cover a plan, so it was credited
    to account_balance instead -- see purchase_plan in apps.billing.services).
    """
    from apps.customers.models import Customer
    from apps.billing.models import Subscription

    customer = Customer.objects.filter(id=customer_id).first()
    if not customer:
        logger.warning(f"send_payment_confirmation_sms: customer {customer_id} no longer exists")
        return

    subscription = Subscription.objects.filter(id=subscription_id).select_related('plan').first() if subscription_id else None
    # Callers pass amount as whatever they had on hand (a float from raw
    # M-Pesa JSON, a Decimal, a plain string) -- normalize once here so the
    # SMS always reads "100.00", never "100.0" or "100.000000001".
    amount = Decimal(str(amount)).quantize(Decimal('0.01'))

    if event_type == 'payment_confirmation' and subscription:
        message = (
            f"Payment of KES {amount} received. Your {subscription.plan.name} plan is now "
            f"active until {subscription.expiry_date.strftime('%d %b %Y')}."
        )
    else:
        event_type = 'balance_credit'
        message = (
            f"Payment of KES {amount} received and credited to your account balance "
            f"(KES {customer.account_balance}). Contact us to activate a plan."
        )

    result = africastalking_service.send_sms(customer.phone_number, message)

    # send_sms never raises -- a transient failure (network/timeout) shows
    # up as data=None, distinct from AT explicitly rejecting the recipient
    # (data present, just not a 'Success' status, which retrying won't fix).
    # Only the former is worth retrying.
    if not result['success'] and result.get('data') is None and self.request.retries < self.max_retries:
        self.retry(exc=Exception(result.get('error', 'SMS send failed')))
        return

    _log(
        customer=customer, subscription=subscription, event_type=event_type,
        phone=customer.phone_number, message=message, result=result,
    )


@shared_task
def send_expiry_reminders():
    """
    Two-stage reminder, checked in one daily pass: subscriptions expiring
    in exactly 3 days get 'expiry_reminder_3day', subscriptions expiring
    today get 'expiry_reminder_dayof'. Dedup is via NotificationLog (has a
    'sent' row for this subscription+stage+today already?) rather than a
    flag on Subscription, so a renewal naturally opens a fresh window
    without needing a reset step. Scheduled in celery.py.
    """
    from apps.billing.models import Subscription

    today = timezone.now().date()
    stages = {
        'expiry_reminder_3day': today + timedelta(days=3),
        'expiry_reminder_dayof': today,
    }

    # Not filtered to status='active' -- check_expired_subscriptions (runs
    # every minute, see celery.py) flips a subscription to 'expired' the
    # instant its expiry_date passes, so a subscription expiring earlier
    # today would already be 'expired' by the time this runs, and a
    # status='active' filter would silently skip its day-of reminder.
    # 'cancelled'/'suspended' are excluded -- those aren't a plain expiry.
    subs = Subscription.objects.filter(
        status__in=['active', 'expired'], expiry_date__date__in=stages.values()
    ).select_related('customer', 'plan')

    sent_count = 0
    for sub in subs:
        for event_type, target_date in stages.items():
            if sub.expiry_date.date() != target_date:
                continue

            already_sent = NotificationLog.objects.filter(
                subscription=sub, event_type=event_type, created_at__date=today, status='sent'
            ).exists()
            if already_sent:
                continue

            message = (
                f"Your {sub.plan.name} plan expires on {sub.expiry_date.strftime('%d %b')}. "
                f"Renew via M-Pesa or the customer portal to avoid disconnection."
            )
            result = africastalking_service.send_sms(sub.customer.phone_number, message)
            _log(
                customer=sub.customer, subscription=sub, event_type=event_type,
                phone=sub.customer.phone_number, message=message, result=result,
            )
            if result['success']:
                sent_count += 1

    logger.info(f"send_expiry_reminders: sent {sent_count} reminders")
    return sent_count
