"""
Safaricom's C2B API sends a SHA-256 hash of the paying MSISDN instead of the
real number (data-minimization rollout, effective since 2023-11-30 and fully
masked since 2026-03-24) -- see Daraja C2B Confirmation docs. The hash is
deterministic and computed over the number's full international format
(2547XXXXXXXX), so customers are matched by hashing our own stored numbers
the same way and comparing, never by reversing Safaricom's hash: doing that
would reconstruct a non-consenting payer's phone number, which is exactly
the kind of thing the Data Protection Act 2019 makes a merchant liable for
as the data controller.
"""
import hashlib


def normalize_phone(phone_number):
    """Coerce any Kenyan mobile format to 254XXXXXXXXX.

    Handles 07XXXXXXXX, +254XXXXXXXXX, 254XXXXXXXXX and the bare nine-digit
    form people often type or paste ("725316559", "712 345 678") -- the last
    one used to reach Africa's Talking/Daraja unchanged and be rejected as an
    invalid number. Spaces, dashes and brackets are dropped first. Anything
    that still isn't a Kenyan mobile is returned as-is (digits only) so the
    caller's own length check reports it.
    """
    raw = (phone_number or '').strip()
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if not digits:
        return raw
    if digits.startswith('254'):
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '254' + digits[1:]
    if len(digits) == 9 and digits[0] in '17':
        return '254' + digits
    return digits


def fix_bare_phone(phone_number):
    """Only repair the bare nine-digit form ("725316559" -> "254725316559");
    any other value (07..., 254..., +254..., foreign) is returned as typed,
    so valid stored numbers never change shape."""
    raw = (phone_number or '').strip()
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if len(digits) == 9 and digits[0] in '17' and not raw.startswith('+'):
        return '254' + digits
    return raw


def local_phone(phone_number):
    """254XXXXXXXXX / 9-digit / 07... -> 07XXXXXXXX, the format customer
    records and guest hotspot usernames have always used. Unrecognised input
    is returned stripped and unchanged."""
    full = normalize_phone(phone_number)
    if len(full) == 12 and full.startswith('254') and full.isdigit():
        return '0' + full[3:]
    return (phone_number or '').strip()


def hash_phone(phone_number):
    return hashlib.sha256(normalize_phone(phone_number).encode()).hexdigest()


def is_msisdn_hash(value):
    value = (value or '').lower()
    return len(value) == 64 and all(c in '0123456789abcdef' for c in value)
