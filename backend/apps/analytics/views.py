from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import timedelta
import datetime as dt
import csv
from django.http import HttpResponse

from apps.billing.models import Transaction, Subscription, UsageRecord, BillingPlan, Voucher
from apps.customers.models import Customer
from apps.network.models import Router, ActiveSession, PPPoESecret, HotspotUser
from apps.customers.permissions import RoleAllowed
from apps.payments.models import C2BPayment
from apps.payments.services.payer_name import payer_display_name
from apps.analytics.utils import report_window


def mask_msisdn(value):
    """
    '254722618418' / '0722618418' -> '0722 ••• 418' for admin lists. A C2B
    payer may only have Safaricom's SHA-256 hash, which isn't a number at
    all -- that (or anything else unparseable) masks to ''.
    """
    raw = (value or '').strip().replace(' ', '').replace('-', '').lstrip('+')
    if not raw.isdigit():
        return ''  # e.g. a hex hash -- picking its digits out would invent a number
    digits = raw
    if len(digits) == 12 and digits.startswith('254'):
        digits = '0' + digits[3:]
    if len(digits) != 10:
        return ''
    return f'{digits[:4]} ••• {digits[-3:]}'


def _last_transactions(limit=6):
    """
    Latest completed payments for the dashboard's live Payments feed.
    Phone numbers are masked here, not in the browser, so the admin list
    never receives the full number.
    """
    return [
        {
            'username': t.customer.username,
            'name': t.customer.get_full_name() or t.customer.username,
            'amount': float(t.amount),
            'date': t.created_at,
            'method': t.payment_method,
            'receipt': t.mpesa_receipt_number or '',
            'phone': mask_msisdn(t.mpesa_phone_number or t.customer.phone_number),
            'service_type': t.customer.service_type,
            'plan': t.subscription.plan.name if t.subscription_id and t.subscription.plan_id else '',
        }
        for t in Transaction.objects.filter(status='completed').select_related(
            'customer', 'subscription__plan'
        ).order_by('-created_at')[:limit]
    ]


GATEWAY_FAILED_KEY = 'dashboard:mpesa_gateway_failed'
GATEWAY_CHECKING_KEY = 'dashboard:mpesa_gateway_checking'


def _check_gateway():
    from django.core.cache import cache
    from apps.payments.services.mpesa_service import mpesa_service
    try:
        if not mpesa_service.get_access_token():
            # Remember the failure for a while so every dashboard load
            # doesn't start another 30s attempt against an unreachable API.
            cache.set(GATEWAY_FAILED_KEY, True, 120)
    finally:
        cache.delete(GATEWAY_CHECKING_KEY)


def _gateway_status():
    """True/False when known, None while a background check is running."""
    import threading
    from django.core.cache import cache
    if cache.get('mpesa_access_token'):
        return True
    if cache.get(GATEWAY_FAILED_KEY):
        return False
    # add() only succeeds for the first caller, so concurrent loads start
    # one check between them; the 60s expiry covers a thread that dies.
    if cache.add(GATEWAY_CHECKING_KEY, True, 60):
        threading.Thread(target=_check_gateway, daemon=True).start()
    return None


def can_see_income(user):
    """Technicians manage the network, not the books -- keep revenue
    figures out of their API responses entirely, not just hidden in the UI."""
    return user.is_superuser or user.role != 'technician'


