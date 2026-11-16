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

        if channel not in ('sms', 'whatsapp', 'telegram', 'email'):
            return Response({'error': 'channel must be sms, whatsapp, telegram or email'}, status=400)
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
        if not channels or any(c not in ('sms', 'whatsapp', 'telegram', 'email') for c in channels):
            return Response({'error': 'channels must be a non-empty list of sms/whatsapp/telegram/email'}, status=400)

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



# --- Message templates (admin only, like the rest of notification settings) ---

def _system_templates_payload():
    from apps.notifications.models import MessageTemplate
    from apps.notifications.templates import DEFAULTS, placeholders_for
    saved = {t.key: t for t in MessageTemplate.objects.filter(kind='system')}
    return [
        {
            'key': key,
            'name': label,
            'body': saved[key].body if key in saved else default,
            'default_body': default,
            'is_custom': key in saved,
            'placeholders': placeholders_for(key),
        }
        for key, (label, default, _) in DEFAULTS.items()
    ]


class MessageTemplatesView(APIView):
    """GET: the system messages (current wording + defaults) and saved promotional templates."""
    permission_classes = [RoleAllowed('admin')]

    def get(self, request):
        from apps.notifications.models import MessageTemplate
        from apps.notifications.templates import COMMON
        return Response({
            'system': _system_templates_payload(),
            'promo': [
                {'id': t.id, 'name': t.name, 'body': t.body, 'updated_at': t.updated_at}
                for t in MessageTemplate.objects.filter(kind='promo')
            ],
            'promo_placeholders': COMMON,
        })


class SystemTemplateView(APIView):
    """PUT {body}: customise a system message. DELETE: back to the default wording."""
    permission_classes = [RoleAllowed('admin')]

    def put(self, request, key):
        from apps.notifications.models import MessageTemplate
        from apps.notifications.templates import DEFAULTS, customer_context, fill
        if key not in DEFAULTS:
            return Response({'error': 'Unknown message.'}, status=404)
        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'error': 'The message cannot be empty.'}, status=400)
        try:
            fill(body, customer_context(None))
        except (ValueError, IndexError) as e:
            return Response({'error': f'Check the curly braces: {e}'}, status=400)
        MessageTemplate.objects.update_or_create(
            kind='system', key=key, defaults={'name': DEFAULTS[key][0], 'body': body},
        )
        return Response({'system': _system_templates_payload()})

    def delete(self, request, key):
        from apps.notifications.models import MessageTemplate
        MessageTemplate.objects.filter(kind='system', key=key).delete()
        return Response({'system': _system_templates_payload()})


class PromoTemplateView(APIView):
    """POST {name, body}: save a promotional template. PATCH/DELETE /<id>/."""
    permission_classes = [RoleAllowed('admin')]

    def _validate(self, data, partial=False):
        from apps.notifications.templates import customer_context, fill
        name = (data.get('name') or '').strip()
        body = (data.get('body') or '').strip()
        if not partial and (not name or not body):
            return None, Response({'error': 'Name and message are required.'}, status=400)
        if body:
            try:
                fill(body, customer_context(None))
            except (ValueError, IndexError) as e:
                return None, Response({'error': f'Check the curly braces: {e}'}, status=400)
        return {k: v for k, v in (('name', name), ('body', body)) if v}, None

    def post(self, request):
        from apps.notifications.models import MessageTemplate
        fields, error = self._validate(request.data)
        if error:
            return error
        t = MessageTemplate.objects.create(kind='promo', **fields)
        return Response({'id': t.id, 'name': t.name, 'body': t.body}, status=201)

    def patch(self, request, pk):
        from apps.notifications.models import MessageTemplate
        t = MessageTemplate.objects.filter(kind='promo', pk=pk).first()
        if not t:
            return Response({'error': 'Not found.'}, status=404)
        fields, error = self._validate(request.data, partial=True)
        if error:
            return error
        for k, v in fields.items():
            setattr(t, k, v)
        t.save()
        return Response({'id': t.id, 'name': t.name, 'body': t.body})

    def delete(self, request, pk):
        from apps.notifications.models import MessageTemplate
        MessageTemplate.objects.filter(kind='promo', pk=pk).delete()
        return Response(status=204)


