"""
Notification service layer.

Call `notify_customer(customer, event, context)` or
`notify_admins(event, context)` from anywhere in the codebase -- both are
fire-and-forget: they build the message from the event template, create a
NotificationLog row per channel, and hand delivery to Celery (falling back
to a synchronous send if the broker is unavailable, e.g. in development).

Neither function ever raises: a notification failure must never break the
business flow (payment processing, suspension, registration) that emitted it.
"""

import logging

from django.conf import settings

logger = logging.getLogger('apps.notifications')

# Message templates per event. Placeholders are filled from the `context`
# dict passed by the caller; missing keys render as ''.
CUSTOMER_TEMPLATES = {
    'welcome': (
        "Hi {name}, welcome to {company}! Your account ({username}) has been "
        "created. Buy a plan to activate your internet. Need help? Just reply "
        "to this message."
    ),
    'payment_received': (
        "Hi {name}, payment of {currency} {amount} received (receipt "
        "{receipt}). Your {plan} plan is active until {expiry}. Thank you for "
        "choosing {company}!"
    ),
    'payment_failed': (
        "Hi {name}, your payment could not be completed: {reason}. No money "
        "was deducted for this attempt. Please try again or contact support."
    ),
    'subscription_expiring': (
        "Hi {name}, your {plan} plan expires on {expiry}. Renew now to avoid "
        "disconnection. - {company}"
    ),
    'subscription_expired': (
        "Hi {name}, your {plan} plan has expired and your connection has been "
        "paused. Renew to get back online instantly. - {company}"
    ),
}

ADMIN_TEMPLATES = {
    'new_registration': (
        "[{company}] New customer: {name} ({username}), phone {phone}, "
        "service {service_type}."
    ),
    'payment_received': (
        "[{company}] Payment: {currency} {amount} from {name} ({phone}) for "
        "{plan}. Receipt {receipt}."
    ),
    'subscription_expired': (
        "[{company}] {count} subscription(s) expired and were suspended: "
        "{customers}"
    ),
}


class _SafeDict(dict):
    def __missing__(self, key):
        return ''


def _company_name():
    try:
        from apps.sitesettings.models import SiteSettings
        return SiteSettings.load().company_name
    except Exception:
        return 'ISP'


def _render(template, context):
    ctx = _SafeDict(context or {})
    ctx.setdefault('company', _company_name())
    return template.format_map(ctx)


def _dispatch(channel, recipient, message, event, customer=None, audience='customer'):
    """Create the log row and queue the actual send."""
    from apps.notifications.models import NotificationLog
    from apps.notifications.tasks import send_notification

    log = NotificationLog.objects.create(
        customer=customer,
        audience=audience,
        channel=channel,
        recipient=str(recipient),
        event=event,
        message=message,
    )
    try:
        send_notification.delay(log.id)
    except Exception as exc:
        # Broker down (common in dev) -- send in-process rather than dropping.
        logger.warning(f"Celery unavailable ({exc}); sending notification {log.id} synchronously")
        try:
            send_notification(log.id)
        except Exception:
            logger.error(f"Synchronous send failed for notification {log.id}", exc_info=True)


def notify_customer(customer, event, context=None):
    """
    Send `event` to a customer over every channel that is globally enabled,
    opted into by the customer, and has a usable address.
    """
    try:
        template = CUSTOMER_TEMPLATES.get(event)
        if not template:
            logger.error(f"Unknown customer notification event '{event}'")
            return

        context = dict(context or {})
        context.setdefault('name', customer.first_name or customer.username)
        context.setdefault('username', customer.username)
        message = _render(template, context)

        if settings.NOTIFY_SMS_ENABLED and customer.notify_sms and customer.phone_number:
            _dispatch('sms', customer.phone_number, message, event, customer)

        if settings.NOTIFY_WHATSAPP_ENABLED and customer.notify_whatsapp and customer.phone_number:
            _dispatch('whatsapp', customer.phone_number, message, event, customer)

        if settings.NOTIFY_TELEGRAM_ENABLED and customer.notify_telegram and customer.telegram_chat_id:
            _dispatch('telegram', customer.telegram_chat_id, message, event, customer)
    except Exception:
        logger.error(f"notify_customer({event}) failed", exc_info=True)


def _admin_phone_numbers():
    """Staff admins' phone numbers plus any extras from ADMIN_NOTIFY_PHONES."""
    from apps.customers.models import Customer

    phones = set(settings.ADMIN_NOTIFY_PHONES)
    staff_phones = Customer.objects.filter(
        is_staff=True, is_active=True, role='admin'
    ).exclude(phone_number='').values_list('phone_number', flat=True)
    phones.update(staff_phones)
    return phones


def notify_admins(event, context=None):
    """
    Send `event` to the admin team: staff admins (by phone) over SMS/WhatsApp
    and the chat IDs in ADMIN_TELEGRAM_CHAT_IDS over Telegram.
    """
    try:
        template = ADMIN_TEMPLATES.get(event)
        if not template:
            logger.error(f"Unknown admin notification event '{event}'")
            return

        message = _render(template, context)
        customer = (context or {}).get('_customer')  # for log linkage only

        if settings.NOTIFY_SMS_ENABLED or settings.NOTIFY_WHATSAPP_ENABLED:
            for phone in _admin_phone_numbers():
                if settings.NOTIFY_SMS_ENABLED:
                    _dispatch('sms', phone, message, event, customer, audience='admin')
                if settings.NOTIFY_WHATSAPP_ENABLED:
                    _dispatch('whatsapp', phone, message, event, customer, audience='admin')

        if settings.NOTIFY_TELEGRAM_ENABLED:
            for chat_id in settings.ADMIN_TELEGRAM_CHAT_IDS:
                _dispatch('telegram', chat_id, message, event, customer, audience='admin')
    except Exception:
        logger.error(f"notify_admins({event}) failed", exc_info=True)
