"""
Africa's Talking SMS integration -- a plain requests.post call, same as
apps.payments.services.mpesa_service, rather than the africastalking PyPI
SDK: keeps this dependency-free (requests is already required for M-Pesa)
and consistent with how the rest of this project talks to external APIs.
"""

import logging

import requests
from django.conf import settings

from apps.payments.services.phone_hash import normalize_phone

logger = logging.getLogger('notifications')


class AfricasTalkingService:
    """
    Africa's Talking SMS API integration.
    """

    def __init__(self):
        self.username = settings.AFRICASTALKING_USERNAME
        self.api_key = settings.AFRICASTALKING_API_KEY
        self.sender_id = settings.AFRICASTALKING_SENDER_ID or None
        self.base_url = settings.AFRICASTALKING_BASE_URL

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

        except requests.exceptions.RequestException as e:
            logger.error(f"SMS request to {to} failed: {str(e)}")
            return {'success': False, 'error': str(e), 'data': None}


# Singleton instance
africastalking_service = AfricasTalkingService()
