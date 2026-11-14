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

# Africa's Talking per-recipient statuses that need a human to act, explained
# in the notification log / test-send result instead of a bare code.
STATUS_HELP = {
    'UserInBlacklist': (
        "the number has blocked promotional SMS on Safaricom (Do Not Disturb). The customer can dial "
        "*456*9*5# to allow them; to reach everyone, get a transactional Sender ID approved and set it here"
    ),
    'DoNotDisturbRejection': "rejected by the network's Do Not Disturb rules -- use an approved transactional Sender ID",
    'InsufficientBalance': "your Africa's Talking account is out of credit -- top it up",
    'InvalidSenderId': "the Sender ID isn't approved for this account -- clear the field or use an approved one",
    'InvalidPhoneNumber': 'the phone number is not a valid mobile number',
    'UnsupportedNumberType': 'the number type (e.g. landline) cannot receive SMS',
    'AbsentSubscriber': 'the phone was off or out of coverage',
    'RiskHold': "Africa's Talking held the message for review (risk check)",
}


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
        # Fail before calling AT: a blank key (never saved, or saved under a
        # different NOTIFICATIONS_ENCRYPTION_KEY so it no longer decrypts --
        # EncryptedCharField reads that back as '') only ever earns a 401
        # that looks like a wrong key. config_error tells callers retrying
        # is pointless.
        if not self.username or not self.api_key:
            error = (
                "Africa's Talking username/API key not set (or the stored key can't be "
                "decrypted with this server's NOTIFICATIONS_ENCRYPTION_KEY) -- re-enter "
                "them under Settings -> Notifications."
            )
            logger.error(f"SMS to {to} not sent: {error}")
            return {'success': False, 'error': error, 'data': None, 'config_error': True}
        if not to.isdigit() or len(to) != 12:
            error = f'invalid phone number {phone_number!r} (expected 07XXXXXXXX / 2547XXXXXXXX)'
            logger.warning(f"SMS not sent: {error}")
            return {'success': False, 'error': error, 'data': None, 'config_error': True}
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
            try:
                response = requests.post(
                    f'{self.base_url}/version1/messaging', data=payload, headers=headers, timeout=30
                )
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as first_error:
                # One retry for a dropped/garbled connection (seen as "SSL record
                # layer failure" when the Pi's traffic goes through a tunnel such
                # as Cloudflare WARP). The message wasn't accepted, so resending
                # can't duplicate it.
                logger.warning(f"SMS to {to}: connection error ({first_error}); retrying once")
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
            if error_status in STATUS_HELP:
                error_status = f'{error_status}: {STATUS_HELP[error_status]}'
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
            if response is not None and response.status_code == 401:
                error += (
                    f" -- check the username ({self.username!r}) and API key belong to the same "
                    f"AT app, and that the environment ({'production' if 'sandbox' not in self.base_url else 'sandbox'}) "
                    "matches it: sandbox keys only work with username 'sandbox'."
                )
            logger.error(f"SMS request to {to} failed: {error}")
            return {'success': False, 'error': error, 'data': None}

        except requests.exceptions.RequestException as e:
            logger.error(f"SMS request to {to} failed: {str(e)}")
            return {'success': False, 'error': str(e), 'data': None}
