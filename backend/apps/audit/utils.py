import datetime
import decimal
import uuid

MASK = '••••••'
SENSITIVE_WORDS = ('password', 'passphrase', 'secret', 'api_key', 'apikey', 'token', 'passkey', 'consumer_key', 'device_code',
                   'private_key', 'credential', 'pin')


def is_sensitive(name):
    name = (name or '').lower()
    return any(w in name for w in SENSITIVE_WORDS)


def mask(data):
    """Copy of a request body with secret-looking keys replaced by MASK."""
    if isinstance(data, dict):
        return {k: (MASK if is_sensitive(k) and v not in ('', None) else mask(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [mask(v) for v in data[:200]]
    return data


def json_value(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return f'<{len(bytes(value))} bytes>'
    if isinstance(value, (dict, list)):
        text = str(value)
        return value if len(text) <= 1000 else text[:1000] + '…'
    text = str(value)
    return text if len(text) <= 500 else text[:500] + '…'
