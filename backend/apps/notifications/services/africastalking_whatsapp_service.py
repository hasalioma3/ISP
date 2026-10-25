"""
Africa's Talking WhatsApp Business API (chat.africastalking.com). Same
credentials as the SMS integration; `whatsapp_at_number` is the business
number registered with Africa's Talking (the `waNumber` field).
"""
import logging

import requests

from apps.notifications.models import NotificationSettings
from apps.payments.services.phone_hash import normalize_phone

logger = logging.getLogger('notifications')


class AfricasTalkingWhatsAppService:
    def __init__(self):
        ns = NotificationSettings.load()
        self.username = (ns.at_username or '').strip()
        self.api_key = (ns.at_api_key or '').strip()
        self.wa_number = (ns.whatsapp_at_number or '').strip()
        # chat.sandbox.africastalking.com does not exist; WhatsApp has a single host.
        self.base_url = 'https://chat.africastalking.com'

    def send_message(self, phone_number, message):
        """Same {'success', 'data'|'error'} contract as the other senders; never raises."""
        if not self.wa_number:
            return {'success': False, 'error': "Africa's Talking WhatsApp number is not configured", 'data': None}
        to = normalize_phone(phone_number)
        payload = {
            'username': self.username,
            'waNumber': self.wa_number if self.wa_number.startswith('+') else f'+{self.wa_number}',
            'phoneNumber': f'+{to}',
            'body': {'message': message},
        }
        headers = {'apiKey': self.api_key, 'Accept': 'application/json', 'Content-Type': 'application/json'}
        try:
            response = requests.post(
                f'{self.base_url}/whatsapp/message/send', json=payload, headers=headers, timeout=30
            )
            try:
                data = response.json()
            except ValueError:
                data = {'raw': response.text[:500]}
            if response.ok:
                return {'success': True, 'data': data}
            detail = str(data)[:500].replace(self.api_key, '***') if self.api_key else str(data)[:500]
            return {'success': False, 'error': f"Africa's Talking WhatsApp returned HTTP {response.status_code}: {detail}", 'data': data}
        except requests.exceptions.RequestException as e:
            logger.error(f"AT WhatsApp send to {to} failed: {e}")
            return {'success': False, 'error': str(e), 'data': None}
