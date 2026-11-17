from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from cloud.accounts.permissions import IsPlatform, IsPlatformOrReadOnlyStaff
from cloud.core.models import PlatformSettings

SECRETS = ['mpesa_passkey', 'mpesa_consumer_key', 'mpesa_consumer_secret', 'tenant_consumer_key',
           'tenant_consumer_secret', 'initiator_password', 'mpesa_certificate']


class SettingsSerializer(serializers.ModelSerializer):
    """Secrets are write-only; `<name>_set` says whether one is stored.
    A blank value in a PATCH keeps the stored secret."""

    class Meta:
        model = PlatformSettings
        exclude = ['id', 'c2b_secret']
        read_only_fields = ['c2b_registered_at', 'updated_at']
        extra_kwargs = {name: {'write_only': True, 'required': False, 'allow_blank': True} for name in SECRETS}

    def to_representation(self, obj):
        data = super().to_representation(obj)
        for name in SECRETS:
            data[f'{name}_set'] = bool(getattr(obj, name))
        data['c2b_urls'] = {
            'confirmation': obj.public_url(f'/api/mpesa/c2b/{obj.c2b_secret}/confirmation/') if obj.public_base_url else '',
            'validation': obj.public_url(f'/api/mpesa/c2b/{obj.c2b_secret}/validation/') if obj.public_base_url else '',
        }
        data['warnings'] = warnings(obj)
        return data

    def validate_invoice_day(self, v):
        if not 1 <= v <= 28:
            raise serializers.ValidationError('Pick a day from 1 to 28 (every month has one).')
        return v

    def validate_settlement_hour(self, v):
        if v > 23:
            raise serializers.ValidationError('Hour must be 0-23.')
        return v

    def validate_settlement_weekday(self, v):
        if v > 6:
            raise serializers.ValidationError('0 (Monday) to 6 (Sunday).')
        return v

    def validate_mpesa_certificate(self, v):
        if v and 'BEGIN CERTIFICATE' not in v:
            raise serializers.ValidationError('Paste the whole certificate, including the BEGIN/END CERTIFICATE lines.')
        return v

    def validate(self, data):
        start = data.get('port_range_start', self.instance.port_range_start if self.instance else 9500)
        end = data.get('port_range_end', self.instance.port_range_end if self.instance else 9999)
        if not 1024 < start <= end < 65536:
            raise serializers.ValidationError({'port_range_end': 'Use a range between 1025 and 65535.'})
        if data.get('public_base_url'):
            data['public_base_url'] = data['public_base_url'].rstrip('/')
            if not data['public_base_url'].startswith('https://'):
                raise serializers.ValidationError({'public_base_url': 'Safaricom only calls HTTPS addresses.'})
        return data

    def update(self, instance, data):
        for name in SECRETS:
            if name in data and not data[name]:
                data.pop(name)
        return super().update(instance, data)


def warnings(cfg):
    out = []
    if not cfg.public_base_url:
        out.append('Set the public address: without it Safaricom has nowhere to send payments.')
    if not (cfg.mpesa_shortcode and cfg.mpesa_passkey and cfg.mpesa_consumer_key and cfg.mpesa_consumer_secret):
        out.append('M-Pesa collection is not fully set up (shortcode, passkey, consumer key and secret).')
    if not (cfg.tenant_consumer_key and cfg.tenant_consumer_secret):
        out.append('No ISP-instance Daraja app set: ISP instances cannot start STK payments.')
    elif cfg.tenant_consumer_key == cfg.mpesa_consumer_key:
        out.append('ISP instances use the same Daraja app as the platform. Their admins can read it -- give them a '
                   'separate app with only M-Pesa Express enabled.')
    if not cfg.c2b_registered_at:
        out.append('C2B URLs are not registered yet, so paybill payments will not reach the platform.')
    if not (cfg.initiator_name and cfg.initiator_password and cfg.mpesa_certificate):
        out.append('Payouts are not set up (initiator name, password and Safaricom certificate).')
    return out


