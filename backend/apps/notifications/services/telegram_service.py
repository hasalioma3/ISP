"""
Telegram Bot API integration -- a plain requests.post call, same style as
africastalking_service.py. Credentials come from NotificationSettings.
"""
import logging

import requests

from apps.notifications.models import NotificationSettings

logger = logging.getLogger('notifications')


class TelegramService:
    def __init__(self):
        self.token = NotificationSettings.load().telegram_bot_token

    def send_message(self, chat_id, message):
        """Same {'success': bool, 'data'|'error': ...} contract as the
        other channel services -- never raises."""
        if not self.token:
            return {'success': False, 'error': 'Telegram bot token not configured', 'data': None}

        try:
            response = requests.post(
                f'https://api.telegram.org/bot{self.token}/sendMessage',
                json={'chat_id': chat_id, 'text': message},
                timeout=30,
            )
            data = response.json()
            if data.get('ok'):
                return {'success': True, 'data': data}
            return {'success': False, 'error': data.get('description', 'Telegram send failed'), 'data': data}
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram send to {chat_id} failed: {e}")
            return {'success': False, 'error': str(e), 'data': None}
