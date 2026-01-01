from django.urls import path
from .views import DashboardStatsView, IncomeReportView, UsageReportView

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('income/', IncomeReportView.as_view(), name='income-report'),
    path('usage/', UsageReportView.as_view(), name='usage-report'),
]
