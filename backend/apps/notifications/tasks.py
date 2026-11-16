import logging
import time
from datetime import datetime, time as dtime, timedelta
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


def send_confirmation(customer, message, event_type, subscription=None):
    """
    Deliver a confirmation on the channels chosen in Settings ->
    Notifications -> Payment confirmations (WhatsApp by default). If none of
    them got through and the SMS fallback is on, try SMS. Every attempt is
    in the notification log. Returns True if any channel delivered it.
    """
    settings_obj = NotificationSettings.load()
    return send_with_fallback(customer, message, event_type, settings_obj.confirmation_channel_list(),
                              settings_obj.confirmation_sms_fallback, subscription=subscription)


@shared_task
def send_payment_confirmation_sms(customer_id, event_type, amount, subscription_id=None):
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

    # Only the service types ticked in Settings -> Notifications get
    # confirmations (default: PPPoE only, not hotspot).
    if not NotificationSettings.load().confirmations_enabled_for(customer.service_type):
        logger.info(f"Confirmation for {customer.username} skipped: {customer.service_type} confirmations are off")
        return

    from apps.notifications.templates import render
    if event_type == 'payment_confirmation' and subscription:
        message = render('payment_confirmation', {
            'amount': amount, 'plan': subscription.plan.name,
            'expiry': timezone.localtime(subscription.expiry_date).strftime('%d %b %Y %H:%M'),
        }, customer)
    else:
        event_type = 'balance_credit'
        message = render('balance_credit', {'amount': amount, 'balance': customer.account_balance}, customer)

    send_confirmation(customer, message, event_type, subscription)

def send_with_fallback(customer, message, event_type, channels, sms_fallback, subscription=None):
    """
    Send `message` to the customer on each channel in `channels` they have an
    address for; if none delivered and sms_fallback is on, try SMS. Every
    attempt is in the notification log. Returns True if anything got through.
    """
    delivered = False
    for channel in channels:
        recipient = customer.email if channel == 'email' else customer.phone_number
        if not recipient:
            continue
        result = send_and_log(channel=channel, recipient=recipient, message=message, event_type=event_type,
                              customer=customer, subscription=subscription)
        delivered = delivered or result['success']
    if not delivered and sms_fallback and 'sms' not in channels and customer.phone_number:
        logger.info(f"{event_type} for {customer.username} not delivered on {channels}; falling back to SMS")
        delivered = send_and_log(channel='sms', recipient=customer.phone_number, message=message,
                                 event_type=event_type, customer=customer, subscription=subscription)['success']
    return delivered


def _reminder_when(days_left, expiry):
    local = timezone.localtime(expiry)
    if days_left == 0:
        return f"expires today at {local.strftime('%H:%M')}"
    if days_left == 1:
        return f"expires tomorrow ({local.strftime('%d %b, %H:%M')})"
    return f"expires in {days_left} days (on {local.strftime('%d %b')})"


@shared_task
def send_expiry_reminders(force=False):
    """
    Renewal reminders, as set in Settings -> Notifications -> Renewal
    reminders: the first `reminder_days_before` days before expiry, then
    every `reminder_every_days` days, plus one on the expiry day itself
    (NotificationSettings.reminder_offsets). Runs hourly from beat and only
    does anything in the configured hour, so changing the send time in the
    UI needs no beat change; `force` skips the hour check (tests/manual runs).

    Only the customer's latest live subscription is reminded -- someone who
    already renewed (a later subscription is queued/active) isn't nagged
    about the old one. Dedup is one 'expiry_reminder' log row per
    subscription per day, so a re-run in the same hour never double-sends,
    and a renewal opens a fresh window by itself.
    """
    from apps.billing.models import Subscription

    ns = NotificationSettings.load()
    if not ns.reminder_enabled:
        return 0
    now = timezone.localtime()
    if not force and now.hour != ns.reminder_hour:
        return 0
    offsets = ns.reminder_offsets()
    if not offsets:
        return 0
    today = now.date()
    targets = {today + timedelta(days=d): d for d in offsets}

    # 'expired' too: check_expired_subscriptions flips a subscription the
    # minute it passes expiry, so one that ran out this morning would
    # otherwise miss its day-of reminder.
    subs = (
        Subscription.objects.filter(status__in=['active', 'expired'])
        .filter(plan__service_type__in=ns.reminder_service_type_list())
        .select_related('customer', 'plan')
    )
    # expiry_date__date uses the DB/UTC date on some backends; compare in
    # Nairobi time in Python over a slightly wider window instead.
    lo = timezone.make_aware(datetime.combine(min(targets), dtime.min)) - timedelta(days=1)
    hi = timezone.make_aware(datetime.combine(max(targets), dtime.max)) + timedelta(days=1)
    subs = subs.filter(expiry_date__gte=lo, expiry_date__lte=hi)

    from apps.notifications.templates import render
    from apps.customers.reminders import how_to_pay

    channels = ns.reminder_channel_list()
    sent_count = 0
    for sub in subs:
        days_left = targets.get(timezone.localtime(sub.expiry_date).date())
        if days_left is None:
            continue
        # Already renewed: a later subscription exists for this customer.
        if Subscription.objects.filter(
            customer=sub.customer, status__in=['active', 'pending'], expiry_date__gt=sub.expiry_date
        ).exclude(pk=sub.pk).exists():
            continue
        if NotificationLog.objects.filter(
            subscription=sub, event_type='expiry_reminder', created_at__date=today
        ).exists():
            continue
        price = f"KES {sub.plan.price:,.0f}"
        message = render('expiry_reminder', {
            'plan': sub.plan.name,
            'when': _reminder_when(days_left, sub.expiry_date),
            'days_left': days_left,
            'expiry': timezone.localtime(sub.expiry_date).strftime('%d %b %Y %H:%M'),
            'price': price,
            'how_to_pay': how_to_pay(sub.customer, price),
        }, sub.customer)
        if send_with_fallback(sub.customer, message, 'expiry_reminder', channels,
                              ns.reminder_sms_fallback, subscription=sub):
            sent_count += 1

    logger.info(f"send_expiry_reminders: sent {sent_count} reminders (days before: {offsets})")
    return sent_count


