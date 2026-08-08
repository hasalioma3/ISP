"""
Central subscription-assignment and wallet logic.

apply_subscription() enforces "at most one active subscription per
service_type" -- every activation path (STK push callback, C2B
confirmation, admin manual top-up/assign, plan switch) must go through it
rather than creating a Subscription row directly. Before this existed, each
call site duplicated its own reuse-or-create logic (inconsistently), which
is how a customer could end up with two simultaneously "Active" PPPoE
subscriptions.

purchase_plan() is the wallet-model entry point for a fresh payment (STK/
C2B): account_balance is a real running ledger, not just an edge-case
credit -- every payment lands in it first, and the plan's price is then
deducted from it. This makes any leftover (a payment that doesn't exactly
cover the plan, or exceeds it) visible and spendable rather than silently
absorbed or lost, and it composes with apply_subscription's own proration
credit on a plan switch for free (both just move account_balance).
"""
from decimal import Decimal

from django.utils import timezone

from apps.billing.models import Subscription


def get_daily_rate(plan):
    """Plan price spread evenly over its real duration, for prorating a partially-used plan."""
    duration_days = Decimal(plan.get_duration_timedelta().total_seconds()) / Decimal(86400)
    if duration_days <= 0:
        return Decimal('0')
    return plan.price / duration_days


def get_active_subscription(customer, service_type):
    """The customer's current non-expired active subscription for this service_type, if any."""
    return Subscription.objects.filter(
        customer=customer,
        plan__service_type=service_type,
        status='active',
        expiry_date__gt=timezone.now(),
    ).order_by('-created_at').first()


def preview_plan_switch(customer, plan):
    """
    What apply_subscription would do for this customer/plan, without
    actually changing anything -- lets a caller check affordability (e.g.
    paying for a switch out of account_balance) before committing to a
    switch that triggers real network activation and can't be cleanly
    undone once it fires.

    Returns (current_active_subscription_or_None, prorated_credit). The
    credit is nonzero only when there's an active subscription for a
    DIFFERENT plan -- the unused value remaining on it, computed at its
    daily rate.
    """
    active = get_active_subscription(customer, plan.service_type)
    if not active or active.plan_id == plan.id:
        return active, Decimal('0')

    remaining = active.expiry_date - timezone.now()
    remaining_days = Decimal(remaining.total_seconds()) / Decimal(86400)
    credit = (get_daily_rate(active.plan) * remaining_days).quantize(Decimal('0.01'))
    return active, credit


def apply_subscription(customer, plan):
    """
    Assign `plan` to `customer`, enforcing at most one active subscription
    per service_type:
    - No existing active subscription for this service_type -> create one.
    - Existing active subscription for the SAME plan -> renew (extend
      expiry_date by the plan's duration).
    - Existing active subscription for a DIFFERENT plan (upgrade/downgrade)
      -> the unused value remaining on the old plan is prorated and
      credited to the customer's account_balance (never just lost), then
      the same subscription row is switched to the new plan for its full
      duration starting now.

    Returns (subscription, credited_amount) -- credited_amount is the
    prorated balance credit from a plan switch, or Decimal('0') otherwise.
    Does NOT deduct anything from account_balance for the new plan itself
    -- callers that pay for the new plan from a fresh payment (STK/C2B/cash
    top-up) don't need to, and callers paying from existing balance (plan
    switch funded by account_balance) handle that deduction themselves,
    after checking affordability via preview_plan_switch first.
    """
    duration = plan.get_duration_timedelta()
    active, credited = preview_plan_switch(customer, plan)

    if active and active.plan_id == plan.id:
        active.expiry_date += duration
        active.status = 'active'
        active.save()
        return active, Decimal('0')

    if credited:
        customer.account_balance += credited
        customer.save(update_fields=['account_balance'])

    if active:
        active.plan = plan
        active.start_date = timezone.now()
        active.expiry_date = timezone.now() + duration
        active.status = 'active'
        active.save()
        return active, credited

    subscription = Subscription.objects.create(
        customer=customer,
        plan=plan,
        expiry_date=timezone.now() + duration,
        status='active',
    )
    return subscription, credited


def purchase_plan(customer, plan, payment_amount):
    """
    Wallet-model purchase for a fresh payment: credit payment_amount to
    account_balance, then, if the balance now covers plan.price, deduct it
    and apply the plan via apply_subscription (renew/switch/create).

    If the balance doesn't cover plan.price (a partial C2B payment, or one
    smaller than any plan), the payment is still credited and kept as
    balance rather than lost -- no plan is applied yet; the customer (or an
    admin, via switch_plan) can complete the purchase once there's enough.

    Returns (subscription_or_None, switch_credited, applied). `applied` is
    False when the plan wasn't purchased (insufficient balance) --
    switch_credited is always Decimal('0') in that case, since
    apply_subscription never ran.
    """
    customer.account_balance += payment_amount
    customer.save(update_fields=['account_balance'])

    if customer.account_balance < plan.price:
        return None, Decimal('0'), False

    subscription, switch_credited = apply_subscription(customer, plan)
    customer.account_balance -= plan.price
    customer.save(update_fields=['account_balance'])
    return subscription, switch_credited, True


class InsufficientBalance(Exception):
    """Raised by purchase_plan_from_balance -- carries the numbers so callers can build a clear error message."""
    def __init__(self, available, required):
        self.available = available
        self.required = required
        super().__init__(f"KES {available} available, KES {required} required")


def purchase_plan_from_balance(customer, plan):
    """
    Pay for `plan` entirely out of the customer's EXISTING account_balance
    (no fresh payment involved) -- shared by the admin 'switch plan' action
    and the customer self-service purchase/renew/upgrade flow. Works
    equally for a first-time purchase (no active subscription yet), a
    same-plan renewal, or a switch to a different plan.

    Affordability -- including any proration credit from switching away
    from a different active plan -- is checked BEFORE apply_subscription
    runs: its save() synchronously triggers real network activation via a
    signal, which can't be undone by a later rollback, so we can't "try it
    and roll back" on insufficient funds.

    Raises InsufficientBalance if the balance (plus any proration credit)
    doesn't cover plan.price -- nothing is changed in that case. Returns
    (subscription, credited_amount) on success.
    """
    _, projected_credit = preview_plan_switch(customer, plan)
    projected_balance = customer.account_balance + projected_credit
    if projected_balance < plan.price:
        raise InsufficientBalance(projected_balance, plan.price)

    subscription, credited = apply_subscription(customer, plan)
    customer.account_balance -= plan.price
    customer.save(update_fields=['account_balance'])
    return subscription, credited
