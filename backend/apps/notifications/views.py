import logging

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.customers.models import Customer
from apps.notifications.providers import SENDERS, normalize_phone, send_telegram

logger = logging.getLogger('apps.notifications')


@api_view(['POST'])
@permission_classes([AllowAny])
def telegram_webhook(request):
    """
    Telegram bot webhook. Customers link their account by sending the bot:

        /start <username or phone number>

    We match the customer, store their chat ID, and confirm in the chat.
    Register the webhook once with:

        https://api.telegram.org/bot<TOKEN>/setWebhook
            ?url=https://<your-domain>/api/notifications/telegram/webhook/
            &secret_token=<TELEGRAM_WEBHOOK_SECRET>
    """
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if secret and request.headers.get('X-Telegram-Bot-Api-Secret-Token') != secret:
        return Response(status=status.HTTP_403_FORBIDDEN)

    message = (request.data or {}).get('message') or {}
    chat_id = (message.get('chat') or {}).get('id')
    text = (message.get('text') or '').strip()

    # Always return 200 so Telegram doesn't endlessly redeliver updates.
    if not (chat_id and text):
        return Response({'ok': True})

    if text.startswith('/start'):
        parts = text.split(maxsplit=1)
        identifier = parts[1].strip() if len(parts) > 1 else ''

        customer = None
        if identifier:
            customer = Customer.objects.filter(username__iexact=identifier).first()
            if not customer:
                normalized = normalize_phone(identifier)
                if normalized:
                    # phone_number is stored in assorted formats; match on suffix
                    customer = Customer.objects.filter(
                        phone_number__endswith=normalized[-9:]
                    ).first()

        if customer:
            customer.telegram_chat_id = str(chat_id)
            customer.save(update_fields=['telegram_chat_id'])
            send_telegram(chat_id, (
                f"Hi {customer.first_name or customer.username}, your account is now "
                "linked. You will receive payment and subscription alerts here."
            ))
            logger.info(f"Linked Telegram chat {chat_id} to customer {customer.username}")
        else:
            send_telegram(chat_id, (
                "To link your account, send: /start <your username or phone number>"
            ))

    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def send_test(request):
    """
    Admin utility to verify provider credentials without waiting for a real
    event. Body: {"channel": "sms|whatsapp|telegram", "recipient": "...",
    "message": "..."} -- sends synchronously and returns the provider result.
    """
    channel = request.data.get('channel')
    recipient = request.data.get('recipient')
    message = request.data.get('message', 'Test notification from your ISP billing system.')

    sender = SENDERS.get(channel)
    if not sender:
        return Response(
            {'error': f"channel must be one of {sorted(SENDERS)}"},
            status=status.HTTP_400_BAD_REQUEST
        )
    if not recipient:
        return Response({'error': 'recipient is required'}, status=status.HTTP_400_BAD_REQUEST)

    ok, detail = sender(recipient, message)
    return Response({'success': ok, 'detail': detail},
                    status=status.HTTP_200_OK if ok else status.HTTP_502_BAD_GATEWAY)
