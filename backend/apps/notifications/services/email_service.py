"""
Email over SMTP, configured in the database (Settings -> Notifications ->
Email), not in env, like the other channels. Returns the same
{'success', 'error', 'data'} shape as the SMS/WhatsApp senders so it plugs
into dispatch.send_and_log.
"""
import logging
from email.utils import formataddr

from django.core.mail import EmailMessage, get_connection

from apps.notifications.models import NotificationSettings

logger = logging.getLogger('notifications')

SMTP_TIMEOUT = 15


class EmailService:
    def __init__(self):
        self.settings = NotificationSettings.load()

    def _connection(self):
        host, port, security = self.settings.smtp_connection_settings()
        return get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=host,
            port=port,
            username=self.settings.smtp_username,
            password=self.settings.smtp_password,
            use_tls=security == 'starttls',
            use_ssl=security == 'ssl',
            timeout=SMTP_TIMEOUT,
            fail_silently=False,
        )

    def send_email(self, recipient, message, subject=None):
        s = self.settings
        if not s.email_enabled:
            return {'success': False, 'error': 'Email is turned off in Settings -> Notifications', 'data': None, 'config_error': True}
        host, _, _ = s.smtp_connection_settings()
        if not host or not s.smtp_username or not s.smtp_password:
            return {'success': False, 'error': 'SMTP host, username or password not set', 'data': None, 'config_error': True}
        sender = s.email_from_address or s.smtp_username
        from_header = formataddr((s.email_from_name, sender)) if s.email_from_name else sender
        if subject is None:
            # Notifications are short texts; use the first sentence as subject.
            subject = (message.split('. ')[0] or message)[:78]
        try:
            sent = EmailMessage(
                subject=subject, body=message, from_email=from_header, to=[recipient],
                connection=self._connection(),
            ).send()
            return {'success': bool(sent), 'error': '' if sent else 'Mail server accepted no recipients', 'data': {'sent': sent}}
        except Exception as e:  # SMTPAuthenticationError, timeouts, refused connections...
            hint = ''
            if 'Username and Password not accepted' in str(e) or '535' in str(e):
                hint = (' -- for Gmail use an App Password (Google Account -> Security -> App passwords), '
                        'not your normal password')
            logger.error('Email to %s failed: %s', recipient, e)
            return {'success': False, 'error': f'{type(e).__name__}: {e}{hint}', 'data': None}
