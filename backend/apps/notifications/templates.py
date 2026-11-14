"""
Message wording: built-in defaults plus admin overrides (MessageTemplate).

render(key, context) returns the admin's version when one is saved, else the
default. Placeholders are {name}-style; an unknown or misspelt placeholder is
left in the text as-is rather than failing the send, and a template that
can't be formatted at all (e.g. a stray "{") falls back to the default.
"""
import logging
import string

logger = logging.getLogger('notifications')

COMMON = {
    'first_name': "Customer's first name (or username)",
    'name': "Customer's full name",
    'username': 'Account / login name',
    'company': 'Your company name',
    'support_phone': 'Support phone from Branding settings',
}

# key -> (label, default body, extra placeholders)
DEFAULTS = {
    'payment_confirmation': (
        'Payment received (plan activated)',
        'Payment of KES {amount} received. Your {plan} plan is now active until {expiry}.',
        {'amount': 'Amount paid', 'plan': 'Plan name', 'expiry': 'Expiry date and time'},
    ),
    'balance_credit': (
        'Payment credited to balance',
        'Payment of KES {amount} received and credited to your account balance (KES {balance}). '
        'Contact us to activate a plan.',
        {'amount': 'Amount paid', 'balance': 'New account balance'},
    ),
    'subscription_extended': (
        'Plan extended by staff',
        'Your {plan} plan has been {action} and is active until {expiry}.',
        {'plan': 'Plan name', 'action': '"extended" or "reactivated"', 'expiry': 'New expiry'},
    ),
    'cash_added': (
        'Cash added to account',
        'KES {amount} has been added to your account. Your balance is now KES {balance}.',
        {'amount': 'Amount added', 'balance': 'New balance'},
    ),
    'payment_reminder': (
        'Payment reminder',
        'Hi {first_name}, your {company} {plan} plan {expiry_text}. To renew, {how_to_pay}, '
        'or log in to your account to pay.',
        {'plan': 'Plan name', 'price': 'Plan price', 'expiry_text': '"expires on ..." / "expired on ..."',
         'how_to_pay': 'Buy Goods / Paybill instructions'},
    ),
    'voucher_send': (
        'Voucher code',
        'Your hotspot voucher code: {code}, valid for {plan}. Use it at the login page.',
        {'code': 'Voucher code', 'plan': 'Plan name'},
    ),
}


class _Keep(dict):
    """format_map helper: unknown placeholders stay as literal {name}."""
    def __missing__(self, key):
        return '{' + key + '}'


def placeholders_for(key):
    return {**COMMON, **(DEFAULTS[key][2] if key in DEFAULTS else {})}


def customer_context(customer):
    from apps.sitesettings.models import SiteSettings
    site = SiteSettings.load()
    ctx = {'company': site.company_name, 'support_phone': site.support_phone}
    if customer is not None:
        ctx.update({
            'first_name': customer.first_name or customer.username,
            'name': customer.get_full_name() or customer.username,
            'username': customer.username,
        })
    return ctx


def fill(body, context):
    """Format `body` with `context`, keeping unknown placeholders. Raises on malformed text."""
    # Validate the template's own syntax first ("{" without "}" etc.).
    list(string.Formatter().parse(body))
    return body.format_map(_Keep({k: ('' if v is None else v) for k, v in context.items()}))


def render(key, context, customer=None):
    """The message for `key`, using the admin's template when saved."""
    from apps.notifications.models import MessageTemplate

    ctx = {**customer_context(customer), **context}
    default = DEFAULTS[key][1]
    custom = MessageTemplate.objects.filter(kind='system', key=key).values_list('body', flat=True).first()
    if custom:
        try:
            return fill(custom, ctx)
        except (ValueError, IndexError, KeyError) as e:
            logger.error("Template %r is malformed (%s); sending the default wording", key, e)
    return fill(default, ctx)
