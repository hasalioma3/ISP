import re

from django.contrib.auth import get_user_model, password_validation
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from cloud.accounts.permissions import IsPlatform, IsTenantOwner
from cloud.accounts.views import UserSerializer, tokens_for
from cloud.pricing.models import PricingPlan
from cloud.tenants.models import RESERVED_SLUGS, SLUG_RE, Tenant, TenantEvent, UsageSnapshot

User = get_user_model()


class LargePages(PageNumberPagination):
    page_size_query_param = 'page_size'  # pickers ask for everything at once
    max_page_size = 500


def suggest_slug(name):
    base = re.sub(r'[^a-z0-9]', '', (name or '').lower())
    if not base or not base[0].isalpha():
        base = 'isp' + base
    base = base[:24]
    if len(base) < 3:
        base = (base + 'net')[:24]
    candidate, n = base, 1
    while Tenant.objects.filter(slug=candidate).exists() or candidate in RESERVED_SLUGS:
        n += 1
        candidate = f'{base[:22]}{n}'
    return candidate


# --- serializers ------------------------------------------------------------

class EventSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source='actor.email', default=None)

    class Meta:
        model = TenantEvent
        fields = ['id', 'created_at', 'kind', 'message', 'actor']


class TenantSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', default=None, read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    instance_label = serializers.CharField(source='get_instance_state_display', read_only=True)
    url = serializers.CharField(read_only=True)
    trial_seconds_left = serializers.IntegerField(read_only=True)
    balance = serializers.SerializerMethodField()
    subscribers = serializers.SerializerMethodField()
    estimate = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ['id', 'slug', 'name', 'contact_name', 'contact_email', 'contact_phone', 'status', 'status_label',
                  'plan', 'plan_name', 'discount_percent', 'notes', 'created_at', 'ready_at', 'trial_ends_at',
                  'trial_seconds_left', 'activated_at', 'suspended_at', 'suspend_reason', 'cancel_requested_at',
                  'port', 'url', 'admin_username', 'instance_state', 'instance_label', 'last_health_at', 'last_error',
                  'image_tag', 'account_prefix', 'settlement_method', 'settlement_account', 'settlement_account_ref',
                  'settlement_name', 'settlement_hold', 'metrics', 'metrics_at', 'balance', 'subscribers', 'estimate']
        read_only_fields = ['slug', 'status', 'created_at', 'ready_at', 'trial_ends_at', 'activated_at', 'suspended_at',
                            'suspend_reason', 'cancel_requested_at', 'port', 'admin_username', 'instance_state',
                            'last_health_at', 'last_error', 'image_tag', 'account_prefix', 'metrics', 'metrics_at']

    def get_balance(self, obj):
        from cloud.billing.ledger import balance
        return str(balance(obj))

    def get_subscribers(self, obj):
        m = obj.metrics or {}
        return {'active': sum((m.get('active') or {}).values()), 'all': sum((m.get('all') or {}).values())}

    def get_estimate(self, obj):
        """This month's bill at today's counts, by the tenant's plan rules."""
        from cloud.billing.invoicing import counted
        plan = obj.effective_plan()
        if not plan:
            return None
        n = counted(plan, obj.metrics or {})
        return {'plan': plan.name, 'counted_subscribers': n, **plan.quote(n)}

    def validate_settlement_account(self, v):
        return re.sub(r'\s+', '', v or '')

    def validate(self, data):
        method = data.get('settlement_method', getattr(self.instance, 'settlement_method', ''))
        account = data.get('settlement_account', getattr(self.instance, 'settlement_account', ''))
        if method == 'phone' and account:
            from cloud.billing.daraja import DarajaError, normalize_phone
            try:
                data['settlement_account'] = normalize_phone(account)
            except DarajaError as e:
                raise serializers.ValidationError({'settlement_account': str(e)})
        elif method in ('paybill', 'till') and account and not re.fullmatch(r'\d{5,7}', account):
            raise serializers.ValidationError({'settlement_account': 'A paybill or till number is 5-7 digits.'})
        if method == 'paybill' and 'settlement_account_ref' in data and not data['settlement_account_ref']:
            raise serializers.ValidationError({'settlement_account_ref': 'Paybills need an account number.'})
        return data