class SettingsView(APIView):
    permission_classes = [IsPlatformOrReadOnlyStaff]

    def get(self, request):
        return Response(SettingsSerializer(PlatformSettings.load()).data)

    def patch(self, request):
        cfg = PlatformSettings.load()
        mpesa_before = {f: getattr(cfg, f) for f in ('mpesa_environment', 'mpesa_shortcode', 'mpesa_shortcode_type',
                                                     'mpesa_till_number', 'mpesa_passkey', 'tenant_consumer_key',
                                                     'tenant_consumer_secret', 'public_base_url', 'tenant_host',
                                                     'tenant_url_template')}
        s = SettingsSerializer(cfg, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        changed = [f for f, v in mpesa_before.items() if getattr(cfg, f) != v]
        if changed:
            # Instances carry these in their env: re-apply to all of them.
            from cloud.tenants.tasks import resync_all
            resync_all.delay()
        data = dict(s.data)
        data['resynced'] = bool(changed)
        return Response(data)


class MpesaActionView(APIView):
    """POST {action: test | register_c2b}"""
    permission_classes = [IsPlatformOrReadOnlyStaff]

    def post(self, request):
        from cloud.billing.daraja import Daraja, DarajaError, security_credential
        cfg = PlatformSettings.load()
        action = request.data.get('action')
        try:
            if action == 'test':
                Daraja(cfg).token()
                result = {'platform_app': 'ok'}
                if cfg.tenant_consumer_key:
                    Daraja(cfg, cfg.tenant_consumer_key, cfg.tenant_consumer_secret).token()
                    result['tenant_app'] = 'ok'
                if cfg.mpesa_certificate and cfg.initiator_password:
                    security_credential(cfg.mpesa_certificate, cfg.initiator_password)
                    result['security_credential'] = 'ok'
                return Response({'ok': True, **result})
            if action == 'register_c2b':
                if not cfg.public_base_url:
                    return Response({'error': 'Set the public address first'}, status=400)
                resp = Daraja(cfg).register_c2b(
                    cfg.public_url(f'/api/mpesa/c2b/{cfg.c2b_secret}/confirmation/'),
                    cfg.public_url(f'/api/mpesa/c2b/{cfg.c2b_secret}/validation/'))
                cfg.c2b_registered_at = timezone.now()
                cfg.save(update_fields=['c2b_registered_at'])
                return Response({'ok': True, 'response': resp})
        except DarajaError as e:
            return Response({'ok': False, 'error': str(e)}, status=400)
        return Response({'error': 'Unknown action'}, status=400)


class PublicConfigView(APIView):
    """What the public sign-up page needs (brand, plans, trial length)."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from cloud.pricing.models import PricingPlan
        from cloud.pricing.views import PlanSerializer
        cfg = PlatformSettings.load()
        plans = PricingPlan.objects.filter(is_active=True, is_public=True).prefetch_related('tiers')
        return Response({'brand_name': cfg.brand_name, 'trial_days': cfg.trial_days, 'signup_enabled': cfg.signup_enabled,
                         'support_email': cfg.support_email, 'support_phone': cfg.support_phone, 'terms_url': cfg.terms_url,
                         'plans': PlanSerializer(plans, many=True).data})


class DashboardView(APIView):
    permission_classes = [IsPlatform]

    def get(self, request):
        from cloud.billing.models import Collection, Invoice, LedgerEntry, Settlement
        from cloud.tenants.models import Tenant
        now = timezone.now()
        month_start = timezone.localtime(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tenants = Tenant.objects.exclude(status='deleted')
        by_status = dict(tenants.values_list('status').annotate(n=Count('id')))
        collected = Collection.objects.filter(verified=True, tenant__isnull=False)
        held = LedgerEntry.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0')
        days = []
        for i in range(29, -1, -1):
            day = timezone.localdate(now) - timedelta(days=i)
            days.append(day)
        per_day = {row['day']: row['total'] for row in collected.filter(paid_at__date__gte=days[0])
                   .annotate(day=TruncDate('paid_at')).values('day').annotate(total=Sum('amount'))}
        subscribers = 0
        for t in tenants.filter(status__in=Tenant.LIVE):
            subscribers += sum((t.metrics.get('active') or {}).values())
        return Response({
            'tenants': {'total': tenants.count(), 'by_status': by_status},
            'trials_ending_24h': tenants.filter(status='trial', trial_ends_at__lte=now + timedelta(hours=24)).count(),
            'subscribers_active': subscribers,
            'collected_month': collected.filter(paid_at__gte=month_start).aggregate(s=Sum('amount'))['s'] or 0,
            'collected_today': collected.filter(paid_at__date=timezone.localdate(now)).aggregate(s=Sum('amount'))['s'] or 0,
            'collections_by_day': [{'date': d.isoformat(), 'amount': float(per_day.get(d) or 0)} for d in days],
            'held_for_isps': held,
            'invoiced_month': Invoice.objects.filter(issued_at__gte=month_start).exclude(status='void').aggregate(s=Sum('amount'))['s'] or 0,
            'unpaid_invoices': Invoice.objects.filter(status='open').aggregate(s=Sum('amount'), n=Count('id')),
            'paid_out_month': Settlement.objects.filter(status='succeeded', completed_at__gte=month_start).aggregate(s=Sum('amount'))['s'] or 0,
            'payouts_awaiting_approval': Settlement.objects.filter(status='pending_approval').count(),
            'unallocated_payments': Collection.objects.filter(tenant__isnull=True).count(),
            'unhealthy': tenants.filter(status__in=Tenant.LIVE, instance_state__in=['unhealthy', 'missing', 'stopped']).count(),
            'settings_warnings': warnings(PlatformSettings.load()),
        })
