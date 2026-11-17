"""
Customer payments for the ISPs, arriving on the platform shortcode.

STK push: each ISP instance asks Safaricom to call back
  /api/mpesa/stk/<tenant.callback_token>/ -- so the token says which ISP it
  is. We record the payment, confirm it with Safaricom's STK query (the
  callback URL is public, so a forged callback must not create money), credit
  the ISP's ledger, and forward the untouched body to the instance's own
  /api/payments/callback/ so it activates the customer as it always has.

C2B (paybill/till): Safaricom allows one confirmation URL per shortcode,
  shared by every ISP, so we work out whose customer paid (routing below),
  then forward to that instance's C2B confirmation URL.

Routing a C2B payment (first match wins):
  1. account starts with an ISP's prefix ("ACME john" / "ACME-john" / "ACMEjohn")
  2. exactly one ISP has a subscriber with that username
  3. otherwise it's left unallocated for a platform admin to assign.
The ISP app tells its customers to pay with their username as the account
number, so (2) covers the normal case without changing that app.
"""
import logging
import re

import requests
from django.db import transaction
from django.utils import timezone

from cloud.billing import daraja
from cloud.billing.ledger import credit_collection
from cloud.billing.models import Collection
from cloud.core.models import PlatformSettings
from cloud.tenants.models import Tenant

logger = logging.getLogger('cloud.billing')

FORWARD_TIMEOUT = 20
# Calls to an instance go straight to its backend on the private SaaS
# network, not through its nginx -- so say what nginx would: the ISP app
# redirects anything it thinks is plain HTTP to HTTPS (SECURE_SSL_REDIRECT).
TENANT_HEADERS = {'X-Forwarded-Proto': 'https'}


# --- STK ----------------------------------------------------------------

def handle_stk_callback(tenant, body):
    """Record + queue verification/forwarding. Always returns quickly."""
    info = daraja.parse_stk_callback(body)
    collection = None
    if info['result_code'] == '0' and info['receipt']:
        collection, created = Collection.objects.get_or_create(receipt=info['receipt'], defaults={
            'tenant': tenant, 'source': 'stk', 'amount': info['amount'] or 0, 'phone': info['phone'],
            'paid_at': info['paid_at'] or timezone.now(), 'checkout_request_id': info['checkout_request_id'],
            'routed_by': 'callback', 'raw': body,
        })
        if not created:
            logger.info('Duplicate STK callback %s', info['receipt'])
            return collection
    from cloud.billing.tasks import forward_stk, verify_collection
    if collection:
        # A successful payment reaches the instance (which switches the
        # customer on) only once Safaricom confirms it -- verify() forwards
        # it then. The callback URL is public; a forged one must not get a
        # customer free service.
        transaction.on_commit(lambda: verify_collection.delay(collection.pk))
    else:
        # Failed/cancelled payments go straight through: the instance has a
        # pending payment request waiting to hear how it ended.
        transaction.on_commit(lambda: forward_stk.delay(tenant.pk, body, None))
    return collection


def verify(collection):
    """Confirm an STK payment with Safaricom; when paid, credit it and pass it
    on to the instance. -> 'paid' | 'failed' | 'pending' (try again later)."""
    cfg = PlatformSettings.load()
    if not collection.verified:
        if not cfg.verify_stk_callbacks or collection.source != 'stk':
            state, desc = 'paid', 'verification off'
        else:
            try:
                state, desc = daraja.Daraja(cfg).stk_query(collection.checkout_request_id)
            except daraja.DarajaError as e:
                state, desc = 'pending', str(e)
        collection.verify_attempts += 1
        collection.verify_error = '' if state == 'paid' else f'{state}: {desc}'[:255]
        collection.verified = state == 'paid'
        collection.save(update_fields=['verified', 'verify_error', 'verify_attempts'])
        if state != 'paid':
            if state == 'failed':
                logger.warning('STK callback %s for %s did not verify: %s', collection.receipt, collection.tenant_id, desc)
            return state
    credit_collection(collection)
    if collection.tenant_id and not collection.forwarded:
        from cloud.billing.tasks import forward_stk
        transaction.on_commit(lambda: forward_stk.delay(collection.tenant_id, collection.raw, collection.pk))
    return 'paid'