class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Active Subscribers
        active_subs = Subscription.objects.filter(status='active', expiry_date__gt=now).count()
        expired_subs = Subscription.objects.filter(status='expired').count()

        # Revenue today / this month
        revenue_today = Transaction.objects.filter(
            status='completed', created_at__gte=start_of_today
        ).aggregate(total=Sum('amount'))['total'] or 0
        revenue_month = Transaction.objects.filter(
            status='completed',
            created_at__gte=start_of_month
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Usage this Month (GB)
        usage_bytes = UsageRecord.objects.filter(
            start_time__gte=start_of_month
        ).aggregate(
            total_up=Sum('upload_bytes'),
            total_down=Sum('download_bytes')
        )
        total_bytes = (usage_bytes['total_up'] or 0) + (usage_bytes['total_down'] or 0)
        usage_gb = round(total_bytes / (1024**3), 2)

        # New Customers
        new_customers = Customer.objects.filter(created_at__gte=start_of_month).count()
        new_this_week = Customer.objects.filter(created_at__gte=now - timedelta(days=7)).count()
        total_customers = Customer.objects.count()

        # Rolling 30-day collections vs the 30 days before, for the
        # dashboard's revenue KPI and its % change.
        completed = Transaction.objects.filter(status='completed')
        revenue_30d = completed.filter(created_at__gte=now - timedelta(days=30)).aggregate(
            total=Sum('amount'), n=Count('id'))
        revenue_prev_30d = completed.filter(
            created_at__gte=now - timedelta(days=60), created_at__lt=now - timedelta(days=30)
        ).aggregate(total=Sum('amount'))['total'] or 0
        avg_ticket_30d = (
            float(revenue_30d['total']) / revenue_30d['n'] if revenue_30d['n'] else 0
        )

        # STK push success rate over 30 days: of the prompts that reached a
        # final state, how many were paid. Still-open prompts are left out so
        # a burst of in-flight requests doesn't read as failures.
        from apps.payments.models import PaymentRequest
        stk = PaymentRequest.objects.filter(created_at__gte=now - timedelta(days=30)).aggregate(
            done=Count('id', filter=Q(status='completed')),
            final=Count('id', filter=Q(status__in=['completed', 'failed', 'timeout', 'cancelled'])),
        )
        stk_success_rate = round(stk['done'] / stk['final'] * 100, 1) if stk['final'] else None

        # Live online counts (kept fresh by the collect_usage_statistics
        # celery task, not queried live from routers on every page load)
        hotspot_online = ActiveSession.objects.filter(session_type='hotspot').count()
        pppoe_online = ActiveSession.objects.filter(session_type='pppoe').count()
        static_online = ActiveSession.objects.filter(session_type='static').count()

        # Per-router summary for the Router View panel
        routers = []
        for router in Router.objects.filter(is_active=True):
            routers.append({
                'id': router.id,
                'name': router.name,
                'online': ActiveSession.objects.filter(router=router).count(),
                'valid': (
                    PPPoESecret.objects.filter(router=router, status='enabled').count() +
                    HotspotUser.objects.filter(router=router, status='enabled').count()
                ),
                'invalid': (
                    PPPoESecret.objects.filter(router=router, status='disabled').count() +
                    HotspotUser.objects.filter(router=router, status='disabled').count()
                ),
                # Last known state (see apps.network.services.router_status),
                # so the Sites card renders before the live health poll lands.
                'is_online': router.is_online,
                'last_seen_at': router.last_seen_at,
                'board_name': (router.last_health or {}).get('board_name'),
            })

        show_income = can_see_income(request.user)

        return Response({
            'active_subscribers': active_subs,
            'expired_subscribers': expired_subs,
            'income_today': revenue_today if show_income else None,
            'monthly_revenue': revenue_month if show_income else None,
            'monthly_usage_gb': usage_gb,
            'new_customers': new_customers,
            'new_this_week': new_this_week,
            'total_customers': total_customers,
            'revenue_30d': float(revenue_30d['total'] or 0) if show_income else None,
            'revenue_prev_30d': float(revenue_prev_30d) if show_income else None,
            'avg_ticket_30d': round(avg_ticket_30d, 2) if show_income else None,
            'stk_success_rate': stk_success_rate if show_income else None,
            'hotspot_online': hotspot_online,
            'pppoe_online': pppoe_online,
            'static_online': static_online,
            'total_online': hotspot_online + pppoe_online + static_online,
            'routers': routers,
        })

class IncomeReportView(APIView):
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        export = request.query_params.get('export') == 'csv'
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        now = timezone.now()
        end_date = now
        start_date = now - timedelta(days=30)
        
        if start_date_str:
            try:
                parsed = timezone.datetime.fromisoformat(start_date_str)
                start_date = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
                start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            except: pass
        if end_date_str:
            try:
                parsed = timezone.datetime.fromisoformat(end_date_str)
                end_date = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
                # A date-only string parses to midnight -- as a range's upper
                # bound that excludes the entire day it names, since almost
                # every transaction happens after 00:00. Push it to the last
                # instant of that day instead.
                end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            except: pass
            
        # Daily Revenue Aggregation
        daily_revenue = Transaction.objects.filter(
            status='completed',
            created_at__range=(start_date, end_date)
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('date')
        
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="income_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Date', 'Transactions', 'Revenue'])
            for entry in daily_revenue:
                writer.writerow([entry['date'], entry['count'], entry['total']])
            return response
            
        return Response(daily_revenue)

class UsageReportView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        # Top users by usage (past 30 days)
        limit = int(request.query_params.get('limit', 10))
        start_date = timezone.now() - timedelta(days=30)
        
        top_users = UsageRecord.objects.filter(
            start_time__gte=start_date
        ).values(
            'customer__username', 'customer__first_name', 'customer__last_name'
        ).annotate(
            total_up=Sum('upload_bytes'),
            total_down=Sum('download_bytes')
        ).annotate(
            total_bytes=F('total_up') + F('total_down')
        ).order_by('-total_bytes')[:limit]
        
        data = []
        for user in top_users:
            full_name = f"{user['customer__first_name']} {user['customer__last_name']}".strip() or user['customer__username']
            data.append({
                'username': user['customer__username'],
                'name': full_name,
                'upload_gb': round((user['total_up'] or 0) / (1024**3), 2),
                'download_gb': round((user['total_down'] or 0) / (1024**3), 2),
                'total_gb': round((user['total_bytes'] or 0) / (1024**3), 2)
            })

        return Response(data)


class VoucherUsageReportView(APIView):
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        search = request.query_params.get('search', '').strip()
        export = request.query_params.get('export') == 'csv'

        try:
            page = max(int(request.query_params.get('page', 1)), 1)
            page_size = min(max(int(request.query_params.get('page_size', 25)), 1), 200)
            if start_date:
                start_date = dt.date.fromisoformat(start_date)
            if end_date:
                end_date = dt.date.fromisoformat(end_date)
        except (TypeError, ValueError):
            return Response(
                {'error': 'page, page_size, start_date, or end_date is invalid'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vouchers = Voucher.objects.filter(
            status='used', used_at__isnull=False
        ).select_related('used_by', 'plan', 'batch')
        if start_date:
            vouchers = vouchers.filter(used_at__date__gte=start_date)
        if end_date:
            vouchers = vouchers.filter(used_at__date__lte=end_date)
        if search:
            vouchers = vouchers.filter(
                Q(code__icontains=search)
                | Q(used_mac__icontains=search)
                | Q(used_by__username__icontains=search)
                | Q(used_by__first_name__icontains=search)
                | Q(used_by__last_name__icontains=search)
                | Q(plan__name__icontains=search)
            )
        vouchers = vouchers.order_by('-used_at', '-id')

        def serialize_voucher(voucher):
            customer = voucher.used_by
            customer_name = ''
            if customer:
                customer_name = customer.full_name
            return {
                'id': voucher.id,
                'voucher_code': voucher.code,
                'mac_address': voucher.used_mac or '',
                'customer_username': customer.username if customer else '',
                'customer_name': customer_name,
                'plan_name': voucher.plan.name if voucher.plan else '',
                'amount': str(voucher.amount) if voucher.amount is not None else '',
                'used_at': voucher.used_at,
            }

        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="voucher_usage_report.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Voucher Code', 'MAC Address', 'Customer Username', 'Customer Name',
                'Plan', 'Amount', 'Redeemed At',
            ])
            for voucher in vouchers.iterator():
                row = serialize_voucher(voucher)
                writer.writerow([
                    row['voucher_code'], row['mac_address'], row['customer_username'],
                    row['customer_name'], row['plan_name'], row['amount'], row['used_at'],
                ])
            return response

        total = vouchers.count()
        offset = (page - 1) * page_size
        results = [serialize_voucher(voucher) for voucher in vouchers[offset:offset + page_size]]
        return Response({
            'results': results,
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max((total + page_size - 1) // page_size, 1),
        })


class UsageChartView(APIView):
    """
    Network-wide today / this-week / this-year-by-month data usage, for the
    "General Data Usage" panel on the admin dashboard.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        from apps.billing.usage_stats import build_usage_chart
        return Response(build_usage_chart(UsageRecord.objects.all()))


class DashboardExtraView(APIView):
    """
    Secondary dashboard panels: monthly registration/sales trends, best
    selling packages, user composition, payment gateway status, per-router
    transaction breakdown, recent transactions, and voucher stock. Split
    from DashboardStatsView so the fast core stats aren't held up by these
    heavier aggregations (this view hits the M-Pesa API for a live gateway
    check, and does a per-customer router lookup).
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        # The dashboard polls just the payments feed every 15s; skip the
        # heavy aggregations below (the per-router loop walks every
        # transaction) for that.
        if request.query_params.get('section') == 'payments':
            return Response({
                'last_transactions': _last_transactions() if can_see_income(request.user) else [],
            })

        today = timezone.now().date()
        year_start = today.replace(month=1, day=1)
        start_of_month = today.replace(day=1)
        show_income = can_see_income(request.user)

        # Monthly registered customers (Jan-Dec this year)
        reg_rows = Customer.objects.filter(created_at__date__gte=year_start).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(count=Count('id'))
        reg_map = {r['month'].month: r['count'] for r in reg_rows}
        monthly_registrations = [
            {'month': dt.date(today.year, m, 1).strftime('%b'), 'count': reg_map.get(m, 0)}
            for m in range(1, 13)
        ]

        # Monthly sales, best-selling packages, per-router and recent
        # transaction amounts are all revenue figures -- skip computing them
        # entirely (not just hiding in the UI) for roles that shouldn't see
        # income.
        monthly_sales = []
        best_selling = []
        if show_income:
            sales_rows = Transaction.objects.filter(
                status='completed', created_at__date__gte=year_start
            ).annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('amount'))
            sales_map = {r['month'].month: float(r['total'] or 0) for r in sales_rows}
            monthly_sales = [
                {'month': dt.date(today.year, m, 1).strftime('%b'), 'total': sales_map.get(m, 0)}
                for m in range(1, 13)
            ]

            plan_sales = Subscription.objects.filter(
                created_at__date__gte=start_of_month, plan__isnull=False
            ).values('plan__id', 'plan__name', 'plan__price').annotate(sales=Count('id')).order_by('-sales')[:10]
            best_selling = [
                {
                    'name': p['plan__name'],
                    'price': float(p['plan__price'] or 0),
                    'sales': p['sales'],
                    'revenue': float((p['plan__price'] or 0) * p['sales']),
                }
                for p in plan_sales
            ]

        # All users insights (active / expired / everything else)
        active_count = Customer.objects.filter(status='active').count()
        expired_count = Customer.objects.filter(status='expired').count()
        inactive_count = Customer.objects.exclude(status__in=['active', 'expired']).count()

        # Users by service type
        service_counts = Customer.objects.values('service_type').annotate(count=Count('id'))
        total_customers = Customer.objects.count() or 1
        users_by_service = [
            {
                'service_type': s['service_type'],
                'count': s['count'],
                'percentage': round(s['count'] / total_customers * 100, 1),
            }
            for s in service_counts
        ]

        # Payment gateway status -- a real connectivity check (can we get a
        # Daraja token?), but never made inside this request: a token fetch
        # can take up to 30s (after every restart, hourly on expiry, and on
        # every load while Safaricom is unreachable), and the dashboard sat
        # on "Loading..." meanwhile. A cached token means connected; else
        # the check runs in a background thread and this load reports
        # connected=None ("checking") -- the next load has the answer.
        from django.conf import settings as dj_settings
        payment_gateway = {
            'name': 'M-Pesa STK Push',
            'environment': dj_settings.MPESA_ENVIRONMENT,
            'shortcode': dj_settings.MPESA_SHORTCODE,
            'connected': _gateway_status(),
        }

        # Transactions per router, via each customer's PPPoE/Hotspot router
        transactions_per_router = []
        last_transactions = []
        if show_income:
            router_customer_map = {}
            for row in PPPoESecret.objects.values('customer_id', 'router__name'):
                router_customer_map[row['customer_id']] = row['router__name']
            for row in HotspotUser.objects.values('customer_id', 'router__name'):
                router_customer_map.setdefault(row['customer_id'], row['router__name'])

            router_totals = {}
            total_txn_count = 0
            for t in Transaction.objects.filter(status='completed').values('customer_id', 'amount'):
                router_name = router_customer_map.get(t['customer_id'], 'Unassigned')
                bucket = router_totals.setdefault(router_name, {'transactions': 0, 'amount': 0.0})
                bucket['transactions'] += 1
                bucket['amount'] += float(t['amount'])
                total_txn_count += 1
            transactions_per_router = [
                {
                    'router': name,
                    'transactions': data['transactions'],
                    'percentage': round(data['transactions'] / total_txn_count * 100, 2) if total_txn_count else 0,
                    'amount': round(data['amount'], 2),
                }
                for name, data in sorted(router_totals.items(), key=lambda kv: -kv[1]['transactions'])
            ]

            last_transactions = _last_transactions()

        # Voucher stock per plan
        voucher_rows = Voucher.objects.values('plan__name').annotate(
            unused=Count('id', filter=Q(status='active')),
            used=Count('id', filter=Q(status='used')),
        )
        voucher_stock = [
            {'plan_name': v['plan__name'] or 'Unassigned', 'unused': v['unused'], 'used': v['used']}
            for v in voucher_rows
        ]

        return Response({
            'monthly_registrations': monthly_registrations,
            'monthly_sales': monthly_sales,
            'best_selling_packages': best_selling,
            'user_insights': {'active': active_count, 'expired': expired_count, 'inactive': inactive_count},
            'users_by_service_type': users_by_service,
            'payment_gateway': payment_gateway,
            'transactions_per_router': transactions_per_router,
            'last_transactions': last_transactions,
            'voucher_stock': voucher_stock,
        })


class ExpiringTodayView(APIView):
    """Paginated list of subscriptions expiring today, for the admin dashboard."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        today = timezone.now().date()
        page = max(int(request.query_params.get('page', 1) or 1), 1)
        page_size = min(int(request.query_params.get('page_size', 10) or 10), 100)

        qs = Subscription.objects.filter(
            expiry_date__date=today
        ).select_related('customer').order_by('expiry_date')

        total = qs.count()
        start = (page - 1) * page_size
        rows = qs[start:start + page_size]

        return Response({
            'results': [
                {'username': s.customer.username, 'created_on': s.start_date, 'expires_on': s.expiry_date}
                for s in rows
            ],
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max((total + page_size - 1) // page_size, 1),
        })


class RecentActivityView(APIView):
    """Recent successful logins, for the admin dashboard's activity feed."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        from apps.customers.models import LoginActivity
        limit = min(int(request.query_params.get('limit', 15) or 15), 50)
        activities = LoginActivity.objects.select_related('customer').order_by('-created_at')[:limit]
        return Response([
            {
                'username': a.customer.username,
                'message': f"{a.customer.username} Login Successful",
                'created_at': a.created_at,
            }
            for a in activities
        ])


class DataUsageView(APIView):
    """
    Per-user data usage for a Daily/Weekly/Monthly window, with search,
    router, and service-type filters, several sort orders, and CSV export.
    Backs the admin Data Usage page.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        period = request.query_params.get('period', 'daily')
        date_str = request.query_params.get('date')
        search = request.query_params.get('search', '').strip()
        router_id = request.query_params.get('router')
        service_type = request.query_params.get('type')
        sort = request.query_params.get('sort', 'highest')
        limit = min(int(request.query_params.get('limit', 50) or 50), 200)
        export = request.query_params.get('export') == 'csv'

        try:
            ref_date = dt.date.fromisoformat(date_str) if date_str else timezone.now().date()
        except ValueError:
            ref_date = timezone.now().date()

        start, end, prev_start, prev_end = report_window(period, ref_date)

        qs = UsageRecord.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
        if search:
            qs = qs.filter(customer__username__icontains=search)
        if service_type:
            qs = qs.filter(customer__service_type=service_type)
        if router_id:
            customer_ids = set(PPPoESecret.objects.filter(router_id=router_id).values_list('customer_id', flat=True))
            customer_ids |= set(HotspotUser.objects.filter(router_id=router_id).values_list('customer_id', flat=True))
            qs = qs.filter(customer_id__in=customer_ids)

        per_user = qs.values(
            'customer__username', 'customer__first_name', 'customer__last_name'
        ).annotate(upload=Sum('upload_bytes'), download=Sum('download_bytes'))

        results = []
        for u in per_user:
            upload_gb = round((u['upload'] or 0) / (1024 ** 3), 2)
            download_gb = round((u['download'] or 0) / (1024 ** 3), 2)
            name = f"{u['customer__first_name']} {u['customer__last_name']}".strip() or u['customer__username']
            results.append({
                'username': u['customer__username'],
                'name': name,
                'upload_gb': upload_gb,
                'download_gb': download_gb,
                'total_gb': round(upload_gb + download_gb, 2),
            })

        sort_keys = {
            'highest': lambda r: -r['total_gb'],
            'lowest': lambda r: r['total_gb'],
            'downloaders': lambda r: -r['download_gb'],
            'uploaders': lambda r: -r['upload_gb'],
            'username': lambda r: r['username'].lower(),
        }
        results.sort(key=sort_keys.get(sort, sort_keys['highest']))
        results = results[:limit]

        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="data_usage_{period}_{start}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Username', 'Name', 'Upload (GB)', 'Download (GB)', 'Total (GB)'])
            for r in results:
                writer.writerow([r['username'], r['name'], r['upload_gb'], r['download_gb'], r['total_gb']])
            return response

        totals_agg = qs.aggregate(up=Sum('upload_bytes'), down=Sum('download_bytes'))
        total_up = round((totals_agg['up'] or 0) / (1024 ** 3), 2)
        total_down = round((totals_agg['down'] or 0) / (1024 ** 3), 2)
        active_users = qs.values('customer_id').distinct().count()

        prev_agg = UsageRecord.objects.filter(
            created_at__date__gte=prev_start, created_at__date__lte=prev_end
        ).aggregate(up=Sum('upload_bytes'), down=Sum('download_bytes'))
        prev_total_bytes = (prev_agg['up'] or 0) + (prev_agg['down'] or 0)
        current_total_bytes = (totals_agg['up'] or 0) + (totals_agg['down'] or 0)
        vs_previous_pct = (
            round((current_total_bytes - prev_total_bytes) / prev_total_bytes * 100, 1)
            if prev_total_bytes else None
        )

        return Response({
            'period': period,
            'start': start,
            'end': end,
            'totals': {
                'upload_gb': total_up,
                'download_gb': total_down,
                'total_gb': round(total_up + total_down, 2),
                'active_users': active_users,
                'avg_per_user_gb': round((total_up + total_down) / active_users, 2) if active_users else 0,
                'vs_previous_pct': vs_previous_pct,
                'previous_total_gb': round(prev_total_bytes / (1024 ** 3), 2),
            },
            'top_users': results[:10],
            'users': results,
        })


class RecentPaymentsView(APIView):
    """
    Unified feed of M-Pesa payments -- STK push (Transaction) and direct
    C2B till payments (C2BPayment) -- for the admin Payments page. Admin
    only, not the usual admin/sales income split: this exposes raw payer
    data (including unmatched payers' phone hashes), not just totals.
    """
    permission_classes = [RoleAllowed('admin')]

    def get(self, request):
        page = max(int(request.query_params.get('page', 1) or 1), 1)
        page_size = min(int(request.query_params.get('page_size', 20) or 20), 100)

        # Transaction and C2BPayment are separate tables, so they can't be
        # ordered together in one query -- pull enough of each (already
        # ordered, most recent first) to cover every row up to this page,
        # merge, then paginate in Python. `count` below is a real DB count
        # so page numbers stay accurate; only the row *content* on very deep
        # pages beyond fetch_limit could be incomplete. Fine at this
        # project's payment volume -- would need a real DB-side UNION if
        # that ever changes.
        fetch_limit = min(page * page_size, 1000)

        # A matched C2B payment also produces a Transaction carrying the same
        # M-Pesa code (payment_processor / assign_c2b_payment), so listing
        # both tables showed every Paybill/Till payment twice. Keep the C2B
        # row (it carries matched/assign state) and drop its Transaction twin.
        c2b_codes = C2BPayment.objects.values('transaction_id')
        stk_transactions = Transaction.objects.filter(payment_method='mpesa').exclude(
            transaction_id__in=c2b_codes
        ).exclude(mpesa_receipt_number__in=c2b_codes)
        transactions = stk_transactions.select_related('customer').order_by('-created_at')[:fetch_limit]

        c2b_payments = C2BPayment.objects.select_related(
            'matched_customer'
        ).order_by('-created_at')[:fetch_limit]

        rows = []
        for t in transactions:
            rows.append({
                'c2b_payment_id': None,
                'transaction_id': t.transaction_id,
                'customer': t.customer.username,
                'matched': True,
                'payer_name': t.customer.get_full_name(),
                'amount': float(t.amount),
                'method': 'stk',
                'status': 'utilized' if t.status == 'completed' else 'open',
                'paid_at': t.mpesa_transaction_date or t.created_at,
            })
        for c in c2b_payments:
            rows.append({
                'c2b_payment_id': c.id,
                'transaction_id': c.transaction_id,
                # Unmatched/non-customer payers only ever get the hashed
                # MSISDN Safaricom sent -- see apps.payments.services.phone_hash
                # for why we never attempt to reverse it back to a real number.
                'customer': c.matched_customer.username if c.matched_customer else c.msisdn,
                'matched': c.matched_customer_id is not None,
                # Name Safaricom sent with a Buy Goods/Paybill payment, so an
                # unmatched payer is recognisable without their phone number.
                'payer_name': payer_display_name(c),
                'amount': float(c.amount),
                'method': 'c2b',
                'status': 'utilized' if c.status == 'activated' else 'open',
                'paid_at': c.transaction_time or c.created_at,
            })

        rows.sort(key=lambda r: r['paid_at'], reverse=True)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]

        total = stk_transactions.count() + C2BPayment.objects.count()

        return Response({
            'results': page_rows,
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max((total + page_size - 1) // page_size, 1),
        })


class RouterBandwidthTrendView(APIView):
    """
    Per-router bandwidth usage trend, for the admin Network Ops page.

    CAVEAT (also returned in the response so the frontend renders it
    visibly, not just here as a code comment): UsageRecord has no direct
    Router FK -- only via the customer's CURRENT PPPoESecret/HotspotUser.router
    (both apps.network.models). A customer who has since switched routers
    will have their historical usage attributed to their new router, not
    the one actually carrying that traffic at the time. Fine for the common
    case (customers rarely change routers), but not exact.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        router_id = request.query_params.get('router')
        if not router_id:
            return Response({'error': 'router is required'}, status=status.HTTP_400_BAD_REQUEST)

        router = Router.objects.filter(id=router_id).first()
        if not router:
            return Response({'error': 'Router not found'}, status=status.HTTP_404_NOT_FOUND)

        period = request.query_params.get('period', 'daily')
        date_str = request.query_params.get('date')
        try:
            ref_date = dt.date.fromisoformat(date_str) if date_str else timezone.now().date()
        except ValueError:
            ref_date = timezone.now().date()

        start, end, _, _ = report_window(period, ref_date)

        customer_ids = set(PPPoESecret.objects.filter(router=router).values_list('customer_id', flat=True))
        customer_ids |= set(HotspotUser.objects.filter(router=router).values_list('customer_id', flat=True))

        daily = UsageRecord.objects.filter(
            customer_id__in=customer_ids, created_at__date__gte=start, created_at__date__lte=end
        ).annotate(date=TruncDate('created_at')).values('date').annotate(
            up=Sum('upload_bytes'), down=Sum('download_bytes')
        ).order_by('date')

        series = []
        peak_mbps = 0
        for row in daily:
            day_bytes = (row['up'] or 0) + (row['down'] or 0)
            # bits/day -> Mbps (decimal, matching how BillingPlan.download_speed is stated)
            avg_mbps = round(day_bytes * 8 / 1_000_000 / 86400, 2)
            peak_mbps = max(peak_mbps, avg_mbps)

            entry = {'date': row['date'].isoformat(), 'avg_mbps': avg_mbps}
            if router.uplink_mbps:
                if avg_mbps >= router.uplink_mbps:
                    entry['headroom_pct'] = 0
                    entry['over_capacity'] = True
                else:
                    entry['headroom_pct'] = round((1 - avg_mbps / router.uplink_mbps) * 100, 1)
            series.append(entry)

        return Response({
            'router': {'id': router.id, 'name': router.name, 'uplink_mbps': router.uplink_mbps},
            'period': period,
            'start': start,
            'end': end,
            'series': series,
            'peak_mbps': peak_mbps,
            'caveat': (
                "Attribution is based on each customer's CURRENT router assignment, applied "
                "retroactively -- historical usage for a customer who has since switched "
                "routers will show under their new router, not the one they actually used "
                "at the time."
            ),
        })


class ChurnForecastView(APIView):
    """
    Subscriptions expiring soon + a renewal-rate metric, for the admin
    Network Ops page. Admin/sales only, like IncomeReportView -- this is a
    revenue-retention metric, not operational capacity data.
    """
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        days = min(max(int(request.query_params.get('days', 30) or 30), 1), 90)
        today = timezone.now().date()
        end_date = today + timedelta(days=days)

        expiring_qs = Subscription.objects.filter(
            status='active', expiry_date__date__gte=today, expiry_date__date__lte=end_date
        ).select_related('customer', 'plan').order_by('expiry_date')

        expiring = [
            {
                'username': s.customer.username,
                'plan': s.plan.name,
                'expires_on': s.expiry_date,
                'days_left': (s.expiry_date.date() - today).days,
            }
            for s in expiring_qs
        ]

        # Of subscriptions that lapsed more than `days` ago (long enough to
        # have had a real chance to renew by now), what fraction of those
        # customers have a newer Subscription since. O(N) .exists() calls --
        # fine at this WISP's data volume (hundreds-low thousands of
        # subscriptions); rewrite with Exists/OuterRef as a single query if
        # this ever needs to run over 10k+ lapsed subscriptions.
        cutoff = timezone.now() - timedelta(days=days)
        lapsed = list(Subscription.objects.filter(expiry_date__lt=cutoff).select_related('customer'))
        renewed_count = sum(
            1 for sub in lapsed
            if Subscription.objects.filter(customer=sub.customer, created_at__gt=sub.expiry_date).exists()
        )
        lapsed_count = len(lapsed)

        return Response({
            'days': days,
            'expiring': expiring,
            'expiring_count': len(expiring),
            'renewal_rate': {
                'lapsed_count': lapsed_count,
                'renewed_count': renewed_count,
                'renewal_rate_pct': round(renewed_count / lapsed_count * 100, 1) if lapsed_count else None,
            },
        })


def _parse_day(value):
    """'YYYY-MM-DD' -> date, or None."""
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


class DailyUsageView(APIView):
    """
    Whole-network data usage per day (GB) between start_date and end_date
    (default: last 30 days), for the Reports "Data usage overview" chart.
    Days are Nairobi days (TruncDate uses the active TIME_ZONE).
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        today = timezone.localdate()
        end = _parse_day(request.query_params.get('end_date')) or today
        start = _parse_day(request.query_params.get('start_date')) or end - timedelta(days=29)
        if (end - start).days > 366:
            return Response({'error': 'Pick a range of at most a year.'}, status=status.HTTP_400_BAD_REQUEST)
        rows = UsageRecord.objects.filter(
            start_time__date__gte=start, start_time__date__lte=end,
        ).annotate(date=TruncDate('start_time')).values('date').annotate(
            up=Sum('upload_bytes'), down=Sum('download_bytes'), users=Count('customer', distinct=True),
        )
        gb = 1024 ** 3
        by_day = {r['date']: r for r in rows}
        out = []
        day = start
        while day <= end:
            r = by_day.get(day)
            up, down = (r['up'] or 0, r['down'] or 0) if r else (0, 0)
            out.append({
                'date': day.isoformat(),
                'upload_gb': round(up / gb, 2),
                'download_gb': round(down / gb, 2),
                'total_gb': round((up + down) / gb, 2),
                'users': r['users'] if r else 0,
            })
            day += timedelta(days=1)
        return Response(out)


class DayBreakdownView(APIView):
    """
    Drill-down for one bar on the Reports charts.
    ?kind=revenue&date=YYYY-MM-DD -> totals by plan and payment method, plus
      that day's completed payments (admin/sales, like the income report).
    ?kind=usage&date=YYYY-MM-DD -> usage by service type and the top
      subscribers that day.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        kind = request.query_params.get('kind')
        day = _parse_day(request.query_params.get('date'))
        if not day or kind not in ('revenue', 'usage'):
            return Response({'error': 'kind (revenue|usage) and date (YYYY-MM-DD) are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if kind == 'revenue':
            if not can_see_income(request.user):
                return Response({'error': 'Not allowed.'}, status=status.HTTP_403_FORBIDDEN)
            return Response(self._revenue(day))
        return Response(self._usage(day))

    @staticmethod
    def _revenue(day):
        qs = Transaction.objects.filter(status='completed', created_at__date=day)
        total = qs.aggregate(total=Sum('amount'), n=Count('id'))
        by_plan = [
            {'name': r['subscription__plan__name'] or 'Balance / no plan', 'count': r['n'], 'amount': float(r['amount'] or 0)}
            for r in qs.values('subscription__plan__name').annotate(n=Count('id'), amount=Sum('amount')).order_by('-amount')
        ]
        method_labels = dict(Transaction.PAYMENT_METHOD_CHOICES)
        by_method = [
            {'name': method_labels.get(r['payment_method'], r['payment_method']), 'count': r['n'], 'amount': float(r['amount'] or 0)}
            for r in qs.values('payment_method').annotate(n=Count('id'), amount=Sum('amount')).order_by('-amount')
        ]
        items = [
            {
                'time': t.created_at,
                'customer': t.customer.get_full_name() or t.customer.username,
                'username': t.customer.username,
                'plan': t.subscription.plan.name if t.subscription_id and t.subscription.plan_id else '',
                'method': method_labels.get(t.payment_method, t.payment_method),
                'reference': t.mpesa_receipt_number or t.transaction_id,
                'amount': float(t.amount),
            }
            for t in qs.select_related('customer', 'subscription__plan').order_by('-created_at')[:200]
        ]
        return {
            'kind': 'revenue', 'date': day.isoformat(),
            'total': float(total['total'] or 0), 'count': total['n'],
            'by_plan': by_plan, 'by_method': by_method, 'items': items,
        }

    @staticmethod
    def _usage(day):
        gb = 1024 ** 3
        qs = UsageRecord.objects.filter(start_time__date=day)
        agg = qs.aggregate(up=Sum('upload_bytes'), down=Sum('download_bytes'), users=Count('customer', distinct=True))
        by_type = [
            {'name': (r['customer__service_type'] or 'unknown').upper(),
             'total_gb': round(((r['up'] or 0) + (r['down'] or 0)) / gb, 2), 'users': r['users']}
            for r in qs.values('customer__service_type').annotate(
                up=Sum('upload_bytes'), down=Sum('download_bytes'), users=Count('customer', distinct=True))
        ]
        by_type.sort(key=lambda r: -r['total_gb'])
        users = qs.values('customer__username', 'customer__first_name', 'customer__last_name').annotate(
            up=Sum('upload_bytes'), down=Sum('download_bytes'),
        ).annotate(total=F('up') + F('down')).order_by('-total')[:50]
        items = [
            {
                'customer': f"{u['customer__first_name']} {u['customer__last_name']}".strip() or u['customer__username'],
                'username': u['customer__username'],
                'upload_gb': round((u['up'] or 0) / gb, 2),
                'download_gb': round((u['down'] or 0) / gb, 2),
                'total_gb': round((u['total'] or 0) / gb, 2),
            }
            for u in users
        ]
        up, down = agg['up'] or 0, agg['down'] or 0
        return {
            'kind': 'usage', 'date': day.isoformat(),
            'total_gb': round((up + down) / gb, 2), 'users': agg['users'],
            'upload_gb': round(up / gb, 2), 'download_gb': round(down / gb, 2),
            'by_type': by_type, 'items': items,
        }
