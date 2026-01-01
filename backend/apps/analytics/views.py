from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
import csv
from django.http import HttpResponse

from apps.billing.models import Transaction, Subscription, UsageRecord
from apps.customers.models import Customer

class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Active Subscribers
        active_subs = Subscription.objects.filter(status='active', expiry_date__gt=now).count()
        
        # Revenue this Month
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
        
        return Response({
            'active_subscribers': active_subs,
            'monthly_revenue': revenue_month,
            'monthly_usage_gb': usage_gb,
            'new_customers': new_customers
        })

class IncomeReportView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        export = request.query_params.get('export') == 'csv'
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        now = timezone.now()
        end_date = now
        start_date = now - timedelta(days=30)
        
        if start_date_str:
            try:
                start_date = timezone.datetime.fromisoformat(start_date_str)
            except: pass
        if end_date_str:
            try:
                end_date = timezone.datetime.fromisoformat(end_date_str)
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
