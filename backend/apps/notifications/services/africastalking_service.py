"""
Africa's Talking SMS integration -- a plain requests.post call, same as
apps.payments.services.mpesa_service, rather than the africastalking PyPI
SDK: keeps this dependency-free (requests is already required for M-Pesa)
and consistent with how the rest of this project talks to external APIs.
"""

import logging

import requests

from apps.notifications.models import NotificationSettings
from apps.payments.services.phone_hash import normalize_phone

logger = logging.getLogger('notifications')


class AfricasTalkingService:
    """
    Africa's Talking SMS API integration. Credentials come from
    NotificationSettings (DB-backed, editable from the admin settings page)
    rather than env vars -- construct a fresh instance per send rather than
    caching one, since credentials can change at runtime.
    """

    def __init__(self):
        ns = NotificationSettings.load()
        # Credentials are commonly pasted from the provider dashboard.
        # Whitespace is not part of either credential and causes a 401.
        self.username = (ns.at_username or '').strip()
        self.api_key = (ns.at_api_key or '').strip()
        self.sender_id = (ns.at_sender_id or '').strip() or None
        self.base_url = (
            'https://api.africastalking.com' if ns.at_environment == 'production'
            else 'https://api.sandbox.africastalking.com'
        )

    def send_sms(self, phone_number, message):
        """
        Send a single SMS. phone_number is normalized to 254XXXXXXXXX here
        (defensively -- callers should already store/pass a sane number,
        but this is a cheap idempotent call and matches initiate_stk_push's
        own defensive formatting of phone_number for STK).

        Returns {'success': True, 'data': <AT response dict>} when AT
        accepted the message for the recipient, else
        {'success': False, 'error': str, 'data': <AT response dict or None>}.
        Never raises -- callers (Celery tasks) don't need to wrap this in
        their own try/except.
        """
        to = normalize_phone(phone_number)
        payload = {
            'username': self.username,
            'to': f'+{to}',
            'message': message,
        }
        if self.sender_id:
            payload['from'] = self.sender_id

        headers = {
            'apiKey': self.api_key,
            'Accept': 'application/json',
        }

        try:
            response = requests.post(
                f'{self.base_url}/version1/messaging', data=payload, headers=headers, timeout=30
            )
            response.raise_for_status()
            data = response.json()

            recipients = data.get('SMSMessageData', {}).get('Recipients', [])
            if recipients and recipients[0].get('status') == 'Success':
                logger.info(f"SMS sent to {to}: messageId={recipients[0].get('messageId')}")
                return {'success': True, 'data': data}

            error_status = (
                recipients[0].get('status') if recipients
                else data.get('SMSMessageData', {}).get('Message', 'Unknown error')
            )
            logger.warning(f"SMS to {to} not accepted: {error_status}")
            return {'success': False, 'error': error_status, 'data': data}

        except requests.exceptions.HTTPError as e:
            response = e.response
            detail = response.text.strip() if response is not None else ''
            if detail:
                detail = detail[:500].replace(self.api_key, '[redacted]')
                error = f'Africa\'s Talking returned HTTP {response.status_code}: {detail}'
            else:
                error = str(e)
            logger.error(f"SMS request to {to} failed: {error}")
            return {'success': False, 'error': error, 'data': None}

        except requests.exceptions.RequestException as e:
            logger.error(f"SMS request to {to} failed: {str(e)}")
            return {'success': False, 'error': str(e), 'data': None}