def expired_today(day=None):
    """
    Subscriptions that ran out on `day` (default today, Nairobi time) whose
    customer hasn't renewed since -- the sales follow-up list.

    PPPoE only: hotspot users are walk-up/voucher buyers with no account to
    chase (and are most of the expiries, which would bury the real
    follow-ups), and static-IP customers are excluded too, as asked.
    """
    from apps.billing.models import Subscription

    day = day or timezone.localdate()
    start = timezone.make_aware(datetime.combine(day, dtime.min))
    end = min(start + timedelta(days=1), timezone.now())
    rows = []
    seen = set()
    subs = (
        Subscription.objects.filter(expiry_date__gte=start, expiry_date__lt=end, plan__service_type='pppoe')
        .exclude(status='cancelled')
        .select_related('customer', 'plan').order_by('expiry_date')
    )
    for sub in subs:
        c = sub.customer
        if c.id in seen or c.is_staff:
            continue
        if Subscription.objects.filter(customer=c, status__in=['active', 'pending'],
                                       expiry_date__gt=timezone.now()).exists():
            continue  # renewed already
        seen.add(c.id)
        rows.append({
            'name': c.get_full_name() or c.username,
            'username': c.username,
            'phone': c.phone_number or '',
            'plan': sub.plan.name,
            'service_type': sub.plan.service_type,
            'price': sub.plan.price,
            'expired_at': timezone.localtime(sub.expiry_date).strftime('%H:%M'),
        })
    return rows


