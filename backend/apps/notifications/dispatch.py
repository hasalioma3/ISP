"""
Generic per-channel dispatch, used by every notification flow added on top
of the original SMS-only ones (payment confirmation, expiry reminders --
apps.notifications.tasks keeps those on their own SMS-specific code path
untouched, to avoid regressing what already works in production). Every
new flow (welcome, payment-failed, suspension, promo broadcast, voucher
send) goes through send_and_log so there's exactly one place that calls a
channel's sender and writes the matching NotificationLog row.
"""
import logging

from apps.notifications.models import NotificationLog
from apps.notifications.services.africastalking_service import AfricasTalkingService
from apps.notifications.services.telegram_service import TelegramService
from apps.notifications.models import NotificationSettings
from apps.notifications.services.africastalking_whatsapp_service import AfricasTalkingWhatsAppService
from apps.notifications.services.whatsapp_service import WhatsAppService

logger = logging.getLogger('notifications')

def _send_whatsapp(recipient, message):
    if NotificationSettings.load().whatsapp_provider == 'africastalking':
        return AfricasTalkingWhatsAppService().send_message(recipient, message)
    return WhatsAppService().send_message(recipient, message)


SENDERS = {
    'sms': lambda recipient, message: AfricasTalkingService().send_sms(recipient, message),
    'whatsapp': lambda recipient, message: _send_whatsapp(recipient, message),
    'telegram': lambda recipient, message: TelegramService().send_message(recipient, message),
}


def send_and_log(*, channel, recipient, message, event_type, customer=None, subscription=None):
    """
    Returns the sender's {'success': bool, ...} result. Not sent at all
    (unknown channel, or no recipient for this customer/channel -- e.g. no
    phone number, or no linked Telegram chat) is also logged as a failure,
    so a missing-channel case always leaves an auditable trace.
    """
    sender = SENDERS.get(channel)
    if not sender:
        logger.warning(f"send_and_log: unknown channel {channel!r}")
        result = {'success': False, 'error': f'unknown channel {channel!r}', 'data': None}
    elif not recipient:
        result = {'success': False, 'error': f'no {channel} recipient', 'data': None}
    else:
        result = sender(recipient, message)

    NotificationLog.objects.create(
        customer=customer,
        subscription=subscription,
        channel=channel,
        event_type=event_type,
        recipient=str(recipient or ''),
        message=message,
        status='sent' if result['success'] else 'failed',
        error='' if result['success'] else str(result.get('error', '')),
        raw_response=result.get('data'),
    )
    return result