OWNER_FIELDS = [f for f in TenantSerializer.Meta.fields
                if f not in ('notes', 'discount_percent', 'last_error', 'image_tag', 'settlement_hold', 'port')]
OWNER_WRITABLE = ('name', 'contact_name', 'contact_phone', 'settlement_method', 'settlement_account',
                  'settlement_account_ref', 'settlement_name')


class OwnerTenantSerializer(TenantSerializer):
    """What an ISP owner may see and change about their own tenant."""

    class Meta(TenantSerializer.Meta):
        fields = OWNER_FIELDS
        read_only_fields = [f for f in OWNER_FIELDS if f not in OWNER_WRITABLE]


class SignupSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=150)
    slug = serializers.CharField(max_length=30, required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True)
    plan = serializers.SlugField(required=False, allow_blank=True)
    accept_terms = serializers.BooleanField()

    def validate_email(self, v):
        v = v.lower()
        if User.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError('An account with this email already exists -- sign in instead.')
        return v

    def validate_phone(self, v):
        from cloud.billing.daraja import DarajaError, normalize_phone
        try:
            return normalize_phone(v)
        except DarajaError as e:
            raise serializers.ValidationError(str(e))

    def validate_slug(self, v):
        v = (v or '').strip().lower()
        if not v:
            return v
        if not SLUG_RE.match(v):
            raise serializers.ValidationError('3-30 lowercase letters or digits, starting with a letter.')
        if v in RESERVED_SLUGS or Tenant.objects.filter(slug=v).exists():
            raise serializers.ValidationError('That name is taken. Try another.')
        return v

    def validate_plan(self, v):
        if not v:
            return None
        plan = PricingPlan.objects.filter(code=v, is_active=True, is_public=True).first()
        if not plan:
            raise serializers.ValidationError('That plan is not available.')
        return plan

    def validate_accept_terms(self, v):
        if not v:
            raise serializers.ValidationError('Please accept the terms to continue.')
        return v

    def validate(self, data):
        try:
            password_validation.validate_password(data['password'], User(email=data['email'], first_name=data['full_name']))
        except Exception as e:
            raise serializers.ValidationError({'password': list(getattr(e, 'messages', [str(e)]))})
        data['slug'] = data.get('slug') or suggest_slug(data['company_name'])
        return data


# --- public -------------------------------------------------------------------

class SignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'signup'

    def post(self, request):
        from cloud.tenants.services import TenantError, signup
        s = SignupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            tenant, user = signup(company_name=d['company_name'], slug=d['slug'], full_name=d['full_name'],
                                  email=d['email'], phone=d['phone'], password=d['password'], plan=d.get('plan'))
        except TenantError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({'tenant': OwnerTenantSerializer(tenant).data, 'user': UserSerializer(user).data,
                         **tokens_for(user)}, status=201)


class SlugCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        slug = (request.query_params.get('slug') or '').lower()
        name = request.query_params.get('name')
        if name and not slug:
            return Response({'slug': suggest_slug(name), 'available': True})
        ok = bool(SLUG_RE.match(slug)) and slug not in RESERVED_SLUGS and not Tenant.objects.filter(slug=slug).exists()
        return Response({'slug': slug, 'available': ok})


# --- platform admin -----------------------------------------------------------