@shared_task
def send_expired_followup(force=False):
    """
    Evening list of customers who expired today and haven't renewed, to the
    admin contacts and the sales contacts so someone can call them. Runs
    hourly from beat; sends in expired_followup_hour, once a day (dedup on
    the log). Nothing is sent on a day with no expiries.
    """
    import csv
    import io
    from apps.notifications.admin_emails import admin_email_recipients, _html_page, _company
    from apps.notifications.services.email_service import EmailService

    ns = NotificationSettings.load()
    if not ns.expired_followup_enabled:
        return 0
    now = timezone.localtime()
    if not force and now.hour != ns.expired_followup_hour:
        return 0
    if not force and NotificationLog.objects.filter(
        event_type='expired_followup', created_at__date=now.date()
    ).exists():
        return 0
    rows = expired_today(now.date())
    if not rows:
        logger.info("send_expired_followup: no unrenewed expiries today")
        return 0

    day = now.strftime('%d %b %Y')
    subject = f"{len(rows)} customer{'s' if len(rows) != 1 else ''} expired today ({day}) - follow up"
    cols = ['Name', 'Username', 'Phone', 'Plan', 'Type', 'Price', 'Expired at']
    table = [[r['name'], r['username'], r['phone'], r['plan'], r['service_type'].upper(),
              f"KES {r['price']:,.0f}", r['expired_at']] for r in rows]
    text = subject + '\n\n' + '\n'.join(
        f"- {r['name']} ({r['username']}) {r['phone']} - {r['plan']}, expired {r['expired_at']}" for r in rows)
    html = _html_page(f'Expired today - {day}',
                      'These customers\' plans ran out today and they have not renewed yet.',
                      [(None, cols, table)])
    buf = io.StringIO()
    csv.writer(buf).writerows([cols] + table)
    attachments = [(f"expired_{now.strftime('%Y%m%d')}.csv", buf.getvalue(), 'text/csv')]

    # Phones get a compact list; long lists are cut to keep SMS cost sane.
    lines = [f"{r['name']} {r['phone']} ({r['plan']})" for r in rows[:15]]
    if len(rows) > 15:
        lines.append(f"+{len(rows) - 15} more (see email)")
    short = f"{_company()}: {len(rows)} expired today, not renewed:\n" + '\n'.join(lines)

    delivered = 0
    emails = list(dict.fromkeys(admin_email_recipients() + ns.sales_email_list())) if ns.email_enabled else []
    if emails:
        service = EmailService()
        for recipient in emails:
            result = service.send_email(recipient, text, subject=subject, html=html, attachments=attachments)
            NotificationLog.objects.create(
                channel='email', event_type='expired_followup', recipient=recipient,
                message=text[:5000], status='sent' if result['success'] else 'failed',
                error='' if result['success'] else str(result.get('error', '')),
            )
            delivered += bool(result['success'])
    for phone in dict.fromkeys(ns.phone_list() + ns.sales_phone_list()):
        for channel in ns.phone_channels():
            delivered += bool(send_and_log(channel=channel, recipient=phone, message=short,
                                           event_type='expired_followup')['success'])
    logger.info(f"send_expired_followup: {len(rows)} customers, {delivered} deliveries")
    return delivered


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
    from apps.notifications.templates import customer_context, fill

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
            recipient = {
                'telegram': customer.telegram_chat_id,
                'email': customer.email,
            }.get(channel, customer.phone_number)
            if not recipient:
                continue
            # Promotional templates can use {first_name}, {company}, ...
            try:
                text = fill(message, customer_context(customer))
            except (ValueError, IndexError):
                text = message  # stray braces: send it exactly as typed
            result = send_and_log(
                channel=channel, recipient=recipient, message=text,
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

    customer = Customer.objects.filter(id=customer_id).first() if customer_id else None
    from apps.notifications.templates import render
    message = render('voucher_send', {'code': voucher.code, 'plan': plan_name}, customer)
    send_and_log(
        channel=channel, recipient=recipient, message=message,
        event_type='voucher_send', customer=customer,
    )


@shared_task
def send_staff_alert(message, customer_id=None, subscription_id=None):
    """
    Tell every admin contact (Settings -> Notifications -> Admin contacts)
    about a money-affecting manual action: a subscription extended or cash
    added. Phones get the text on each chosen channel; emails get it by
    email. Enqueued on commit by apps.customers.views.
    """
    from apps.customers.models import Customer
    from apps.billing.models import Subscription
    from apps.notifications.admin_emails import notify_admins

    notify_admins(
        'staff_alert', subject=message[:78], text=message, sms_text=message,
        customer=Customer.objects.filter(id=customer_id).first() if customer_id else None,
        subscription=Subscription.objects.filter(id=subscription_id).first() if subscription_id else None,
    )


@shared_task
def send_customer_account_notice(customer_id, template_key, context, event_type, subscription_id=None):
    """
    Tell the customer about a change staff made to their account (plan
    recharged/extended, cash credited), worded by the `template_key`
    template. SMS, plus email when email is set up and they have an address.
    Follows the same service-type rule as payment confirmations.
    """
    from apps.customers.models import Customer
    from apps.billing.models import Subscription
    from apps.notifications.templates import render

    customer = Customer.objects.filter(id=customer_id).first()
    if not customer:
        return
    settings_obj = NotificationSettings.load()
    if not settings_obj.confirmations_enabled_for(customer.service_type):
        return
    message = render(template_key, context, customer)
    subscription = Subscription.objects.filter(id=subscription_id).first() if subscription_id else None
    send_confirmation(customer, message, event_type, subscription)


@shared_task
def send_payment_reminder(customer_id, channel='sms', message=None):
    """
    One subscriber's message from the Subscribers page "Send message": their
    payment reminder, or `message` (staff-written text with placeholders).
    """
    from apps.customers.models import Customer
    from apps.customers.reminders import build_payment_reminder
    from apps.notifications.templates import customer_context, fill

    customer = Customer.objects.filter(id=customer_id).first()
    if not customer:
        return
    if message:
        text, event_type = fill(message, customer_context(customer)), 'custom_message'
    else:
        text, event_type = build_payment_reminder(customer), 'payment_reminder'
    if not text:
        return
    recipient = {
        'email': customer.email, 'telegram': customer.telegram_chat_id,
    }.get(channel, customer.phone_number)
    send_and_log(channel=channel, recipient=recipient, message=text, event_type=event_type, customer=customer)



# Superadmin email tasks live in admin_emails.py; importing registers them with Celery.
from apps.notifications import admin_emails  # noqa: E402,F401
