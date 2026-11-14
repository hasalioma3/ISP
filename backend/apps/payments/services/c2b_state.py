"""
One answer to "where did this till (C2B) payment's money go?", shared by the
Payments list (status / Used for / whether Assign is offered) and the
assign endpoint, so the page never offers Assign on a payment the endpoint
will refuse.

The money's real destination is the Transaction carrying the payment (the
one it's linked to, else the one with the same M-Pesa code -- e.g. created
by the STK callback of a portal payment). A plan on that Transaction, or on
the payment itself, means it paid for a plan; a Transaction without one
means it sits in that customer's balance.
"""


def resolve(payment, twin=None):
    """
    Returns (state, transaction_or_None, subscription_or_None) where state is
    'utilized' (paid for a plan), 'assigned' (in a subscriber's balance),
    'review' (hotspot payer waiting for an admin) or 'open' (nobody yet).
    Pass `twin` (the Transaction with the same code) when already fetched;
    otherwise it's looked up.
    """
    from apps.billing.models import Transaction

    txn = payment.linked_transaction if payment.linked_transaction_id else None
    if txn is None:
        txn = twin if twin is not None else Transaction.objects.filter(
            transaction_id=payment.transaction_id
        ).select_related('subscription__plan').first()
    subscription = None
    if txn is not None and txn.subscription_id:
        subscription = txn.subscription
    elif payment.subscription_id:
        subscription = payment.subscription
    if payment.status == 'activated' or subscription is not None:
        return 'utilized', txn, subscription
    if payment.status == 'review':
        return 'review', txn, None
    if payment.status == 'matched_no_plan' or txn is not None:
        return 'assigned', txn, None
    return 'open', None, None


def used_for(payment, state, subscription):
    """Text for the Payments page's "Used for" column (None -> offer Assign)."""
    if state == 'utilized':
        return subscription.plan.name if subscription is not None and subscription.plan_id else 'A plan'
    if state == 'assigned':
        return 'Account balance'
    if payment.status == 'error':
        return 'Activation failed'
    return None
