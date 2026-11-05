import logging
import time
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.notifications.dispatch import send_and_log
from apps.notifications.models import NotificationLog, NotificationSettings
from apps.notifications.services.africastalking_service import AfricasTalkingService

logger = logging.getLogger('notifications')


def _log(*, customer, subscription, event_type, phone, message, result):
    NotificationLog.objects.create(
        customer=customer,
        subscription=subscription,
        event_type=event_type,
        recipient=phone,
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

    result = AfricasTalkingService().send_sms(customer.phone_number, message)

    # send_sms never raises -- a transient failure (network/timeout) shows
    # up as data=None, distinct from AT explicitly rejecting the recipient
    # (data present, just not a 'Success' status, which retrying won't fix).
    # Only the former is worth retrying -- not a config_error (missing
    # credentials / bad number), which fails without ever reaching AT.
    if (not result['success'] and result.get('data') is None and not result.get('config_error')
            and self.request.retries < self.max_retries):
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
            result = AfricasTalkingService().send_sms(sub.customer.phone_number, message)
            _log(
                customer=sub.customer, subscription=sub, event_type=event_type,
                phone=sub.customer.phone_number, message=message, result=result,
            )
            if result['success']:
                sent_count += 1

    logger.info(f"send_expiry_reminders: sent {sent_count} reminders")
    return sent_count


@shared_task
def send_welcome_notification(customer_id, plain_password=None):
    """
    Sent once, right after a new customer is created -- enqueued explicitly
    from each of the three creation call sites (public registration,
    ManualSubscriptionView, VoucherRedeemView) via transaction.on_commit,
    rather than a post_save signal: all three call Customer.objects.create()
    first and only set the password/pppoe/hotspot credentials on a second
    .save() afterwards, so a created=True signal would fire before there's
    anything useful to send.

    Tries every channel the customer has available (not just one) since
    reach matters most for a one-time welcome. A voucher-redeemed hotspot
    customer typically has no phone and no linked Telegram chat yet -- that
    cleanly no-ops (logged, not an error); they get their password from the
    UI response directly instead.
    """
    from apps.customers.models import Customer

    customer = Customer.objects.filter(id=customer_id).first()
    if not customer:
        logger.warning(f"send_welcome_notification: customer {customer_id} no longer exists")
        return

    lines = [f"Welcome to our network, {customer.first_name or customer.username}!"]
    if plain_password:
        lines.append(f"Your login: {customer.username} / {plain_password}")
    lines.append("Contact us anytime if you need help getting connected.")
    message = ' '.join(lines)

    sent_any = False
    if customer.telegram_chat_id:
        result = send_and_log(
            channel='telegram', recipient=customer.telegram_chat_id, message=message,
            event_type='welcome', customer=customer,
        )
        sent_any = sent_any or result['success']
    if customer.phone_number:
        result = send_and_log(
            channel='sms', recipient=customer.phone_number, message=message,
            event_type='welcome', customer=customer,
        )
        sent_any = sent_any or result['success']
        if NotificationSettings.load().whatsapp_enabled:
            result = send_and_log(
                channel='whatsapp', recipient=customer.phone_number, message=message,
                event_type='welcome', customer=customer,
            )
            sent_any = sent_any or result['success']

    if not sent_any:
        logger.info(f"send_welcome_notification: no channel reached customer {customer_id} (no phone/chat id, or all failed)")


@shared_task
def send_payment_failed_notification(customer_id, plan_id, reason):
    """Sibling of send_payment_confirmation_sms -- fired from the
    result_code != '0' branch of payment_processor.process_callback."""
    from apps.billing.models import BillingPlan
    from apps.customers.models import Customer

    customer = Customer.objects.filter(id=customer_id).first()
    if not customer:
        logger.warning(f"send_payment_failed_notification: customer {customer_id} no longer exists")
        return

    plan = BillingPlan.objects.filter(id=plan_id).first()
    plan_name = plan.name if plan else 'your plan'
    message = (
        f"Your payment for {plan_name} could not be completed ({reason}). "
        f"No money was deducted. Please try again."
    )

    if customer.phone_number:
        send_and_log(
            channel='sms', recipient=customer.phone_number, message=message,
            event_type='payment_failed', customer=customer,
        )
    if customer.telegram_chat_id:
        send_and_log(
            channel='telegram', recipient=customer.telegram_chat_id, message=message,
            event_type='payment_failed', customer=customer,
        )


@shared_task
def send_suspension_notice(customer_id, subscription_id):
    """
    Called inline from apps.network.tasks.check_expired_subscriptions right
    after a subscription is flipped to 'expired' -- not a separate beat
    schedule entry. That task's own status='active' filter naturally
    prevents this firing more than once per subscription across repeated
    per-minute runs (an already-expired subscription no longer matches it).
    """
    from apps.billing.models import Subscription
    from apps.customers.models import Customer

    customer = Customer.objects.filter(id=customer_id).first()
    subscription = Subscription.objects.filter(id=subscription_id).select_related('plan').first()
    if not customer or not subscription:
        logger.warning(f"send_suspension_notice: customer {customer_id} or subscription {subscription_id} no longer exists")
        return

    message = (
        f"Your {subscription.plan.name} plan has expired and your connection has been suspended. "
        f"Renew now via M-Pesa or the customer portal to get back online."
    )

    if customer.phone_number:
        send_and_log(
            channel='sms', recipient=customer.phone_number, message=message,
            event_type='suspension', customer=customer, subscription=subscription,
        )
    if customer.telegram_chat_id:
        send_and_log(
            channel='telegram', recipient=customer.telegram_chat_id, message=message,
            event_type='suspension', customer=customer, subscription=subscription,
        )


@shared_task
def send_promo_broadcast(message, channels, service_type_filter='pppoe'):
    """
    Admin-triggered bulk send (PromoBroadcastView) -- not automated, not on
    the beat schedule. Iterates active customers matching service_type_filter
    ('pppoe' also matches 'both'; pass 'all' for every service type) and
    sends over every requested channel. A fixed delay between WhatsApp sends
    specifically throttles the bulk send to reduce the ban risk that comes
    with QR-paired WhatsApp (see whatsapp_service.py) -- not a general rate
    limiter, just a sane pause.
    """
    from apps.customers.models import Customer

    qs = Customer.objects.filter(status='active')
    if service_type_filter == 'pppoe':
        qs = qs.filter(service_type__in=['pppoe', 'both'])
    elif service_type_filter == 'hotspot':
        qs = qs.filter(service_type__in=['hotspot', 'both'])
    elif service_type_filter != 'all':
        qs = qs.filter(service_type=service_type_filter)

    sent_count = 0
    for customer in qs.iterator():
        for channel in channels:
            recipient = customer.telegram_chat_id if channel == 'telegram' else customer.phone_number
            if not recipient:
                continue
            result = send_and_log(
                channel=channel, recipient=recipient, message=message,
                event_type='promo_broadcast', customer=customer,
            )
            if result['success']:
                sent_count += 1
            if channel == 'whatsapp':
                time.sleep(getattr(settings, 'WHATSAPP_BROADCAST_DELAY_SECONDS', 4))

    logger.info(f"send_promo_broadcast: sent {sent_count} messages across {len(channels)} channel(s)")
    return sent_count


@shared_task
def send_voucher_notification(voucher_id, recipient, channel, customer_id=None):
    """
    Delivery only -- sending a voucher code doesn't consume it; redemption
    (VoucherRedeemView) is what flips its status.
    """
    from apps.billing.models import Voucher
    from apps.customers.models import Customer

    voucher = Voucher.objects.select_related('plan').filter(id=voucher_id).first()
    if not voucher:
        logger.warning(f"send_voucher_notification: voucher {voucher_id} no longer exists")
        return

    plan_name = voucher.plan.name if voucher.plan else 'your plan'
    message = f"Your hotspot voucher code: {voucher.code}, valid for {plan_name}. Use it at the login page."

    customer = Customer.objects.filter(id=customer_id).first() if customer_id else None
    send_and_log(
        channel=channel, recipient=recipient, message=message,
        event_type='voucher_send', customer=customer,
    )
