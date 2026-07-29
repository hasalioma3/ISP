from django.urls import path
from .views import (
    DashboardStatsView, IncomeReportView, UsageReportView, UsageChartView,
    DashboardExtraView, ExpiringTodayView, RecentActivityView, DataUsageView,
)

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('dashboard/extra/', DashboardExtraView.as_view(), name='dashboard-extra'),
    path('income/', IncomeReportView.as_view(), name='income-report'),
    path('usage/', UsageReportView.as_view(), name='usage-report'),
    path('usage-chart/', UsageChartView.as_view(), name='usage-chart'),
    path('data-usage/', DataUsageView.as_view(), name='data-usage'),
    path('expiring-today/', ExpiringTodayView.as_view(), name='expiring-today'),
    path('recent-activity/', RecentActivityView.as_view(), name='recent-activity'),
]