class TenantListView(APIView):
    permission_classes = [IsPlatform]

    def get(self, request):
        qs = Tenant.objects.select_related('plan')
        p = request.query_params
        if p.get('status'):
            qs = qs.filter(status__in=p['status'].split(','))
        else:
            qs = qs.exclude(status='deleted')
        if p.get('search'):
            q = p['search']
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(contact_email__icontains=q) |
                           Q(contact_phone__icontains=q) | Q(contact_name__icontains=q))
        if p.get('plan'):
            qs = qs.filter(plan_id=p['plan'])
        pager = LargePages()
        page = pager.paginate_queryset(qs, request)
        return pager.get_paginated_response(TenantSerializer(page, many=True).data)


class TenantDetailView(APIView):
    permission_classes = [IsPlatform]

    def get(self, request, pk):
        t = Tenant.objects.filter(pk=pk).first()
        if not t:
            return Response(status=404)
        data = TenantSerializer(t).data
        data['owners'] = UserSerializer(t.owners.all(), many=True).data
        data['events'] = EventSerializer(t.events.select_related('actor')[:100], many=True).data
        data['snapshots'] = list(UsageSnapshot.objects.filter(tenant=t).values('date', 'peak', 'latest')[:62])
        return Response(data)

    def patch(self, request, pk):
        t = Tenant.objects.filter(pk=pk).first()
        if not t:
            return Response(status=404)
        if not request.user.is_platform_admin and set(request.data) - {'notes'}:
            return Response({'error': 'Support staff can only edit notes.'}, status=403)
        s = TenantSerializer(t, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        before_plan = t.plan_id
        s.save()
        from cloud.tenants.services import log
        if 'plan' in request.data and t.plan_id != before_plan:
            log(t, 'billing', f'Plan changed to {t.plan.name if t.plan else "default"}', actor=request.user)
        elif set(request.data) - {'notes'}:
            log(t, 'note', 'Details updated: ' + ', '.join(sorted(request.data)), actor=request.user)
        return Response(TenantSerializer(t).data)


ACTIONS = {
    # action: (admin only, runs in worker)
    'suspend': (True, True), 'resume': (True, True), 'restart': (True, True), 'cancel': (True, True),
    'destroy': (True, True), 'resync': (True, True), 'extend_trial': (True, True), 'metrics': (False, True),
    'health': (False, True), 'retry_provision': (True, True), 'activate': (True, False), 'note': (False, False),
    'logs': (False, False),
}


class TenantActionView(APIView):
    """POST {action, ...} -- see ACTIONS. Instance work is queued; poll the tenant."""
    permission_classes = [IsPlatform]

    def post(self, request, pk):
        from cloud.tenants import services
        from cloud.tenants.tasks import provision_tenant, tenant_action
        t = Tenant.objects.filter(pk=pk).first()
        if not t:
            return Response(status=404)
        action = request.data.get('action')
        if action not in ACTIONS:
            return Response({'error': 'Unknown action'}, status=400)
        admin_only, queued = ACTIONS[action]
        if admin_only and not request.user.is_platform_admin:
            return Response({'error': 'Platform admins only.'}, status=403)
        if action == 'destroy' and request.data.get('confirm') != t.slug:
            return Response({'error': f'Type the tenant ID ({t.slug}) to confirm.'}, status=400)
        if action == 'note':
            services.log(t, 'note', (request.data.get('message') or '').strip()[:2000] or '(empty)', actor=request.user)
            return Response({'ok': True})
        if action == 'logs':
            from cloud.tenants.orchestrator import OrchestratorError, get_orchestrator
            try:
                return Response({'logs': get_orchestrator().logs(t, request.data.get('service') or 'backend')})
            except OrchestratorError as e:
                return Response({'error': str(e)}, status=400)
        if action == 'activate':
            plan = PricingPlan.objects.filter(pk=request.data.get('plan') or getattr(t.plan, 'pk', None)).first() or t.effective_plan()
            if not plan:
                return Response({'error': 'Create a pricing plan first'}, status=400)
            try:
                services.activate(t, plan, actor=request.user)
            except services.TenantError as e:
                return Response({'error': str(e)}, status=400)
            return Response(TenantSerializer(t).data)
        if action == 'retry_provision':
            if t.status not in ('failed', 'pending'):
                return Response({'error': 'Only a failed or pending setup can be retried.'}, status=400)
            provision_tenant.delay(t.pk)
        else:
            extra = {k: request.data[k] for k in ('reason', 'days') if k in request.data}
            tenant_action.delay(t.pk, action, request.user.pk, **extra)
        return Response({'queued': True, 'action': action}, status=202)


# --- ISP owner portal -----------------------------------------------------------

class PortalTenantView(APIView):
    permission_classes = [IsTenantOwner]

    def get(self, request):
        t = request.user.tenant
        data = OwnerTenantSerializer(t).data
        data['events'] = EventSerializer(t.events.exclude(kind='error').select_related('actor')[:30], many=True).data
        from cloud.billing.settlement import available
        from cloud.core.models import PlatformSettings
        cfg = PlatformSettings.load()
        data['available_to_pay_out'] = str(available(t))
        # How this ISP's customers pay (the platform's shortcode).
        data['mpesa'] = {'shortcode': cfg.mpesa_till_number if cfg.mpesa_shortcode_type == 'till' and cfg.mpesa_till_number
                         else cfg.mpesa_shortcode, 'type': cfg.mpesa_shortcode_type, 'account_prefix': t.account_prefix}
        data['setup_steps'] = [e.message for e in t.events.filter(kind__in=['provision', 'error']).order_by('created_at')]
        return Response(data)

    def patch(self, request):
        t = request.user.tenant
        s = OwnerTenantSerializer(t, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        from cloud.tenants.services import log
        log(t, 'note', 'Account details updated: ' + ', '.join(sorted(request.data)), actor=request.user)
        return Response(OwnerTenantSerializer(t).data)


class PortalActivateView(APIView):
    """The ISP picks a plan and becomes a paying customer."""
    permission_classes = [IsTenantOwner]

    def post(self, request):
        from cloud.tenants import services
        t = request.user.tenant
        if t.status in ('pending', 'provisioning', 'failed', 'deleted'):
            return Response({'error': 'Your system is not ready yet.'}, status=400)
        plan = PricingPlan.objects.filter(code=request.data.get('plan'), is_active=True, is_public=True).first() \
            or (t.plan if t.plan and t.plan.is_active else None)
        if not plan:
            return Response({'error': 'Choose a plan.'}, status=400)
        if not request.data.get('accept_terms'):
            return Response({'error': 'Please accept the terms.'}, status=400)
        if any(k in request.data for k in ('settlement_method', 'settlement_account')):
            s = OwnerTenantSerializer(t, data={k: request.data[k] for k in ('settlement_method', 'settlement_account',
                                                                           'settlement_account_ref', 'settlement_name')
                                               if k in request.data}, partial=True)
            s.is_valid(raise_exception=True)
            s.save()
        try:
            services.activate(t, plan, actor=request.user)
        except services.TenantError as e:
            return Response({'error': str(e)}, status=400)
        return Response(OwnerTenantSerializer(t).data)


class PortalCancelView(APIView):
    permission_classes = [IsTenantOwner]

    def post(self, request):
        from django.utils import timezone
        from cloud.tenants.services import log
        t = request.user.tenant
        t.cancel_requested_at = timezone.now()
        t.save(update_fields=['cancel_requested_at'])
        log(t, 'lifecycle', f'Cancellation requested: {(request.data.get("reason") or "").strip()[:500]}', actor=request.user)
        return Response(OwnerTenantSerializer(t).data)


class PortalRetryView(APIView):
    """An owner can retry their own failed setup."""
    permission_classes = [IsTenantOwner]

    def post(self, request):
        from cloud.tenants.tasks import provision_tenant
        t = request.user.tenant
        if t.status != 'failed':
            return Response({'error': 'Nothing to retry.'}, status=400)
        provision_tenant.delay(t.pk)
        return Response({'queued': True}, status=202)
