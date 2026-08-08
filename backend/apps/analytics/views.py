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
        total_customers = Customer.objects.count()

        # Live online counts (kept fresh by the collect_usage_statistics
        # celery task, not queried live from routers on every page load)
        hotspot_online = ActiveSession.objects.filter(session_type='hotspot').count()
        pppoe_online = ActiveSession.objects.filter(session_type='pppoe').count()

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
            })

        show_income = can_see_income(request.user)

        return Response({
            'active_subscribers': active_subs,
            'expired_subscribers': expired_subs,
            'income_today': revenue_today if show_income else None,
            'monthly_revenue': revenue_month if show_income else None,
            'monthly_usage_gb': usage_gb,
            'new_customers': new_customers,
            'total_customers': total_customers,
            'hotspot_online': hotspot_online,
            'pppoe_online': pppoe_online,
            'total_online': hotspot_online + pppoe_online,
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

        # Payment gateway status -- a real live connectivity check, not just
        # reading config back
        from apps.payments.services.mpesa_service import mpesa_service
        from django.conf import settings as dj_settings
        gateway_token = mpesa_service.get_access_token()
        payment_gateway = {
            'name': 'M-Pesa STK Push',
            'environment': dj_settings.MPESA_ENVIRONMENT,
            'shortcode': dj_settings.MPESA_SHORTCODE,
            'connected': bool(gateway_token),
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

            last_transactions = [
                {'username': t.customer.username, 'amount': float(t.amount), 'date': t.created_at}
                for t in Transaction.objects.select_related('customer').order_by('-created_at')[:5]
            ]

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

    def _window(self, period, ref_date):
        if period == 'weekly':
            start = ref_date - dt.timedelta(days=ref_date.weekday())
            end = start + dt.timedelta(days=6)
            prev_start = start - dt.timedelta(days=7)
            prev_end = start - dt.timedelta(days=1)
        elif period == 'monthly':
            start = ref_date.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1, day=1) - dt.timedelta(days=1)
            else:
                end = start.replace(month=start.month + 1, day=1) - dt.timedelta(days=1)
            prev_month_end = start - dt.timedelta(days=1)
            prev_start = prev_month_end.replace(day=1)
            prev_end = prev_month_end
        else:  # daily
            start = end = ref_date
            prev_start = prev_end = ref_date - dt.timedelta(days=1)
        return start, end, prev_start, prev_end

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

        start, end, prev_start, prev_end = self._window(period, ref_date)

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

        transactions = Transaction.objects.filter(
            payment_method='mpesa'
        ).select_related('customer').order_by('-created_at')[:fetch_limit]

        c2b_payments = C2BPayment.objects.select_related(
            'matched_customer'
        ).order_by('-created_at')[:fetch_limit]

        rows = []
        for t in transactions:
            rows.append({
                'transaction_id': t.transaction_id,
                'customer': t.customer.username,
                'amount': float(t.amount),
                'method': 'stk',
                'status': 'utilized' if t.status == 'completed' else 'open',
                'paid_at': t.mpesa_transaction_date or t.created_at,
            })
        for c in c2b_payments:
            rows.append({
                'transaction_id': c.transaction_id,
                # Unmatched/non-customer payers only ever get the hashed
                # MSISDN Safaricom sent -- see apps.payments.services.phone_hash
                # for why we never attempt to reverse it back to a real number.
                'customer': c.matched_customer.username if c.matched_customer else c.msisdn,
                'amount': float(c.amount),
                'method': 'c2b',
                'status': 'utilized' if c.status == 'activated' else 'open',
                'paid_at': c.transaction_time or c.created_at,
            })

        rows.sort(key=lambda r: r['paid_at'], reverse=True)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]

        total = (
            Transaction.objects.filter(payment_method='mpesa').count()
            + C2BPayment.objects.count()
        )

        return Response({
            'results': page_rows,
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max((total + page_size - 1) // page_size, 1),
        })
