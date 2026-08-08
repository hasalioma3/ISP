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
    """Coerce 07XXXXXXXX / +254XXXXXXXXX / 254XXXXXXXXX to 254XXXXXXXXX."""
    phone_number = (phone_number or '').strip()
    if phone_number.startswith('0'):
        return '254' + phone_number[1:]
    if phone_number.startswith('+'):
        return phone_number[1:]
    return phone_number


def hash_phone(phone_number):
    return hashlib.sha256(normalize_phone(phone_number).encode()).hexdigest()


def is_msisdn_hash(value):
    value = (value or '').lower()
    return len(value) == 64 and all(c in '0123456789abcdef' for c in value)
