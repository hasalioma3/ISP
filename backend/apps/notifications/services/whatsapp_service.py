"""
Talks to the whatsapp-service sidecar (Node.js, Baileys -- QR-paired
WhatsApp Web protocol, not the official Meta Cloud API). The sidecar is
internal-only (no published port, reachable only by service name on the
Docker network) -- Django is the only thing that calls it directly; the
browser sees status/QR through WhatsAppStatusView's proxy.
"""
import logging

import requests
from django.conf import settings

from apps.payments.services.phone_hash import normalize_phone

logger = logging.getLogger('notifications')


class WhatsAppService:
    def __init__(self):
        self.base_url = settings.WHATSAPP_SIDECAR_URL.rstrip('/')

    def send_message(self, phone_number, message):
        """
        Same {'success': bool, 'data'|'error': ...} contract as
        AfricasTalkingService.send_sms -- never raises. phone_number is
        normalized to 254XXXXXXXXX here (same helper send_sms uses) --
        a bare 07.../01... local-format number works for SMS already, so
        it needs to work here too rather than silently producing a
        malformed JID (the sidecar only strips non-digits, it doesn't add
        the country code).
        """
        to = normalize_phone(phone_number)
        try:
            response = requests.post(
                f'{self.base_url}/send', json={'phone': to, 'message': message}, timeout=30
            )
            data = response.json()
            if response.ok and data.get('success'):
                return {'success': True, 'data': data}
            return {'success': False, 'error': data.get('error', 'WhatsApp send failed'), 'data': data}
        except requests.exceptions.RequestException as e:
            logger.error(f"WhatsApp send to {to} failed: {e}")
            return {'success': False, 'error': str(e), 'data': None}

    def get_status(self):
        """Returns {'connected': bool, 'qr': <data URI or None>}, or a
        disconnected/error state if the sidecar itself is unreachable --
        the settings page should degrade to "not connected", not crash."""
        try:
            response = requests.get(f'{self.base_url}/status', timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"WhatsApp sidecar unreachable: {e}")
            return {'connected': False, 'qr': None, 'error': str(e)}
