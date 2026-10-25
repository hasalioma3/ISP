import hmac
import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customers.permissions import RoleAllowed

from .dispatch import send_and_log
from .models import NotificationSettings
from .serializers import NotificationSettingsSerializer
from .services.whatsapp_service import WhatsAppService
from .services.telegram_service import TelegramService
from .tasks import send_promo_broadcast

logger = logging.getLogger('notifications')


class NotificationSettingsView(APIView):
    """
    GET/PATCH the singleton NotificationSettings -- admin-only both ways,
    unlike SiteSettingsView's public GET, since this holds credentials.
    """
    permission_classes = [RoleAllowed('admin')]

    def get(self, request):
        return Response(NotificationSettingsSerializer(NotificationSettings.load()).data)

    def patch(self, request):
        serializer = NotificationSettingsSerializer(NotificationSettings.load(), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


class TestSendView(APIView):
    """POST {channel, recipient, message} -- synchronous, for the settings
    page's per-channel "Send test message" button."""
    permission_classes = [RoleAllowed('admin')]

    def post(self, request):
        channel = request.data.get('channel')
        recipient = request.data.get('recipient')
        message = request.data.get('message') or 'This is a test message from your ISP billing system.'

        if channel not in ('sms', 'whatsapp', 'telegram'):
            return Response({'error': 'channel must be sms, whatsapp, or telegram'}, status=400)
        if not recipient:
            return Response({'error': 'recipient is required'}, status=400)

        result = send_and_log(channel=channel, recipient=recipient, message=message, event_type='welcome')
        if result['success']:
            return Response(result)
        # 'error' key specifically (not just the first key of `result`) so
        # getErrorMessage.ts on the frontend surfaces the real provider
        # error instead of falling back to a generic message.
        return Response({'error': result.get('error') or 'Send failed'}, status=400)


class WhatsAppStatusView(APIView):
    """Proxies the whatsapp-service sidecar's /status so the browser never
    talks to it directly (it's not exposed outside the Docker network)."""
    permission_classes = [RoleAllowed('admin')]

    def get(self, request):
        return Response(WhatsAppService().get_status())


class PromoBroadcastView(APIView):
    """
    POST {message, channels: [...], service_type: 'pppoe'|'hotspot'|'all',
    dry_run: bool}. Admin-only -- bulk sends (especially WhatsApp) carry ban
    risk and are a business decision, kept out of the sales/technician
    roles consistent with the earlier decision restricting technicians from
    settings/bulk actions. dry_run previews the recipient count with no
    sends, for a safe preview before a real broadcast.
    """
    permission_classes = [RoleAllowed('admin')]

    def post(self, request):
        from apps.customers.models import Customer

        message = (request.data.get('message') or '').strip()
        channels = request.data.get('channels') or []
        service_type_filter = request.data.get('service_type') or 'pppoe'
        dry_run = bool(request.data.get('dry_run'))

        if not message:
            return Response({'error': 'message is required'}, status=400)
        if not channels or any(c not in ('sms', 'whatsapp', 'telegram') for c in channels):
            return Response({'error': 'channels must be a non-empty list of sms/whatsapp/telegram'}, status=400)

        qs = Customer.objects.filter(status='active')
        if service_type_filter == 'pppoe':
            qs = qs.filter(service_type__in=['pppoe', 'both'])
        elif service_type_filter == 'hotspot':
            qs = qs.filter(service_type__in=['hotspot', 'both'])
        elif service_type_filter != 'all':
            qs = qs.filter(service_type=service_type_filter)

        if dry_run:
            return Response({'recipient_count': qs.count()})

        send_promo_broadcast.delay(message, channels, service_type_filter)
        return Response({'queued': True, 'recipient_count': qs.count()})


class TelegramWebhookView(APIView):
    """
    POST from Telegram's servers when a customer messages the bot. Only
    handles /start <username> -- Telegram doesn't allow a bot to message a
    user first, so this is how a customer links their chat before they can
    receive any automated Telegram notification.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from apps.customers.models import Customer

        expected_secret = NotificationSettings.load().telegram_webhook_secret
        received_secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not expected_secret or not hmac.compare_digest(expected_secret, received_secret):
            return Response(status=403)

        message = request.data.get('message') or {}
        text = (message.get('text') or '').strip()
        chat_id = message.get('chat', {}).get('id')

        if not chat_id or not text.startswith('/start'):
            return Response({'ok': True})

        username = text[len('/start'):].strip()
        customer = Customer.objects.filter(username__iexact=username).first() if username else None
        if not customer:
            TelegramService().send_message(
                chat_id, "We couldn't match that to an account. Send /start <your portal username>."
            )
            return Response({'ok': True})

        customer.telegram_chat_id = str(chat_id)
        customer.save(update_fields=['telegram_chat_id'])
        TelegramService().send_message(chat_id, f"Linked! You'll now get notifications here, {customer.username}.")
        return Response({'ok': True})
