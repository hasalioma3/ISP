import datetime as dt

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.utils import report_window
from apps.billing.models import Subscription, Transaction, UsageRecord
from apps.customers.models import Customer
from apps.network.models import ActiveSession


class TopHotspotUsersView(APIView):
    """
    The ten hotspot customers who used the most data -- or spent the most --
    in a Daily/Weekly/Monthly window (same windows as Data Usage). Only
    usage on hotspot plans counts, so a "both" customer's PPPoE traffic
    doesn't push them up this list. Backs the "Top 10 hotspot users" card.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        period = request.query_params.get('period', 'weekly')
        by = request.query_params.get('by', 'data')
        try:
            limit = max(1, min(int(request.query_params.get('limit', 10)), 50))
        except ValueError:
            limit = 10
        try:
            ref_date = dt.date.fromisoformat(request.query_params.get('date') or '')
        except ValueError:
            ref_date = timezone.localdate()
        start, end, _, _ = report_window(period, ref_date)
        gb = 1024 ** 3

        usage = UsageRecord.objects.filter(
            created_at__date__gte=start, created_at__date__lte=end, subscription__plan__service_type='hotspot',
        ).values('customer_id').annotate(up=Sum('upload_bytes'), down=Sum('download_bytes'),
                                         days=Count('created_at__date', distinct=True))
        usage_map = {u['customer_id']: u for u in usage}

        spend = Transaction.objects.filter(
            status='completed', created_at__date__gte=start, created_at__date__lte=end,
            subscription__plan__service_type='hotspot',
        ).exclude(payment_method='balance').values('customer_id').annotate(total=Sum('amount'), count=Count('id'))
        spend_map = {s['customer_id']: s for s in spend}

        if by == 'spend':
            ranked = sorted(spend_map, key=lambda cid: -spend_map[cid]['total'])[:limit]
        else:
            ranked = sorted(usage_map, key=lambda cid: -((usage_map[cid]['up'] or 0) + (usage_map[cid]['down'] or 0)))[:limit]

        customers = Customer.objects.in_bulk(ranked)
        online = set(ActiveSession.objects.filter(customer_id__in=ranked).values_list('customer_id', flat=True))
        current_plans = {}
        for s in Subscription.objects.filter(customer_id__in=ranked, status='active', expiry_date__gt=timezone.now()) \
                .select_related('plan').order_by('created_at'):
            current_plans[s.customer_id] = s.plan.name  # newest wins
        rows = []
        for cid in ranked:
            c = customers.get(cid)
            if not c:
                continue
            u, s = usage_map.get(cid, {}), spend_map.get(cid, {})
            up, down = (u.get('up') or 0), (u.get('down') or 0)
            rows.append({
                'rank': len(rows) + 1, 'customer_id': cid, 'username': c.username,
                'name': c.get_full_name() or c.username, 'phone': c.phone_number,
                'mac_address': c.hotspot_mac_address or '',
                'upload_gb': round(up / gb, 2), 'download_gb': round(down / gb, 2), 'total_gb': round((up + down) / gb, 2),
                'active_days': u.get('days', 0), 'spent': float(s.get('total') or 0), 'purchases': s.get('count', 0),
                'current_plan': current_plans.get(cid, ''), 'online': cid in online,
            })
        return Response({'period': period, 'by': by, 'start': start, 'end': end, 'results': rows})