class TemplatePreviewView(APIView):
    """POST {body, key?}: the text as a customer would receive it, with sample values."""
    permission_classes = [RoleAllowed('admin')]

    SAMPLE = {
        'first_name': 'Grace', 'name': 'Grace Wanjiru', 'username': 'HSN-10482',
        'amount': '2500.00', 'plan': 'Home 10 Mbps', 'expiry': '14 Dec 2026 23:59', 'balance': '500.00',
        'action': 'extended', 'price': 'KES 2,500', 'expiry_text': 'expires on 14 Dec 2026 at 23:59',
        'how_to_pay': 'pay KES 2,500 via M-Pesa Buy Goods, Till 123456, from 0722618418', 'code': 'KTWM',
    }

    def post(self, request):
        from apps.notifications.templates import customer_context, fill
        body = request.data.get('body') or ''
        context = {**self.SAMPLE, **{k: v for k, v in customer_context(None).items() if v}}
        try:
            text = fill(body, context)
        except (ValueError, IndexError) as e:
            return Response({'error': f'Check the curly braces: {e}'}, status=400)
        return Response({'preview': text, 'length': len(text), 'sms_parts': max(1, -(-len(text) // 160))})



class DailyReportSendNowView(APIView):
    """POST: email today's sales report to the superadmins now (for checking the setup)."""
    permission_classes = [RoleAllowed('admin')]

    def post(self, request):
        from apps.notifications.admin_emails import admin_email_recipients, send_daily_report
        s = NotificationSettings.load()
        has_email = s.email_enabled and admin_email_recipients()
        has_phone = s.phone_list() and s.phone_channels()
        if not has_email and not has_phone:
            return Response({'error': 'Add an admin email (with Email turned on) or an admin phone under Admin contacts first.'}, status=400)
        sent = send_daily_report(force=True)
        if not sent:
            return Response({'error': 'The email could not be sent -- see the notification log for the reason.'}, status=502)
        return Response({'sent': sent})


# --- Notification status report (every outgoing message) ---

class NotificationReportView(APIView):
    """
    GET: delivery report over the notification log -- totals, per channel,
    per message type, the commonest failure reasons, and a page of messages.
    Filters: start_date/end_date (default last 7 days, Nairobi days), channel,
    status (sent|failed), event_type, search (recipient / customer).
    ?export=csv|xlsx|pdf downloads the filtered messages.
    """
    permission_classes = [RoleAllowed('admin')]

    def get(self, request):
        import datetime as dt
        from django.db.models import Count, Q
        from django.utils import timezone
        from apps.analytics.exports import Section, export_format, export_response
        from apps.notifications.models import NotificationLog

        p = request.query_params
        today = timezone.localdate()

        def day(value, default):
            try:
                return dt.date.fromisoformat(value) if value else default
            except ValueError:
                return default

        start, end = day(p.get('start_date'), today - dt.timedelta(days=6)), day(p.get('end_date'), today)
        qs = NotificationLog.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
        if p.get('channel'):
            qs = qs.filter(channel=p['channel'])
        if p.get('event_type'):
            qs = qs.filter(event_type=p['event_type'])
        if p.get('search'):
            term = p['search'].strip()
            qs = qs.filter(Q(recipient__icontains=term) | Q(customer__username__icontains=term)
                           | Q(customer__first_name__icontains=term) | Q(customer__last_name__icontains=term)
                           | Q(message__icontains=term))
        # Summary/breakdowns ignore the status filter so the totals stay whole.
        base = qs
        if p.get('status') == 'sent':
            qs = qs.filter(status='sent')
        elif p.get('status') == 'failed':
            qs = qs.exclude(status='sent')

        events = dict(NotificationLog.EVENT_TYPE_CHOICES)
        channels = dict(NotificationLog.CHANNEL_CHOICES)
        failed_q = ~Q(status='sent')
        totals = base.aggregate(total=Count('id'), sent=Count('id', filter=Q(status='sent')), failed=Count('id', filter=failed_q))
        by_channel = [
            {'channel': r['channel'], 'label': channels.get(r['channel'], r['channel']), 'sent': r['sent'], 'failed': r['failed']}
            for r in base.values('channel').annotate(sent=Count('id', filter=Q(status='sent')), failed=Count('id', filter=failed_q)).order_by('channel')
        ]
        by_event = [
            {'event_type': r['event_type'], 'label': events.get(r['event_type'], r['event_type']), 'sent': r['sent'], 'failed': r['failed']}
            for r in base.values('event_type').annotate(sent=Count('id', filter=Q(status='sent')), failed=Count('id', filter=failed_q)).order_by('-failed', '-sent')
        ]
        # Group failures by the start of their message (the code/cause),
        # since the tail often carries per-message detail.
        reasons = {}
        for err in base.filter(failed_q).values_list('error', flat=True)[:2000]:
            key = (err or 'No reason recorded').split(' -- ')[0][:140]
            reasons[key] = reasons.get(key, 0) + 1
        top_errors = [{'error': k, 'count': v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:8]]

        def row(log):
            customer = log.customer
            return {
                'id': log.id,
                'created_at': log.created_at,
                'channel': log.channel,
                'channel_label': channels.get(log.channel, log.channel),
                'event_type': log.event_type,
                'event_label': events.get(log.event_type, log.event_type),
                'recipient': log.recipient,
                'customer': {'id': customer.id, 'username': customer.username,
                             'name': customer.get_full_name() or customer.username} if customer else None,
                'status': 'sent' if log.status == 'sent' else 'failed',
                'error': log.error,
                'message': log.message,
            }

        ordered = qs.select_related('customer').order_by('-created_at')
        fmt = export_format(request)
        if fmt:
            rows = [
                [r['created_at'], r['channel_label'], r['event_label'], r['recipient'],
                 r['customer']['name'] if r['customer'] else '', 'Sent' if r['status'] == 'sent' else 'Failed',
                 r['error'][:200], r['message'][:300]]
                for r in (row(log) for log in ordered[:5000])
            ]
            rate = f"{totals['sent'] / totals['total'] * 100:.1f}%" if totals['total'] else '—'
            return export_response(
                fmt,
                filename=f'notifications_{start}_{end}',
                title='Notification delivery report',
                subtitle=f"{start:%d %b %Y} to {end:%d %b %Y}",
                summary=[('Messages', totals['total']), ('Sent', totals['sent']), ('Failed', totals['failed']), ('Delivery rate', rate)],
                sections=[
                    Section(['Channel', 'Sent', 'Failed'], [[c['label'], c['sent'], c['failed']] for c in by_channel],
                            heading='By channel', numeric=(1, 2)),
                    Section(['Reason', 'Count'], [[e['error'], e['count']] for e in top_errors],
                            heading='Most common failures', numeric=(1,)),
                    Section(['Time', 'Channel', 'Type', 'Recipient', 'Customer', 'Status', 'Error', 'Message'], rows,
                            heading='Messages'),
                ],
            )

        page = max(int(p.get('page', 1) or 1), 1)
        page_size = min(max(int(p.get('page_size', 25) or 25), 1), 100)
        count = ordered.count()
        return Response({
            'start_date': start, 'end_date': end,
            'summary': {**totals, 'delivery_rate': round(totals['sent'] / totals['total'] * 100, 1) if totals['total'] else None},
            'by_channel': by_channel,
            'by_event': by_event,
            'top_errors': top_errors,
            'results': [row(log) for log in ordered[(page - 1) * page_size: page * page_size]],
            'count': count,
            'page': page,
            'total_pages': max((count + page_size - 1) // page_size, 1),
            'event_types': [{'value': k, 'label': v} for k, v in NotificationLog.EVENT_TYPE_CHOICES],
            'channels': [{'value': k, 'label': v} for k, v in NotificationLog.CHANNEL_CHOICES],
        })


class NotificationResendView(APIView):
    """POST: send a logged message again, to the same recipient on the same channel (logged as a new attempt)."""
    permission_classes = [RoleAllowed('admin')]

    def post(self, request, pk):
        from apps.notifications.models import NotificationLog
        log = NotificationLog.objects.filter(pk=pk).first()
        if not log:
            return Response({'error': 'Message not found.'}, status=404)
        if not log.recipient:
            return Response({'error': 'This message had no recipient address, so it cannot be resent.'}, status=400)
        if log.channel == 'email':
            from apps.notifications.services.email_service import EmailService
            subject, _, body = log.message.partition('\n\n') if '\n\n' in log.message[:200] else (None, '', log.message)
            result = EmailService().send_email(log.recipient, body or log.message, subject=subject)
            NotificationLog.objects.create(
                customer=log.customer, subscription=log.subscription, channel='email', event_type=log.event_type,
                recipient=log.recipient, message=log.message, status='sent' if result['success'] else 'failed',
                error='' if result['success'] else str(result.get('error', '')),
            )
        else:
            result = send_and_log(channel=log.channel, recipient=log.recipient, message=log.message,
                                  event_type=log.event_type, customer=log.customer, subscription=log.subscription)
        if result['success']:
            return Response({'success': True, 'message': 'Sent again.'})
        return Response({'success': False, 'error': result.get('error') or 'Still failing.'}, status=502)
