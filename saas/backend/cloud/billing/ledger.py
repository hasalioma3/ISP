from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum

from cloud.billing.models import LedgerEntry
from cloud.core.models import PlatformSettings
from cloud.pricing.models import money


def balance(tenant):
    return money(LedgerEntry.objects.filter(tenant=tenant).aggregate(s=Sum('amount'))['s'] or 0)


def post(tenant, kind, amount, reference, description='', **links):
    """Add one entry; a second post with the same (kind, reference) is a no-op."""
    amount = money(amount)
    existing = LedgerEntry.objects.filter(kind=kind, reference=reference).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            return LedgerEntry.objects.create(tenant=tenant, kind=kind, amount=amount, reference=reference,
                                              description=description[:255], **links), True
    except IntegrityError:
        return LedgerEntry.objects.get(kind=kind, reference=reference), False


def collection_fee_percent(tenant):
    plan = tenant.effective_plan()
    if plan and plan.collection_fee_percent is not None:
        return plan.collection_fee_percent
    return PlatformSettings.load().collection_fee_percent


def settlement_fee(tenant):
    plan = tenant.effective_plan()
    if plan and plan.settlement_fee_flat is not None:
        return money(plan.settlement_fee_flat)
    return money(PlatformSettings.load().settlement_fee_flat)


def credit_collection(collection):
    """Credit a verified, allocated payment (and take the collection fee)."""
    if not (collection.tenant_id and collection.verified):
        return None
    entry, created = post(collection.tenant, 'collection', collection.amount, collection.receipt,
                          f'{collection.get_source_display()} {collection.receipt} from {collection.phone or "customer"}',
                          collection=collection)
    pct = collection_fee_percent(collection.tenant)
    if created and pct:
        fee = money(collection.amount * Decimal(pct) / 100)
        if fee:
            post(collection.tenant, 'collection_fee', -fee, collection.receipt, f'{pct}% collection fee on {collection.receipt}',
                 collection=collection)
    return entry
