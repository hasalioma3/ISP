"""
Paying ISPs their money: B2B to a paybill/till, or B2C to a phone.

    available = ledger balance - reserve
    create    -> pending_approval (or queued when approval is off)
    submit    -> amount + fee leave the balance (held), Daraja request sent
    result    -> succeeded, or failed and the hold is reversed

Open invoices are paid from the balance first, so the platform is always
paid before a payout is computed.
"""
import logging
import secrets

from django.db import transaction
from django.utils import timezone

from cloud.billing import daraja
from cloud.billing.ledger import balance, post, settlement_fee
from cloud.billing.models import Settlement
from cloud.core.models import PlatformSettings
from cloud.pricing.models import money

logger = logging.getLogger('cloud.billing')


class SettlementError(Exception):
    pass


def available(tenant):
    cfg = PlatformSettings.load()
    held = sum((s.amount + s.fee for s in tenant.settlements.filter(status__in=['pending_approval', 'queued'])), 0)
    unpaid = sum(tenant.invoices.filter(status='open').values_list('amount', flat=True), 0)
    return money(max(0, balance(tenant) - cfg.reserve_amount - held - unpaid))


def create(tenant, amount=None, actor=None, auto=False):
    cfg = PlatformSettings.load()
    if tenant.settlement_hold:
        raise SettlementError('Payouts to this ISP are on hold')
    if not (tenant.settlement_method and tenant.settlement_account):
        raise SettlementError('This ISP has not set where to send its money')
    from cloud.billing.invoicing import retry_open_invoices
    retry_open_invoices()
    fee = settlement_fee(tenant)
    room = available(tenant) - fee
    amount = money(amount) if amount is not None else room
    if amount <= 0 or amount > room:
        raise SettlementError(f'Only KES {max(room, 0):,.2f} is available to pay out')
    if auto and amount < cfg.settlement_min_amount:
        raise SettlementError(f'Below the minimum payout of KES {cfg.settlement_min_amount:,.0f}')
    s = Settlement.objects.create(
        tenant=tenant, amount=amount, fee=fee, method=tenant.settlement_method, destination=tenant.settlement_account,
        account_ref=tenant.settlement_account_ref, requested_by=actor if getattr(actor, 'pk', None) else None,
        status='pending_approval' if cfg.settlement_requires_approval else 'queued',
        originator_id=f'isp-{tenant.slug}-{secrets.token_hex(8)}')
    from cloud.tenants.services import log
    log(tenant, 'settlement', f'Payout of KES {amount:,.2f} to {s.destination} created', actor=actor)
    if s.status == 'queued':
        from cloud.billing.tasks import submit_settlement
        transaction.on_commit(lambda: submit_settlement.delay(s.pk))
    return s


def approve(settlement, actor):
    if settlement.status != 'pending_approval':
        raise SettlementError('Only payouts awaiting approval can be approved')
    if settlement.requested_by_id and settlement.requested_by_id == getattr(actor, 'pk', None) and not actor.is_superuser:
        raise SettlementError('Someone other than the requester must approve a payout')
    settlement.status, settlement.approved_by = 'queued', actor
    settlement.save(update_fields=['status', 'approved_by'])
    from cloud.billing.tasks import submit_settlement
    transaction.on_commit(lambda: submit_settlement.delay(settlement.pk))
    return settlement


def cancel(settlement, actor=None):
    if settlement.status not in ('pending_approval', 'queued'):
        raise SettlementError('Only payouts not yet sent can be cancelled')
    settlement.status = 'cancelled'
    settlement.save(update_fields=['status'])
    return settlement


