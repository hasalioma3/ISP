"""
Safaricom Daraja client for the platform's own shortcode: STK push (ISPs
paying platform invoices), STK query (verifying an ISP customer's payment
before crediting it), C2B URL registration, and payouts to ISPs -- B2B
(BusinessPayBill / BusinessBuyGoods) or B2C (BusinessPayment).

Written against Daraja's documented JSON shapes; the ISP app has its own
client for its STK pushes and is left untouched.
"""
import base64
import logging
import time
from datetime import datetime

import requests
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from django.utils import timezone

logger = logging.getLogger('cloud.daraja')

TIMEOUT = 30
_tokens = {}  # (base_url, key) -> (token, expires_at)


class DarajaError(Exception):
    pass


def security_credential(certificate_pem, initiator_password):
    """Daraja's SecurityCredential: the initiator password RSA-encrypted
    (PKCS#1 v1.5) with Safaricom's public certificate, base64."""
    if not certificate_pem or not initiator_password:
        raise DarajaError('Set the initiator password and the Safaricom certificate first (Settings -> M-Pesa)')
    try:
        cert = x509.load_pem_x509_certificate(certificate_pem.strip().encode())
    except ValueError as e:
        raise DarajaError(f'The Safaricom certificate is not a valid PEM certificate: {e}')
    encrypted = cert.public_key().encrypt(initiator_password.encode(), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


class Daraja:
    def __init__(self, cfg, consumer_key=None, consumer_secret=None):
        self.cfg = cfg
        self.base = cfg.mpesa_base_url
        self.key = consumer_key or cfg.mpesa_consumer_key
        self.secret = consumer_secret or cfg.mpesa_consumer_secret
        if not (self.key and self.secret):
            raise DarajaError('Daraja consumer key/secret are not set (Settings -> M-Pesa)')

    # -- plumbing --

    def token(self):
        cache_key = (self.base, self.key)
        cached = _tokens.get(cache_key)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        try:
            resp = requests.get(f'{self.base}/oauth/v1/generate', params={'grant_type': 'client_credentials'},
                                auth=(self.key, self.secret), timeout=TIMEOUT)
        except requests.RequestException as e:
            raise DarajaError(f'Could not reach Safaricom: {e.__class__.__name__}')
        if resp.status_code != 200:
            raise DarajaError(f'Safaricom rejected the consumer key/secret (HTTP {resp.status_code})')
        data = resp.json()
        _tokens[cache_key] = (data['access_token'], time.time() + int(data.get('expires_in', 3599)))
        return data['access_token']

    def post(self, path, payload):
        try:
            resp = requests.post(f'{self.base}{path}', json=payload, timeout=TIMEOUT,
                                 headers={'Authorization': f'Bearer {self.token()}'})
        except requests.RequestException as e:
            raise DarajaError(f'Could not reach Safaricom: {e.__class__.__name__}')
        try:
            data = resp.json()
        except ValueError:
            raise DarajaError(f'Unexpected reply from Safaricom (HTTP {resp.status_code})')
        if resp.status_code >= 400:
            raise DarajaError(data.get('errorMessage') or data.get('ResponseDescription') or f'HTTP {resp.status_code}')
        return data

    def _password(self, stamp):
        raw = f'{self.cfg.mpesa_shortcode}{self.cfg.mpesa_passkey}{stamp}'
        return base64.b64encode(raw.encode()).decode()

    # -- STK --

    def stk_push(self, phone, amount, account_ref, description, callback_url):
        stamp = timezone.localtime().strftime('%Y%m%d%H%M%S')
        till = self.cfg.mpesa_shortcode_type == 'till'
        return self.post('/mpesa/stkpush/v1/processrequest', {
            'BusinessShortCode': self.cfg.mpesa_shortcode,
            'Password': self._password(stamp),
            'Timestamp': stamp,
            'TransactionType': 'CustomerBuyGoodsOnline' if till else 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone,
            'PartyB': (self.cfg.mpesa_till_number or self.cfg.mpesa_shortcode) if till else self.cfg.mpesa_shortcode,
            'PhoneNumber': phone,
            'CallBackURL': callback_url,
            'AccountReference': account_ref[:12],
            'TransactionDesc': description[:13],
        })

    def stk_query(self, checkout_request_id):
        """-> (state, description): state is 'paid', 'failed' or 'pending'."""
        stamp = datetime.now().strftime('%Y%m%d%H%M%S')
        try:
            data = self.post('/mpesa/stkpushquery/v1/query', {
                'BusinessShortCode': self.cfg.mpesa_shortcode, 'Password': self._password(stamp),
                'Timestamp': stamp, 'CheckoutRequestID': checkout_request_id,
            })
        except DarajaError as e:
            # "The transaction is being processed" comes back as an error.
            if 'process' in str(e).lower():
                return 'pending', str(e)
            raise
        code = str(data.get('ResultCode', ''))
        if code == '0':
            return 'paid', data.get('ResultDesc', '')
        if code == '':
            return 'pending', data.get('ResponseDescription', '')
        return 'failed', data.get('ResultDesc', '')

    # -- C2B --

    def register_c2b(self, confirmation_url, validation_url):
        return self.post('/mpesa/c2b/v2/registerurl', {
            'ShortCode': self.cfg.mpesa_shortcode, 'ResponseType': 'Completed',
            'ConfirmationURL': confirmation_url, 'ValidationURL': validation_url,
        })

    # -- payouts --

    def payout(self, *, method, destination, amount, account_ref, originator_id, remarks, result_url, timeout_url):
        credential = security_credential(self.cfg.mpesa_certificate, self.cfg.initiator_password)
        sender = self.cfg.settlement_shortcode or self.cfg.mpesa_shortcode
        if method == 'phone':
            return self.post('/mpesa/b2c/v3/paymentrequest', {
                'OriginatorConversationID': originator_id, 'InitiatorName': self.cfg.initiator_name,
                'SecurityCredential': credential, 'CommandID': 'BusinessPayment', 'Amount': int(amount),
                'PartyA': sender, 'PartyB': destination, 'Remarks': remarks[:100],
                'QueueTimeOutURL': timeout_url, 'ResultURL': result_url, 'Occasion': account_ref[:100],
            })
        return self.post('/mpesa/b2b/v1/paymentrequest', {
            'Initiator': self.cfg.initiator_name, 'SecurityCredential': credential,
            'CommandID': 'BusinessBuyGoods' if method == 'till' else 'BusinessPayBill',
            'SenderIdentifierType': '4', 'RecieverIdentifierType': '4', 'Amount': int(amount),
            'PartyA': sender, 'PartyB': destination, 'AccountReference': (account_ref or 'Settlement')[:13],
            'Requester': '', 'Remarks': remarks[:100], 'QueueTimeOutURL': timeout_url, 'ResultURL': result_url,
            'Occassion': originator_id,
        })


def _amount(value):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(value)) if value not in (None, '') else None
    except InvalidOperation:
        return None


