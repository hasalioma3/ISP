from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from apps.customers.models import Customer
from apps.customers.serializers import CustomerRegistrationSerializer, CustomerSerializer
from apps.notifications.tasks import send_welcome_notification


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    Register a new customer
    """
    serializer = CustomerRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        customer = serializer.save()
        transaction.on_commit(
            lambda: send_welcome_notification.delay(customer.id, request.data.get('password'))
        )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(customer)

        # Same reasoning as login(): request.user isn't the new customer yet.
        from types import SimpleNamespace
        serializer_context = {'request': SimpleNamespace(user=customer)}

        return Response({
            'customer': CustomerSerializer(customer, context=serializer_context).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Login customer
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    customer = authenticate(username=username, password=password)
    if not customer and username and password:
        # Voucher accounts use the code (stored uppercase) as both username
        # and password, and codes aren't case sensitive -- let "abcd"/"abcd"
        # sign in. Only for names that are voucher codes; every other login
        # stays exactly as typed.
        from apps.billing.models import Voucher
        if Voucher.objects.filter(code__iexact=username.strip()).exists():
            customer = authenticate(username=username.strip().upper(), password=password.strip().upper())

    if customer:
        from apps.customers.models import LoginActivity
        LoginActivity.objects.create(
            customer=customer,
            ip_address=request.META.get('REMOTE_ADDR')
        )

        refresh = RefreshToken.for_user(customer)

        # request.user is still AnonymousUser here -- authenticate() found a
        # match but nothing has attached it to the request, and no JWT
        # exists yet for DRF's own auth middleware to have run against. The
        # serializer's "is this the customer's own profile" check needs the
        # real customer, so build a minimal stand-in with just the one
        # attribute it reads.
        from types import SimpleNamespace
        serializer_context = {'request': SimpleNamespace(user=customer)}

        return Response({
            'customer': CustomerSerializer(customer, context=serializer_context).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        })
    
    return Response({
        'error': 'Invalid credentials'
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    Get customer profile
    """
    serializer = CustomerSerializer(request.user, context={'request': request})
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update the logged-in user's own basic details (name/email/phone) --
    intentionally NOT the full CustomerSerializer, see SelfProfileSerializer.
    """
    from apps.customers.serializers import SelfProfileSerializer

    serializer = SelfProfileSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change the logged-in user's own password (requires the current one).
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    old_password = request.data.get('old_password') or ''
    new_password = request.data.get('new_password') or ''

    if not request.user.check_password(old_password):
        return Response({'error': 'Current password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        validate_password(new_password, user=request.user)
    except ValidationError as e:
        return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

    request.user.set_password(new_password)
    request.user.save(update_fields=['password'])
    return Response({'success': True, 'message': 'Password changed successfully'})


from rest_framework import filters
from rest_framework.permissions import IsAdminUser
from apps.customers.serializers import StaffSerializer
from apps.customers.permissions import RoleAllowed

class StaffViewSet(viewsets.ModelViewSet):
    """
    Manage staff members -- admins only, since this controls who else gets
    admin-portal access and with what role.
    """
    queryset = Customer.objects.filter(is_staff=True)
    serializer_class = StaffSerializer
    permission_classes = [RoleAllowed('admin')]


class SubscriberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


def _deny_technician(request):
    """
    Technicians manage the network, not money: they can't renew/extend a
    subscription or record cash on an account (admins, sales and the
    superadmin can). Returns a 403 Response to send back, or None.
    """
    user = request.user
    if not user.is_superuser and getattr(user, 'role', '') == 'technician':
        return Response(
            {'error': 'Technicians cannot extend subscriptions or add money to accounts.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _notify_change(*, staff_message, customer_message, event_type, customer, subscription=None):
    """
    After a manual extension or cash credit commits, tell both the customer
    (SMS to their phone) and the manager alert number
    (NotificationSettings.staff_alert_phone). Queued on commit so nothing is
    sent for a change that rolled back.
    """
    from apps.notifications.tasks import send_customer_account_notice, send_staff_alert
    sub_id = subscription.id if subscription else None

    def queue():
        send_customer_account_notice.delay(customer.id, customer_message, event_type, subscription_id=sub_id)
        send_staff_alert.delay(staff_message, customer_id=customer.id, subscription_id=sub_id)
    transaction.on_commit(queue)


class SubscriberViewSet(
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet
):
    """
    View and edit subscribers (Admin only). No create/delete here --
    registration has its own flow, and deleting a customer is not exposed
    through this generic endpoint.
    """
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser]
    pagination_class = SubscriberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'phone_number', 'first_name', 'last_name', 'pppoe_username']
    ordering_fields = ['account_balance', 'calculated_expiry', 'created_at', 'username', 'latest_subscription_at']
    # Default: most recently subscribed first, not most recently registered --
    # a customer who signed up long ago but just renewed should surface
    # above one who registered yesterday and hasn't subscribed since.
    ordering = ['-latest_subscription_at']

    def get_queryset(self):
        from django.db.models import OuterRef, Subquery, CharField, Q
        from django.db.models.functions import Coalesce
        from django.utils import timezone
        from apps.billing.models import Subscription, UsageRecord

        # An active, not-yet-expired subscription always wins for display
        # purposes -- e.g. a still-active plan bought a while ago must not
        # lose to a more-recently-created but already-expired one (that
        # comparison is only "most recent" by created_at, not by what's
        # actually current). Falls back to the plain most-recent-by-
        # created_at subscription only when there's no active one at all.
        active_subscription = Subscription.objects.filter(
            customer=OuterRef('pk'), status='active', expiry_date__gt=timezone.now()
        ).order_by('-created_at')

        latest_subscription = Subscription.objects.filter(
            customer=OuterRef('pk')
        ).order_by('-created_at')

        latest_usage = UsageRecord.objects.filter(
            customer=OuterRef('pk')
        ).order_by('-created_at').values('framed_ip_address')[:1]

        qs = Customer.objects.filter(is_staff=False).annotate(
            calculated_expiry=Coalesce(
                Subquery(active_subscription.values('expiry_date')[:1]),
                Subquery(latest_subscription.values('expiry_date')[:1]),
            ),
            current_plan_name=Coalesce(
                Subquery(active_subscription.values('plan__name')[:1]),
                Subquery(latest_subscription.values('plan__name')[:1]),
            ),
            current_plan_status=Coalesce(
                Subquery(active_subscription.values('status')[:1]),
                Subquery(latest_subscription.values('status')[:1]),
            ),
            current_plan_id=Coalesce(
                Subquery(active_subscription.values('plan_id')[:1]),
                Subquery(latest_subscription.values('plan_id')[:1]),
            ),
            current_plan_price=Coalesce(
                Subquery(active_subscription.values('plan__price')[:1]),
                Subquery(latest_subscription.values('plan__price')[:1]),
            ),
            latest_subscription_at=Coalesce(
                Subquery(latest_subscription.values('created_at')[:1]), 'created_at'
            ),
            router_name=Coalesce(
                'pppoe_secret__router__name', 'hotspot_user__router__name',
                output_field=CharField()
            ),
            last_ip=Subquery(latest_usage),
        )

        params = self.request.query_params
        service_type = params.get('service_type')
        if service_type:
            qs = qs.filter(service_type=service_type)

        router_param = params.get('router')
        if router_param:
            qs = qs.filter(
                Q(pppoe_secret__router_id=router_param) | Q(hotspot_user__router_id=router_param)
            )

        plan_param = params.get('plan')
        if plan_param:
            qs = qs.filter(current_plan_id=plan_param)

        # summary() counts every tab from this same base queryset, so the
        # tab-selecting filters (status / expiring / new) are applied after.
        if self.action == 'summary':
            return qs
        return self._apply_tab(qs, params)

    @staticmethod
    def _expiring_q():
        from django.db.models import Q
        from django.utils import timezone
        now = timezone.now()
        # "Expiring" = active and running out within the next 7 days.
        return Q(status='active', calculated_expiry__gt=now, calculated_expiry__lte=now + timezone.timedelta(days=7))

    def _apply_tab(self, qs, params):
        from django.utils import timezone
        status_param = params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        if params.get('expiring') == 'true':
            qs = qs.filter(self._expiring_q())
        if params.get('is_new') == 'true':
            qs = qs.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7))
        return qs

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Counts for the Subscribers page's tabs (All / Active / Expiring /
        Expired / Suspended / New), honouring the same search, router,
        plan and service-type filters as the list.
        """
        from django.db.models import Count, Q
        from django.utils import timezone
        qs = self.filter_queryset(self.get_queryset())
        counts = qs.aggregate(
            all=Count('id', distinct=True),
            active=Count('id', filter=Q(status='active'), distinct=True),
            expiring=Count('id', filter=self._expiring_q(), distinct=True),
            expired=Count('id', filter=Q(status='expired'), distinct=True),
            suspended=Count('id', filter=Q(status='suspended'), distinct=True),
            new=Count('id', filter=Q(created_at__gte=timezone.now() - timezone.timedelta(days=7)), distinct=True),
        )
        return Response(counts)

    @action(detail=False, methods=['post'], url_path='bulk-stk-reminder')
    def bulk_stk_reminder(self, request):
        """
        Send each selected subscriber an M-Pesa STK prompt for their current
        (or most recent) plan, to their phone number on file. Uses the same
        PaymentRequest flow as self-service checkout, so paying the prompt
        renews them through the normal callback. Admin only (it sends real
        payment prompts); capped per call because each prompt is a live
        Daraja request.
        """
        from apps.billing.models import BillingPlan
        from apps.payments.views import start_stk_push

        if not (request.user.is_superuser or request.user.role == 'admin'):
            return Response({'error': 'Only admins can send payment prompts.'}, status=status.HTTP_403_FORBIDDEN)

        ids = request.data.get('ids') or []
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'Select at least one subscriber.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > self.BULK_STK_LIMIT:
            return Response(
                {'error': f'Send at most {self.BULK_STK_LIMIT} prompts at a time.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sent, failed = [], []
        for customer in self.get_queryset().filter(id__in=ids):
            name = customer.get_full_name() or customer.username
            plan = BillingPlan.objects.filter(id=customer.current_plan_id).first() if customer.current_plan_id else None
            if not plan:
                failed.append(f'{name}: no plan to renew')
                continue
            if plan.service_type == 'static':
                failed.append(f'{name}: static plans are renewed by staff, not STK')
                continue
            if not customer.phone_number:
                failed.append(f'{name}: no phone number on file')
                continue
            _, result = start_stk_push(customer, plan, customer.phone_number)
            if result.get('success'):
                sent.append(f'{name}: KES {plan.price} prompt sent')
            else:
                failed.append(f"{name}: {result.get('error') or 'M-Pesa rejected the request'}")
        return Response({'success': sent, 'failed': failed})

    BULK_STK_LIMIT = 25

    @action(detail=True, methods=['get'])
    def usage(self, request, pk=None):
        """
        Usage records, subscriptions and transactions for one subscriber,
        for the admin subscriber-detail view.
        """
        from apps.billing.models import UsageRecord, Subscription, Transaction
        from apps.billing.serializers import (
            UsageRecordSerializer, SubscriptionSerializer, TransactionSerializer
        )
        from apps.billing.usage_stats import build_usage_chart, usage_summary
        from django.db.models import Sum

        customer = self.get_object()

        customer_records = UsageRecord.objects.filter(customer=customer)
        usage_records = customer_records.order_by('-created_at')[:60]
        summary = usage_summary(customer)

        return Response({
            'plan_totals': summary['plan_totals'],
            'totals': summary['totals'],
            'chart': build_usage_chart(customer_records),
            'usage_records': UsageRecordSerializer(usage_records, many=True).data,
            'subscriptions': SubscriptionSerializer(
                Subscription.objects.filter(customer=customer).order_by('-created_at')[:20], many=True
            ).data,
            'transactions': TransactionSerializer(
                Transaction.objects.filter(customer=customer).order_by('-created_at')[:20], many=True
            ).data,
        })

    @action(detail=True, methods=['post'])
    def topup(self, request, pk=None):
        """
        Manually assign/renew/switch a plan for this subscriber, paid for
        by a fresh manual cash transaction right now: reuses/extends the
        customer's existing active subscription for this service_type
        rather than creating a second concurrently-active one (see
        apps.billing.services.apply_subscription) -- if this is a switch
        to a different plan than they're currently on, the unused value of
        the old one is credited to account_balance, not lost.
        """
        import random
        import string
        from apps.billing.models import BillingPlan, Transaction
        from apps.billing.services import apply_subscription

        denied = _deny_technician(request)
        if denied:
            return denied

        customer = self.get_object()
        plan_id = request.data.get('plan_id')

        try:
            plan = BillingPlan.objects.get(id=plan_id)
        except (BillingPlan.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)

        if plan.service_type == 'static' and not customer.static_ip_address:
            static_ip = (request.data.get('static_ip_address') or '').strip()
            if not static_ip:
                return Response(
                    {'error': 'static_ip_address is required to assign a Static IP plan to this customer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            customer.static_ip_address = static_ip
            customer.service_type = 'static'
            customer.save(update_fields=['static_ip_address', 'service_type'])

        try:
            subscription, credited = apply_subscription(customer, plan)
        except Exception as e:
            return Response(
                {'error': f'Plan assigned locally failed to activate on the router: {e}'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        Transaction.objects.create(
            customer=customer,
            subscription=subscription,
            transaction_id='TOPUP-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=plan.price,
            payment_method='cash',
            status='completed',
            notes=(
                f"Manual top-up by {request.user.username}"
                + (f" (KES {credited} credited to balance from previous plan)" if credited else "")
            )
        )

        expires = timezone.localtime(subscription.expiry_date).strftime('%d %b %Y %H:%M')
        _notify_change(
            staff_message=(
                f"{request.user.username} recharged {customer.get_full_name() or customer.username} "
                f"({customer.username}) on {plan.name}, KES {plan.price} cash. Expires {expires}."
            ),
            customer_message=f"Payment of KES {plan.price} received. Your {plan.name} plan is active until {expires}.",
            event_type='payment_confirmation', customer=customer, subscription=subscription,
        )

        message = f'{plan.name} assigned to {customer.username}'
        if credited:
            message += f' (KES {credited} credited to their balance from the previous plan)'

        return Response({
            'success': True,
            'message': message,
            'subscription': self.get_serializer(customer).data,
        })

    @action(detail=True, methods=['post'], url_path='pppoe-credentials')
    def pppoe_credentials(self, request, pk=None):
        """
        Superuser-only: change this customer's PPPoE username/password and
        push it to their router (see update_pppoe_credentials). Doesn't
        touch the portal login password, which is a separate one-way hash.
        """
        import re
        from apps.network.models import PPPoESecret
        from apps.network.services.network_automation import network_automation

        if not request.user.is_superuser:
            return Response({'error': 'Only a super admin can change PPPoE credentials.'}, status=status.HTTP_403_FORBIDDEN)

        customer = self.get_object()
        username = (request.data.get('pppoe_username') or '').strip()
        password = (request.data.get('pppoe_password') or '').strip()

        if not re.fullmatch(r'[A-Za-z0-9._@-]{1,64}', username):
            return Response({'error': 'Username must be 1-64 characters: letters, digits, . _ @ -'}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 3 or re.search(r'\s', password):
            return Response({'error': 'Password must be at least 3 characters, with no spaces.'}, status=status.HTTP_400_BAD_REQUEST)
        if (Customer.objects.exclude(pk=customer.pk).filter(pppoe_username=username).exists()
                or PPPoESecret.objects.exclude(customer=customer).filter(username=username).exists()):
            return Response({'error': f'PPPoE username "{username}" is already used by another customer.'}, status=status.HTTP_400_BAD_REQUEST)

        result = network_automation.update_pppoe_credentials(customer, username, password)
        return Response({
            'saved': True,
            'router_synced': result['synced'] and result['success'],
            'router_error': None if result['success'] else result.get('error'),
            'subscriber': self.get_serializer(customer).data,
        })

    @action(detail=True, methods=['post'])
    def add_balance(self, request, pk=None):
        """
        Manually credit KES to this customer's account_balance -- e.g. cash
        received that isn't tied to a specific plan right now. Recorded as
        an unlinked completed Transaction (no subscription) for audit.
        """
        import random
        import string
        from decimal import Decimal, InvalidOperation
        from apps.billing.models import Transaction

        denied = _deny_technician(request)
        if denied:
            return denied

        customer = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount')))
        except (InvalidOperation, TypeError):
            return Response({'error': 'A valid amount is required'}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)

        customer.account_balance += amount
        customer.save(update_fields=['account_balance'])

        Transaction.objects.create(
            customer=customer,
            transaction_id='BAL-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=amount,
            payment_method='cash',
            status='completed',
            notes=f"Manual balance top-up by {request.user.username}",
        )
        _notify_change(
            staff_message=(
                f"{request.user.username} added KES {amount} cash to "
                f"{customer.get_full_name() or customer.username} ({customer.username}). "
                f"New balance KES {customer.account_balance}."
            ),
            customer_message=f"KES {amount} has been added to your account. Your balance is now KES {customer.account_balance}.",
            event_type='balance_credit', customer=customer,
        )

        return Response({
            'success': True,
            'message': f'KES {amount} added to {customer.username}\'s balance',
            'account_balance': customer.account_balance,
        })

    @action(detail=True, methods=['post'])
    def extend(self, request, pk=None):
        """
        Superadmin only: move this subscriber's latest subscription to end
        at `expiry_date` (ISO date or datetime; a bare date means the end of
        that day, and a naive time is read in Africa/Nairobi). If it had
        expired, it's reactivated: saving it as active with a future expiry
        makes the subscription signal re-enable the customer on the router
        and mark them active again. No payment is recorded -- this is a
        correction/goodwill tool -- and the staff alert number is told.
        """
        from datetime import datetime, time as dtime
        from apps.billing.models import Subscription

        if not request.user.is_superuser:
            return Response({'error': 'Only the superadmin can extend a subscription to a date.'},
                            status=status.HTTP_403_FORBIDDEN)

        customer = self.get_object()
        raw = str(request.data.get('expiry_date') or '').strip()
        try:
            if len(raw) == 10:  # YYYY-MM-DD -> end of that day
                parsed = datetime.combine(datetime.fromisoformat(raw).date(), dtime(23, 59))
            else:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except ValueError:
            return Response({'error': 'expiry_date must be a date like 2026-12-31 (optionally with a time).'},
                            status=status.HTTP_400_BAD_REQUEST)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)  # TIME_ZONE = Africa/Nairobi
        if parsed <= timezone.now():
            return Response({'error': 'The new expiry must be in the future.'}, status=status.HTTP_400_BAD_REQUEST)

        subscription = Subscription.objects.filter(customer=customer).select_related('plan').order_by('-created_at').first()
        if not subscription:
            return Response({'error': 'This subscriber has never had a plan. Assign one with Recharge first.'},
                            status=status.HTTP_400_BAD_REQUEST)

        was = subscription.status
        old_expiry = subscription.expiry_date
        subscription.expiry_date = parsed
        subscription.status = 'active'
        try:
            subscription.save()
        except Exception as e:
            return Response({'error': f'Could not activate on the router: {e}'},
                            status=status.HTTP_502_BAD_GATEWAY)

        new_local = timezone.localtime(parsed).strftime('%d %b %Y %H:%M')
        _notify_change(
            staff_message=(
                f"{request.user.username} extended {customer.get_full_name() or customer.username} "
                f"({customer.username}) {subscription.plan.name} to {new_local}"
                + (f" (reactivated, was {was})" if was != 'active' else '')
                + f". Previous expiry {timezone.localtime(old_expiry).strftime('%d %b %Y %H:%M')}."
            ),
            customer_message=(
                f"Your {subscription.plan.name} plan has been "
                + ("reactivated" if was != 'active' else "extended")
                + f" and is active until {new_local}."
            ),
            event_type='subscription_extended', customer=customer, subscription=subscription,
        )
        return Response({
            'success': True,
            'reactivated': was != 'active',
            'message': f"{subscription.plan.name} now runs until {new_local}"
                       + (' and has been reactivated.' if was != 'active' else '.'),
        })

    @action(detail=True, methods=['post'])
    def switch_plan(self, request, pk=None):
        """
        Assign/renew/switch this customer's subscription, paid entirely out
        of their existing account_balance rather than a fresh payment --
        see apps.billing.services.purchase_plan_from_balance.
        """
        import random
        import string
        from apps.billing.models import BillingPlan, Transaction
        from apps.billing.services import purchase_plan_from_balance, InsufficientBalance

        # Paying from balance renews the subscription too, so it's an
        # extension in all but name.
        denied = _deny_technician(request)
        if denied:
            return denied

        customer = self.get_object()
        try:
            plan = BillingPlan.objects.get(id=request.data.get('plan_id'), is_active=True)
        except (BillingPlan.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Invalid plan ID'}, status=status.HTTP_400_BAD_REQUEST)

        if plan.service_type == 'static':
            return Response(
                {'error': 'Static IP plans must be assigned by a technician, not switched here'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subscription, credited = purchase_plan_from_balance(customer, plan)
        except InsufficientBalance as e:
            return Response({
                'error': f"Insufficient balance: KES {e.available} available, KES {e.required} required for {plan.name}."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Plan switch failed to activate on the router: {e}'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        Transaction.objects.create(
            customer=customer,
            subscription=subscription,
            transaction_id='SWITCH-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
            amount=plan.price,
            payment_method='balance',
            status='completed',
            notes=(
                f"Plan switch to {plan.name} by {request.user.username}"
                + (f" (KES {credited} credited from previous plan)" if credited else "")
            ),
        )

        return Response({
            'success': True,
            'message': f'{customer.username} switched to {plan.name}',
            'account_balance': customer.account_balance,
        })
