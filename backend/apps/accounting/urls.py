from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('expenses', views.ExpenseViewSet, basename='expenses')
router.register('other-income', views.OtherIncomeViewSet, basename='other-income')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', views.ProfitDashboardView.as_view(), name='profit-dashboard'),
]