def forward_stk(tenant, body, collection=None):
    url = f'{tenant.backend_url}/api/payments/callback/'
    _forward(url, body, collection)


# --- C2B ----------------------------------------------------------------

SEPARATOR_CHARS = ' -_.#:/'
SEPARATORS = re.compile(r'^[\s\-_.#:/]+')


def route(account, phone=''):
    """-> (tenant | None, account as that ISP knows it, how it was routed)."""
    account = (account or '').strip()
    live = Tenant.objects.filter(status__in=['trial', 'active', 'past_due', 'suspended'])
    upper = account.upper()
    for t in sorted(live, key=lambda t: -len(t.account_prefix)):
        prefix = t.account_prefix
        if not prefix or not upper.startswith(prefix):
            continue
        tail = account[len(prefix):]
        rest = SEPARATORS.sub('', tail)
        # "ACME john" / "ACME-john" are unambiguous; "ACMEjohn" only counts
        # when that ISP really has a "john" -- a username like "acmestore"
        # at another ISP must not be captured by the prefix.
        if rest and (tail[:1] in SEPARATOR_CHARS or _exists(t, rest)):
            return t, rest, 'prefix'
    if account:
        matches = [t for t in live if _exists(t, account)]
        if len(matches) == 1:
            return matches[0], account, 'username'
    return None, account, ''


def _exists(tenant, account):
    from django.conf import settings
    from cloud.tenants import tenant_db
    if settings.SAAS_ORCHESTRATOR != 'docker':
        return account.lower() in [a.lower() for a in tenant.metrics.get('fake_accounts', [])]
    try:
        return tenant_db.account_exists(tenant, account)
    except tenant_db.TenantDBError:
        return False


def handle_c2b_confirmation(body):
    info = daraja.parse_c2b(body)
    if not info['receipt']:
        return None
    tenant, account, how = route(info['account'], info['phone'])
    collection, created = Collection.objects.get_or_create(receipt=info['receipt'], defaults={
        'tenant': tenant, 'source': 'c2b', 'amount': info['amount'] or 0, 'phone': info['phone'],
        'account': info['account'], 'payer_name': info['name'], 'paid_at': info['paid_at'] or timezone.now(),
        # Safaricom is the only caller of the secret C2B URL: trusted as-is.
        'verified': True, 'routed_by': how, 'raw': body,
    })
    if not created:
        return collection
    if tenant:
        credit_collection(collection)
        from cloud.billing.tasks import forward_c2b
        transaction.on_commit(lambda: forward_c2b.delay(collection.pk, account))
    else:
        logger.warning('C2B %s (account %r) matched no ISP; left unallocated', info['receipt'], info['account'])
    return collection


def allocate(collection, tenant, account=None, actor=None):
    """Assign an unallocated payment to an ISP (platform admin)."""
    from cloud.tenants.services import log
    if collection.tenant_id:
        raise ValueError('This payment is already allocated')
    collection.tenant, collection.routed_by = tenant, 'manual'
    collection.save(update_fields=['tenant', 'routed_by'])
    credit_collection(collection)
    log(tenant, 'payment', f'Payment {collection.receipt} (KES {collection.amount}) allocated by hand', actor=actor)
    from cloud.billing.tasks import forward_c2b as forward_task
    transaction.on_commit(lambda: forward_task.delay(collection.pk, account or collection.account))
    return collection


def forward_c2b(collection, account):
    tenant = collection.tenant
    body = dict(collection.raw)
    body['BillRefNumber'] = account
    url = f'{tenant.backend_url}/api/payments/c2b/{tenant.c2b_secret}/confirmation/'
    _forward(url, body, collection)


def _forward(url, body, collection):
    try:
        resp = requests.post(url, json=body, timeout=FORWARD_TIMEOUT, headers=TENANT_HEADERS, allow_redirects=False)
        ok = resp.status_code < 400
        error = '' if ok else f'HTTP {resp.status_code}: {resp.text[:300]}'
    except requests.RequestException as e:
        ok, error = False, f'{e.__class__.__name__}: {e}'[:500]
    if collection:
        collection.forwarded = ok
        collection.forward_error = error
        collection.save(update_fields=['forwarded', 'forward_error'])
    if not ok:
        # Raise so the Celery task retries; the money is already recorded.
        raise ForwardError(error)


class ForwardError(Exception):
    pass
