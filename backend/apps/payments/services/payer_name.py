"""
Payer names from Safaricom C2B (Buy Goods / Paybill) confirmations.

Since the 2024 Daraja privacy change the payer's MSISDN arrives hashed (see
phone_hash.py), but FirstName still identifies who paid. Depending on the
account/API version it can come as plain text ("JOHN", what this
deployment receives) or base64, so this decodes what it recognises and
otherwise shows the value as received -- an unrecognised format is never
silently dropped.
"""
import base64
import binascii
import re

_BASE64 = re.compile(r'^[A-Za-z0-9+/]{4,}={0,2}$')
_NAMEISH = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")


def decode_name_part(value):
    """One FirstName/MiddleName/LastName value -> readable text ('' if none)."""
    raw = (value or '').strip()
    if not raw:
        return ''
    # Plain text -- what production actually receives ("HASSAN", "Samson",
    # checked 2026-11). Anything made only of letters (plus space . ' -) is
    # a name as-is: many real names ("Shadrack", "JOHN") are also valid
    # base64 and must never be "decoded" into garbage.
    if _NAMEISH.match(raw):
        return raw.title()
    if _BASE64.match(raw) and len(raw) % 4 == 0:
        try:
            decoded = base64.b64decode(raw, validate=True).decode('utf-8').strip()
        except (binascii.Error, UnicodeDecodeError, ValueError):
            decoded = ''
        if decoded and _NAMEISH.match(decoded):
            return decoded.title()
    return raw


def payer_display_name(payment):
    """'Grace Wanjiru' from a C2BPayment's name fields (decoded)."""
    parts = [decode_name_part(getattr(payment, f, '')) for f in ('first_name', 'middle_name', 'last_name')]
    return ' '.join(p for p in parts if p)