def submit(settlement):
    cfg = PlatformSettings.load()
    with transaction.atomic():
        s = Settlement.objects.select_for_update().get(pk=settlement.pk)
        if s.status != 'queued':
            return s
        if balance(s.tenant) - cfg.reserve_amount < s.amount + s.fee:
            s.status, s.result_desc = 'failed', 'Not enough balance when it was sent'
            s.save(update_fields=['status', 'result_desc'])
            return s
        post(s.tenant, 'settlement', -s.amount, s.originator_id, f'Payout to {s.destination}', settlement=s)
        if s.fee:
            post(s.tenant, 'settlement_fee', -s.fee, s.originator_id, 'Payout fee', settlement=s)
        s.status, s.submitted_at = 'processing', timezone.now()
        s.save(update_fields=['status', 'submitted_at'])
    try:
        resp = daraja.Daraja(cfg).payout(
            method=s.method, destination=s.destination, amount=s.amount, account_ref=s.account_ref,
            originator_id=s.originator_id, remarks=f'{cfg.brand_name} payout to {s.tenant.name}',
            result_url=cfg.public_url('/api/mpesa/payout/result/'), timeout_url=cfg.public_url('/api/mpesa/payout/timeout/'))
    except daraja.DarajaError as e:
        _fail(s, str(e))
        return s
    s.conversation_id = resp.get('ConversationID', '')
    s.result_desc = resp.get('ResponseDescription', '')
    s.save(update_fields=['conversation_id', 'result_desc'])
    return s


def _fail(s, reason, raw=None):
    s.status, s.result_desc, s.completed_at = 'failed', reason[:2000], timezone.now()
    if raw is not None:
        s.raw_result = raw
    s.save(update_fields=['status', 'result_desc', 'completed_at', 'raw_result'])
    # Put the held money back.
    post(s.tenant, 'settlement_reversal', s.amount + s.fee, s.originator_id, f'Payout failed: {reason[:150]}', settlement=s)
    from cloud.tenants.services import log
    log(s.tenant, 'settlement', f'Payout of KES {s.amount:,.2f} failed: {reason[:300]}')


def handle_result(body):
    result = (body or {}).get('Result', {})
    oid, cid = result.get('OriginatorConversationID', ''), result.get('ConversationID', '')
    s = (Settlement.objects.filter(originator_id=oid).first() if oid else None) or \
        (Settlement.objects.filter(conversation_id=cid).first() if cid else None)
    if not s:
        logger.warning('Payout result for unknown conversation %s / %s', oid, cid)
        return None
    if s.status != 'processing':
        return s
    s.result_code = str(result.get('ResultCode', ''))
    if s.result_code == '0':
        s.status, s.completed_at = 'succeeded', timezone.now()
        s.mpesa_receipt = result.get('TransactionID', '')
        s.result_desc = result.get('ResultDesc', '')
        s.raw_result = body
        s.save()
        from cloud.tenants.services import log, notify_owner
        log(s.tenant, 'settlement', f'Paid out KES {s.amount:,.2f} to {s.destination} ({s.mpesa_receipt})')
        notify_owner(s.tenant, f'payout of KES {s.amount:,.0f} sent', (
            f'KES {s.amount:,.2f} has been sent to {s.destination}'
            + (f' (account {s.account_ref})' if s.account_ref else '') + f'. M-Pesa ref {s.mpesa_receipt}.'))
    else:
        s.result_code = s.result_code
        _fail(s, result.get('ResultDesc') or 'M-Pesa rejected the payout', raw=body)
    return s


def handle_timeout(body):
    oid = (body or {}).get('OriginatorConversationID') or (body or {}).get('Result', {}).get('OriginatorConversationID')
    s = Settlement.objects.filter(originator_id=oid).first() if oid else None
    if s and s.status == 'processing':
        # Not necessarily failed -- M-Pesa may still complete it. Flag it for
        # a person to check rather than reversing (which could pay twice).
        s.result_desc = 'M-Pesa timed out; check the statement before retrying'
        s.save(update_fields=['result_desc'])
    return s


def run_scheduled(now=None, force=False):
    cfg = PlatformSettings.load()
    now = timezone.localtime(now or timezone.now())
    if not force:
        if cfg.settlement_schedule == 'manual' or now.hour != cfg.settlement_hour:
            return 0
        if cfg.settlement_schedule == 'weekly' and now.weekday() != cfg.settlement_weekday:
            return 0
    from cloud.tenants.models import Tenant
    n = 0
    for tenant in Tenant.objects.exclude(settlement_method='').exclude(settlement_account='').filter(settlement_hold=False):
        if tenant.settlements.filter(status__in=['pending_approval', 'queued', 'processing'],
                                     created_at__date=now.date()).exists():
            continue
        try:
            create(tenant, auto=True)
            n += 1
        except SettlementError:
            continue
    return n
