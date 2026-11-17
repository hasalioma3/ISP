"""
Earning, redeeming, adjusting and expiring loyalty points. Every change is a
LoyaltyTransaction row written under a row lock on the customer, so two
concurrent redemptions can't both spend the same points.
"""
import logging
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from apps.loyalty.models import LoyaltySettings, LoyaltyTransaction

logger = logging.getLogger('apps.loyalty')

EARNING_METHODS = ('mpesa', 'cash', 'bank', 'other')


class LoyaltyError(Exception):
    pass


def balance(customer):
    return LoyaltyTransaction.objects.filter(customer=customer).aggregate(t=Sum('points'))['t'] or 0


def value_of(points, cfg=None):
    cfg = cfg or LoyaltySettings.load()
    return (Decimal(points) * cfg.point_value_kes).quantize(Decimal('0.01'))


def _lock(customer):
    from apps.customers.models import Customer
    return Customer.objects.select_for_update().get(pk=customer.pk)


def _post(customer, kind, points, **extra):
    current = balance(customer)
    return LoyaltyTransaction.objects.create(customer=customer, kind=kind, points=points,
                                             balance_after=current + points, **extra)


def points_for(amount, cfg):
    if not cfg.kes_per_point or cfg.kes_per_point <= 0:
        return 0
    return int((Decimal(amount) / cfg.kes_per_point).to_integral_value(rounding=ROUND_DOWN))


def award_for_transaction(txn):
    """Earn points on a completed payment (idempotent per transaction).
    -> the new LoyaltyTransaction, or None if nothing was earned."""
    cfg = LoyaltySettings.load()
    customer = txn.customer
    if not cfg.enabled or txn.status != 'completed' or txn.payment_method not in EARNING_METHODS:
        return None
    if customer.is_staff or customer.service_type not in cfg.service_type_list():
        return None
    if txn.amount is None or txn.amount <= 0:
        return None
    points = points_for(txn.amount, cfg)
    with db_transaction.atomic():
        _lock(customer)
        if LoyaltyTransaction.objects.filter(transaction=txn).exists():
            return None
        first = not LoyaltyTransaction.objects.filter(customer=customer, kind__in=['earn', 'bonus']).exists()
        entry = None
        if points > 0:
            entry = _post(customer, 'earn', points, transaction=txn,
                          description=f'Payment {txn.mpesa_receipt_number or txn.transaction_id} (KES {txn.amount})')
        if first and cfg.welcome_bonus:
            bonus = _post(customer, 'bonus', cfg.welcome_bonus, description='Welcome bonus')
            entry = entry or bonus
            points += cfg.welcome_bonus
    if entry and cfg.notify_earn:
        from apps.loyalty.tasks import notify
        db_transaction.on_commit(lambda: notify.delay(customer.pk, 'loyalty_earned', points, str(txn.amount)))
    return entry


def redeem(customer, points, actor=None):
    """Turn points into KES on the customer's account balance."""
    cfg = LoyaltySettings.load()
    if not cfg.enabled:
        raise LoyaltyError('The loyalty programme is turned off.')
    try:
        points = int(points)
    except (TypeError, ValueError):
        raise LoyaltyError('Enter a whole number of points.')
    if points <= 0:
        raise LoyaltyError('Enter how many points to redeem.')
    if points < cfg.min_redeem_points:
        raise LoyaltyError(f'You can redeem from {cfg.min_redeem_points} points.')
    with db_transaction.atomic():
        locked = _lock(customer)
        available = balance(locked)
        if points > available:
            raise LoyaltyError(f'Only {available} points are available.')
        kes = value_of(points, cfg)
        entry = _post(locked, 'redeem', -points, kes_value=kes, created_by=actor,
                      description=f'Redeemed for KES {kes} account credit' + (f' by {actor.username}' if actor and actor.pk != locked.pk else ''))
        locked.account_balance += kes
        locked.save(update_fields=['account_balance'])
    if cfg.notify_redeem:
        from apps.loyalty.tasks import notify
        db_transaction.on_commit(lambda: notify.delay(customer.pk, 'loyalty_redeemed', points, str(kes)))
    return entry, locked.account_balance


def adjust(customer, points, reason, actor):
    try:
        points = int(points)
    except (TypeError, ValueError):
        raise LoyaltyError('Enter a whole number of points.')
    if not points:
        raise LoyaltyError('Enter a non-zero number of points.')
    if not (reason or '').strip():
        raise LoyaltyError('Give a reason for the adjustment.')
    with db_transaction.atomic():
        locked = _lock(customer)
        if balance(locked) + points < 0:
            raise LoyaltyError('That would take the balance below zero.')
        return _post(locked, 'adjust', points, description=reason.strip()[:255], created_by=actor)


def expire_points(today=None):
    """
    Expire points earned more than expiry_months ago that were never used.
    FIFO: everything spent so far (redeemed, expired, negative adjustments)
    counts against the oldest points first, so only the unspent remainder of
    the old earnings goes. -> total points expired.
    """
    cfg = LoyaltySettings.load()
    if not cfg.enabled or not cfg.expiry_months:
        return 0
    cutoff = timezone.now() - timedelta(days=30 * cfg.expiry_months)
    total = 0
    customer_ids = LoyaltyTransaction.objects.filter(points__gt=0, created_at__lt=cutoff) \
        .values_list('customer_id', flat=True).distinct()
    from apps.customers.models import Customer
    for customer in Customer.objects.filter(pk__in=list(customer_ids)):
        with db_transaction.atomic():
            _lock(customer)
            entries = LoyaltyTransaction.objects.filter(customer=customer)
            old_earned = entries.filter(points__gt=0, created_at__lt=cutoff).aggregate(t=Sum('points'))['t'] or 0
            spent = -(entries.filter(points__lt=0).aggregate(t=Sum('points'))['t'] or 0)
            due = min(old_earned - spent, balance(customer))
            if due > 0:
                _post(customer, 'expire', -due, description=f'Points earned before {timezone.localtime(cutoff):%d %b %Y} expired')
                total += due
    return total


def summary(customer, cfg=None):
    cfg = cfg or LoyaltySettings.load()
    pts = balance(customer)
    return {
        'enabled': cfg.enabled and customer.service_type in cfg.service_type_list(),
        'points': pts, 'value_kes': str(value_of(pts, cfg)),
        'kes_per_point': str(cfg.kes_per_point), 'point_value_kes': str(cfg.point_value_kes),
        'min_redeem_points': cfg.min_redeem_points, 'can_self_redeem': cfg.allow_self_redeem,
        'expiry_months': cfg.expiry_months,
    }
