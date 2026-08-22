"""
Celery tasks for the notifications app.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('apps.notifications')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification(self, log_id):
    """
    Deliver one NotificationLog row through its channel's provider.
    Retries (30s backoff) on network/provider exceptions; a clean provider
    rejection (bad number, bad credentials) is recorded as failed without
    retrying, since it won't succeed on a retry either.
    """
    from django.conf import settings
    from apps.notifications.models import NotificationLog
    from apps.notifications.providers import SENDERS

    try:
        log = NotificationLog.objects.get(id=log_id)
    except NotificationLog.DoesNotExist:
        logger.error(f"NotificationLog {log_id} not found")
        return

    if log.status == 'sent':
        return  # already delivered (duplicate task delivery)

    sender = SENDERS.get(log.channel)
    if not sender:
        log.status = 'failed'
        log.error = f"Unknown channel '{log.channel}'"
        log.save(update_fields=['status', 'error'])
        return

    log.attempts += 1
    if log.channel == 'sms':
        log.provider = settings.SMS_PROVIDER
    elif log.channel == 'whatsapp':
        log.provider = settings.WHATSAPP_PROVIDER
    else:
        log.provider = 'telegram'

    try:
        ok, detail = sender(log.recipient, log.message)
    except Exception as exc:
        log.status = 'pending'
        log.error = str(exc)
        log.save(update_fields=['status', 'error', 'attempts', 'provider'])
        logger.warning(f"Notification {log_id} raised {exc}; retrying")
        raise self.retry(exc=exc)

    if ok:
        log.status = 'sent'
        log.error = ''
        log.sent_at = timezone.now()
        log.save(update_fields=['status', 'error', 'sent_at', 'attempts', 'provider'])
        logger.info(f"Notification {log_id} sent via {log.channel} to {log.recipient}")
    else:
        log.status = 'failed'
        log.error = detail
        log.save(update_fields=['status', 'error', 'attempts', 'provider'])
        logger.error(f"Notification {log_id} failed via {log.channel}: {detail}")


@shared_task
def send_expiry_reminders():
    """
    Remind customers whose active subscription expires within the next
    NOTIFY_EXPIRY_REMINDER_HOURS (default 24h). Runs hourly via Celery Beat;
    the NotificationLog is used for dedup so each expiry only triggers one
    reminder per customer.
    """
    from django.conf import settings
    from apps.billing.models import Subscription
    from apps.notifications.models import NotificationLog
    from apps.notifications.services import notify_customer

    window_hours = settings.NOTIFY_EXPIRY_REMINDER_HOURS
    now = timezone.now()

    expiring = Subscription.objects.filter(
        status='active',
        expiry_date__gt=now,
        expiry_date__lte=now + timedelta(hours=window_hours),
    ).select_related('customer', 'plan')

    count = 0
    for sub in expiring:
        already_reminded = NotificationLog.objects.filter(
            customer=sub.customer,
            event='subscription_expiring',
            created_at__gte=now - timedelta(hours=window_hours),
        ).exists()
        if already_reminded:
            continue

        notify_customer(sub.customer, 'subscription_expiring', {
            'plan': sub.plan.name,
            'expiry': timezone.localtime(sub.expiry_date).strftime('%d %b %Y %H:%M'),
        })
        count += 1

    logger.info(f"Queued expiry reminders for {count} customer(s)")
    return count
