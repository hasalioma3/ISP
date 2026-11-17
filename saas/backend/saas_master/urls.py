from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from cloud.accounts import views as accounts
from cloud.billing import views as billing
from cloud.core import views as core
from cloud.pricing import views as pricing
from cloud.tenants import views as tenants

urlpatterns = [
    path('django-admin/', admin.site.urls),

    # Auth
    path('api/auth/login/', accounts.login),
    path('api/auth/refresh/', TokenRefreshView.as_view()),
    path('api/auth/me/', accounts.MeView.as_view()),
    path('api/auth/password/', accounts.ChangePasswordView.as_view()),

    # Public
    path('api/public/config/', core.PublicConfigView.as_view()),
    path('api/public/signup/', tenants.SignupView.as_view()),
    path('api/public/slug/', tenants.SlugCheckView.as_view()),
    path('api/public/quote/', pricing.QuoteView.as_view()),

    # M-Pesa (Safaricom calls these)
    path('api/mpesa/stk/<str:token>/', billing.StkCallbackView.as_view()),
    path('api/mpesa/c2b/<str:token>/validation/', billing.C2BValidationView.as_view()),
    path('api/mpesa/c2b/<str:token>/confirmation/', billing.C2BConfirmationView.as_view()),
    path('api/mpesa/platform/<str:token>/', billing.PlatformStkCallbackView.as_view()),
    path('api/mpesa/payout/result/', billing.PayoutResultView.as_view()),
    path('api/mpesa/payout/timeout/', billing.PayoutTimeoutView.as_view()),

    # Platform admin
    path('api/admin/dashboard/', core.DashboardView.as_view()),
    path('api/admin/settings/', core.SettingsView.as_view()),
    path('api/admin/settings/mpesa/', core.MpesaActionView.as_view()),
    path('api/admin/team/', accounts.TeamView.as_view()),
    path('api/admin/team/<int:pk>/', accounts.TeamMemberView.as_view()),
    path('api/admin/tenants/', tenants.TenantListView.as_view()),
    path('api/admin/tenants/<int:pk>/', tenants.TenantDetailView.as_view()),
    path('api/admin/tenants/<int:pk>/action/', tenants.TenantActionView.as_view()),
    path('api/admin/tenants/<int:pk>/ledger/', billing.LedgerView.as_view()),
    path('api/admin/plans/', pricing.PlanListView.as_view()),
    path('api/admin/plans/<int:pk>/', pricing.PlanDetailView.as_view()),
    path('api/admin/collections/', billing.CollectionListView.as_view()),
    path('api/admin/collections/<int:pk>/action/', billing.CollectionActionView.as_view()),
    path('api/admin/invoices/', billing.InvoiceListView.as_view()),
    path('api/admin/invoices/create/', billing.InvoiceCreateView.as_view()),
    path('api/admin/invoices/<int:pk>/action/', billing.InvoiceActionView.as_view()),
    path('api/admin/settlements/', billing.SettlementListView.as_view()),
    path('api/admin/settlements/<int:pk>/action/', billing.SettlementActionView.as_view()),

    # ISP owner portal
    path('api/portal/tenant/', tenants.PortalTenantView.as_view()),
    path('api/portal/activate/', tenants.PortalActivateView.as_view()),
    path('api/portal/cancel/', tenants.PortalCancelView.as_view()),
    path('api/portal/retry/', tenants.PortalRetryView.as_view()),
    path('api/portal/invoices/', billing.PortalInvoicesView.as_view()),
    path('api/portal/invoices/<int:pk>/pay/', billing.PortalPayInvoiceView.as_view()),
    path('api/portal/statement/', billing.PortalStatementView.as_view()),
    path('api/portal/settlements/', billing.PortalSettlementsView.as_view()),
    path('api/portal/collections/', billing.PortalCollectionsView.as_view()),
]
