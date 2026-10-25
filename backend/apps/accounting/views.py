from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Transaction
from apps.customers.permissions import RoleAllowed

from .models import Expense, OtherIncome
from .serializers import ExpenseSerializer, OtherIncomeSerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    """Expense CRUD -- same income-visibility convention as IncomeReportView (admin/sales, not technician)."""
    serializer_class = ExpenseSerializer
    permission_classes = [RoleAllowed('admin', 'sales')]
    queryset = Expense.objects.all()
    filterset_fields = ['category']
    search_fields = ['description', 'notes']
    ordering_fields = ['date', 'amount', 'created_at']

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


class OtherIncomeViewSet(viewsets.ModelViewSet):
    """Other-income CRUD -- same income-visibility convention as IncomeReportView (admin/sales, not technician)."""
    serializer_class = OtherIncomeSerializer
    permission_classes = [RoleAllowed('admin', 'sales')]
    queryset = OtherIncome.objects.all()
    filterset_fields = ['category']
    search_fields = ['description', 'notes']
    ordering_fields = ['date', 'amount', 'created_at']

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


def _parse_date_range(request):
    """Same start_date/end_date query-param parsing as IncomeReportView, for a consistent date picker UX."""
    now = timezone.now()
    end_date = now
    start_date = now - timedelta(days=30)

    start_date_str = request.query_params.get('start_date')
    end_date_str = request.query_params.get('end_date')

    if start_date_str:
        try:
            parsed = timezone.datetime.fromisoformat(start_date_str)
            start_date = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        except (ValueError, TypeError):
            pass
    if end_date_str:
        try:
            parsed = timezone.datetime.fromisoformat(end_date_str)
            end_date = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
            # A date-only string parses to midnight -- as a range's upper
            # bound that excludes the entire day it names, since almost
            # every transaction happens after 00:00. Push it to the last
            # instant of that day instead.
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        except (ValueError, TypeError):
            pass

    return start_date, end_date


class ProfitDashboardView(APIView):
    """
    Revenue (real customer payments) + other income - expenses, over a
    date range, with a daily series for charting and an expense category
    breakdown.
    """
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        start_date, end_date = _parse_date_range(request)
        start_day, end_day = start_date.date(), end_date.date()

        # 'balance' Transactions are an internal reallocation of money
        # already counted as revenue when it first came in (STK/C2B/cash),
        # not new cash -- e.g. a plan switch paid from existing balance.
        # Counting them too would double-count that money.
        revenue_qs = Transaction.objects.filter(
            status='completed', created_at__range=(start_date, end_date)
        ).exclude(payment_method='balance')
        other_income_qs = OtherIncome.objects.filter(date__range=(start_day, end_day))
        expense_qs = Expense.objects.filter(date__range=(start_day, end_day))

        revenue_total = float(revenue_qs.aggregate(total=Sum('amount'))['total'] or 0)
        other_income_total = float(other_income_qs.aggregate(total=Sum('amount'))['total'] or 0)
        expense_total = float(expense_qs.aggregate(total=Sum('amount'))['total'] or 0)
        total_income = revenue_total + other_income_total

        daily_revenue = {
            r['date']: float(r['total'])
            for r in revenue_qs.annotate(date=TruncDate('created_at')).values('date').annotate(total=Sum('amount'))
        }
        daily_other_income = {
            r['date']: float(r['total'])
            for r in other_income_qs.values('date').annotate(total=Sum('amount'))
        }
        daily_expenses = {
            r['date']: float(r['total'])
            for r in expense_qs.values('date').annotate(total=Sum('amount'))
        }

        all_dates = sorted(set(daily_revenue) | set(daily_other_income) | set(daily_expenses))
        daily_series = []
        for d in all_dates:
            income = daily_revenue.get(d, 0) + daily_other_income.get(d, 0)
            exp = daily_expenses.get(d, 0)
            daily_series.append({
                'date': d,
                'income': round(income, 2),
                'expenses': round(exp, 2),
                'profit': round(income - exp, 2),
            })

        expense_by_category = [
            {
                'category': e['category'],
                'label': dict(Expense.CATEGORY_CHOICES).get(e['category'], e['category']),
                'total': float(e['total']),
            }
            for e in expense_qs.values('category').annotate(total=Sum('amount')).order_by('-total')
        ]

        return Response({
            'start_date': start_day,
            'end_date': end_day,
            'revenue': round(revenue_total, 2),
            'other_income': round(other_income_total, 2),
            'total_income': round(total_income, 2),
            'total_expenses': round(expense_total, 2),
            'profit': round(total_income - expense_total, 2),
            'daily_series': daily_series,
            'expense_by_category': expense_by_category,
        })
