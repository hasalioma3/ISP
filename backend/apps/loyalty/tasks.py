from celery import shared_task


@shared_task
def notify(customer_id, template_key, points, amount):
    from apps.customers.models import Customer
    from apps.loyalty.models import LoyaltySettings
    from apps.loyalty.services import balance, value_of
    from apps.notifications.tasks import send_with_fallback
    from apps.notifications.templates import render

    customer = Customer.objects.filter(pk=customer_id).first()
    if not customer:
        return
    cfg = LoyaltySettings.load()
    pts = balance(customer)
    message = render(template_key, {
        'points': points, 'amount': amount, 'balance': pts, 'value': value_of(pts, cfg),
        'account_balance': customer.account_balance,
    }, customer)
    send_with_fallback(customer, message, template_key, cfg.channel_list(), sms_fallback=True)


@shared_task
def expire_points():
    from apps.loyalty.services import expire_points as run
    return run()
