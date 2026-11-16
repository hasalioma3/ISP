"""
Payment-reminder text for the Subscribers page's bulk "Send reminder".
Kept out of the view so the preview the admin sees and the message the
Celery task sends are built by exactly the same code.
"""
from django.conf import settings
from django.utils import timezone


def _local_phone(number):
    digits = ''.join(ch for ch in (number or '') if ch.isdigit())
    if len(digits) == 12 and digits.startswith('254'):
        digits = '0' + digits[3:]
    return digits


def build_payment_reminder(customer):
    """
    "Hi Grace, your Hasanet Home 10 Mbps plan expires on 14 Dec 2026.
    Renew: pay KES 2,500 via M-Pesa Buy Goods Till 499xxx from 0722618418..."
    Uses the current (or most recent) subscription; returns None when the
    customer has never had a plan, since there's nothing to quote.
    """
    from apps.billing.models import Subscription

    sub = (
        Subscription.objects.filter(customer=customer, status='active', expiry_date__gt=timezone.now())
        .select_related('plan').order_by('-created_at').first()
        or Subscription.objects.filter(customer=customer).select_related('plan').order_by('-created_at').first()
    )
    if not sub:
        return None

    expiry = timezone.localtime(sub.expiry_date)
    when = (
        f"expires on {expiry:%d %b %Y at %H:%M}" if sub.expiry_date > timezone.now()
        else f"expired on {expiry:%d %b %Y}"
    )
    price = f"KES {sub.plan.price:,.0f}"

    if settings.MPESA_SHORTCODE_TYPE == 'till':
        till = settings.MPESA_TILL_NUMBER or settings.MPESA_SHORTCODE
        phone = _local_phone(customer.phone_number)
        how = f"pay {price} via M-Pesa Buy Goods, Till {till}" + (f", from {phone}" if phone else '')
    else:
        how = f"pay {price} via M-Pesa Paybill {settings.MPESA_SHORTCODE}, account {customer.username}"

    from apps.notifications.templates import render
    return render('payment_reminder', {
        'plan': sub.plan.name, 'price': price, 'expiry_text': when, 'how_to_pay': how,
    }, customer)



def how_to_pay(customer, price_text):
    """The "pay KES X via Buy Goods/Paybill ..." clause used in reminders."""
    if settings.MPESA_SHORTCODE_TYPE == 'till':
        till = settings.MPESA_TILL_NUMBER or settings.MPESA_SHORTCODE
        phone = _local_phone(customer.phone_number)
        return f"pay {price_text} via M-Pesa Buy Goods, Till {till}" + (f", from {phone}" if phone else '')
    return f"pay {price_text} via M-Pesa Paybill {settings.MPESA_SHORTCODE}, account {customer.username}"