def normalize_phone(phone):
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    if digits.startswith('0') and len(digits) == 10:
        digits = '254' + digits[1:]
    elif len(digits) == 9 and digits[0] in '17':
        digits = '254' + digits
    if not (digits.startswith('254') and len(digits) == 12):
        raise DarajaError('Enter a Kenyan phone number, e.g. 0712345678')
    return digits


def parse_stk_callback(body):
    """-> dict(checkout_request_id, result_code, result_desc, amount, receipt, phone, paid_at)."""
    cb = (body or {}).get('Body', {}).get('stkCallback', {})
    items = {i.get('Name'): i.get('Value') for i in cb.get('CallbackMetadata', {}).get('Item', [])}
    paid_at = None
    if items.get('TransactionDate'):
        try:
            paid_at = timezone.make_aware(datetime.strptime(str(items['TransactionDate']), '%Y%m%d%H%M%S'))
        except ValueError:
            pass
    return {
        'checkout_request_id': cb.get('CheckoutRequestID', ''), 'merchant_request_id': cb.get('MerchantRequestID', ''),
        'result_code': str(cb.get('ResultCode', '')), 'result_desc': cb.get('ResultDesc', ''),
        'amount': _amount(items.get('Amount')), 'receipt': items.get('MpesaReceiptNumber') or '',
        'phone': str(items.get('PhoneNumber') or ''), 'paid_at': paid_at,
    }


def parse_c2b(body):
    paid_at = None
    if body.get('TransTime'):
        try:
            paid_at = timezone.make_aware(datetime.strptime(str(body['TransTime']), '%Y%m%d%H%M%S'))
        except ValueError:
            pass
    name = ' '.join(filter(None, [body.get('FirstName'), body.get('MiddleName'), body.get('LastName')]))
    return {'receipt': body.get('TransID', ''), 'amount': _amount(body.get('TransAmount')), 'account': body.get('BillRefNumber', '') or '',
            'phone': str(body.get('MSISDN') or ''), 'name': name, 'paid_at': paid_at,
            'shortcode': str(body.get('BusinessShortCode') or '')}
