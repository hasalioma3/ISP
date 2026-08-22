"""
Low-level channel providers for outbound notifications.

Every function returns (success: bool, detail: str). `detail` is the provider
message ID on success or a human-readable error on failure -- it is stored in
NotificationLog either way, so no provider errors are silently swallowed.

Supported providers (selected via settings, credentials from .env):
    SMS       - Africa's Talking (default, KE-friendly) or Twilio
    WhatsApp  - Meta WhatsApp Cloud API (default) or Twilio WhatsApp
    Telegram  - Telegram Bot API
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger('apps.notifications')

REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_phone(phone):
    """
    Normalize a phone number to E.164 (+254712345678).
    Handles the common Kenyan formats: 0712..., 712..., 254712..., +254712...
    The default country code is configurable (NOTIFY_DEFAULT_COUNTRY_CODE).
    """
    if not phone:
        return None
    cc = getattr(settings, 'NOTIFY_DEFAULT_COUNTRY_CODE', '254')
    digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    if not digits:
        return None
    if digits.startswith('0'):
        digits = cc + digits[1:]
    elif not digits.startswith(cc) and len(digits) <= 10:
        digits = cc + digits
    return '+' + digits


def _twilio_message(to, body, from_):
    """Send a message through Twilio's Messages API (used for SMS and WhatsApp)."""
    sid = settings.TWILIO_ACCOUNT_SID
    token = settings.TWILIO_AUTH_TOKEN
    if not (sid and token and from_):
        return False, 'Twilio credentials/sender not configured'

    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={'From': from_, 'To': to, 'Body': body},
        timeout=REQUEST_TIMEOUT,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code in (200, 201):
        return True, data.get('sid', 'sent')
    return False, f"Twilio {resp.status_code}: {data.get('message', resp.text[:200])}"


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

def send_sms(phone, message):
    phone = normalize_phone(phone)
    if not phone:
        return False, 'No valid phone number'

    provider = settings.SMS_PROVIDER

    if provider == 'twilio':
        return _twilio_message(phone, message, settings.TWILIO_SMS_FROM)

    if provider == 'africastalking':
        username = settings.AFRICASTALKING_USERNAME
        api_key = settings.AFRICASTALKING_API_KEY
        if not (username and api_key):
            return False, "Africa's Talking credentials not configured"

        # Sandbox account uses a different host
        host = ('https://api.sandbox.africastalking.com'
                if username == 'sandbox' else 'https://api.africastalking.com')
        payload = {'username': username, 'to': phone, 'message': message}
        if settings.AFRICASTALKING_SENDER_ID:
            payload['from'] = settings.AFRICASTALKING_SENDER_ID

        resp = requests.post(
            f"{host}/version1/messaging",
            headers={'apiKey': api_key, 'Accept': 'application/json'},
            data=payload,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            try:
                recipients = resp.json()['SMSMessageData']['Recipients']
                first = recipients[0] if recipients else {}
                # statusCode 100/101/102 = processed/sent/queued
                if first.get('statusCode') in (100, 101, 102):
                    return True, first.get('messageId', 'sent')
                return False, f"AT status: {first.get('status', 'unknown')}"
            except (ValueError, KeyError, IndexError):
                return False, f"AT unexpected response: {resp.text[:200]}"
        return False, f"AT {resp.status_code}: {resp.text[:200]}"

    return False, f"Unknown SMS provider '{provider}'"


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

def send_whatsapp(phone, message):
    phone = normalize_phone(phone)
    if not phone:
        return False, 'No valid phone number'

    provider = settings.WHATSAPP_PROVIDER

    if provider == 'twilio':
        return _twilio_message(
            f"whatsapp:{phone}", message, f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}"
        )

    if provider == 'meta':
        token = settings.WHATSAPP_ACCESS_TOKEN
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        if not (token and phone_number_id):
            return False, 'WhatsApp Cloud API credentials not configured'

        # NOTE: free-form text is only delivered inside the 24h customer
        # service window. Outside it, Meta requires a pre-approved template
        # message -- see the README notifications section.
        resp = requests.post(
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{phone_number_id}/messages",
            headers={'Authorization': f'Bearer {token}'},
            json={
                'messaging_product': 'whatsapp',
                'to': phone.lstrip('+'),
                'type': 'text',
                'text': {'body': message},
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code == 200:
            try:
                return True, data['messages'][0]['id']
            except (KeyError, IndexError):
                return True, 'sent'
        err = data.get('error', {}).get('message', resp.text[:200])
        return False, f"WhatsApp {resp.status_code}: {err}"

    return False, f"Unknown WhatsApp provider '{provider}'"


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram(chat_id, message):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return False, 'Telegram bot token not configured'
    if not chat_id:
        return False, 'No Telegram chat ID'

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={'chat_id': str(chat_id), 'text': message},
        timeout=REQUEST_TIMEOUT,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code == 200 and data.get('ok'):
        return True, str(data.get('result', {}).get('message_id', 'sent'))
    return False, f"Telegram {resp.status_code}: {data.get('description', resp.text[:200])}"


SENDERS = {
    'sms': send_sms,
    'whatsapp': send_whatsapp,
    'telegram': send_telegram,
}
