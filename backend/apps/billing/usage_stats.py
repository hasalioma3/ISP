import datetime
from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone


def build_usage_chart(queryset):
    """
    Today / this-week (Mon-Sun) / this-year-by-month (Jan-Dec) upload+download
    totals from a UsageRecord queryset, in GB. Used for both the per-subscriber
    and network-wide "live usage" charts.
    """
    now = timezone.now()
    today = now.date()

    today_agg = queryset.filter(created_at__date=today).aggregate(
        up=Sum('upload_bytes'), down=Sum('download_bytes')
    )
    today_up = round((today_agg['up'] or 0) / (1024 ** 3), 2)
    today_down = round((today_agg['down'] or 0) / (1024 ** 3), 2)
    today_data = {
        'upload_gb': today_up,
        'download_gb': today_down,
        'total_gb': round(today_up + today_down, 2),
    }

    monday = today - datetime.timedelta(days=today.weekday())
    week_days = [monday + datetime.timedelta(days=i) for i in range(7)]
    weekly_rows = queryset.filter(
        created_at__date__gte=monday, created_at__date__lte=week_days[-1]
    ).annotate(day=TruncDate('created_at')).values('day').annotate(
        up=Sum('upload_bytes'), down=Sum('download_bytes')
    )
    weekly_map = {row['day']: row for row in weekly_rows}
    weekly = []
    for d in week_days:
        row = weekly_map.get(d)
        weekly.append({
            'day': d.strftime('%A'),
            'upload_gb': round((row['up'] or 0) / (1024 ** 3), 2) if row else 0,
            'download_gb': round((row['down'] or 0) / (1024 ** 3), 2) if row else 0,
        })

    year_start = today.replace(month=1, day=1)
    monthly_rows = queryset.filter(created_at__date__gte=year_start).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(up=Sum('upload_bytes'), down=Sum('download_bytes'))
    monthly_map = {row['month'].month: row for row in monthly_rows}
    monthly = []
    for m in range(1, 13):
        row = monthly_map.get(m)
        monthly.append({
            'month': datetime.date(today.year, m, 1).strftime('%b'),
            'upload_gb': round((row['up'] or 0) / (1024 ** 3), 2) if row else 0,
            'download_gb': round((row['down'] or 0) / (1024 ** 3), 2) if row else 0,
        })

    return {'today': today_data, 'weekly': weekly, 'monthly': monthly}
