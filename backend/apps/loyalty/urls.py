from django.urls import path

from apps.loyalty import views

urlpatterns = [
    path('settings/', views.LoyaltySettingsView.as_view(), name='loyalty-settings'),
    path('overview/', views.LoyaltyOverviewView.as_view(), name='loyalty-overview'),
    path('customers/<int:customer_id>/', views.CustomerLoyaltyView.as_view(), name='loyalty-customer'),
    path('me/', views.MyLoyaltyView.as_view(), name='loyalty-me'),
]
