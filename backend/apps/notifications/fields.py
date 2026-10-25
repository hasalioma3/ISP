"""
Fernet-based field encryption for notification channel credentials (AT API
key, Telegram bot token/webhook secret) stored in NotificationSettings.
The key itself (NOTIFICATIONS_ENCRYPTION_KEY) must stay in the environment,
never in the database -- encrypting a DB-stored secret with a key that's
also DB-stored is circular and protects nothing.
"""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    return Fernet(settings.NOTIFICATIONS_ENCRYPTION_KEY.encode())


class EncryptedCharField(models.CharField):
    """
    Transparently encrypts on write, decrypts on read. max_length is the
    DB column size (ciphertext, base64 -- roughly 1.5x the plaintext plus
    a fixed overhead), not the plaintext length.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            # Key rotated/missing -- fail closed (blank), never 500 just
            # because a secret can't be decrypted.
            return ''
