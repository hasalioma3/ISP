from django.urls import path

from apps.audit import views

urlpatterns = [
    path('logs/', views.AuditLogView.as_view(), name='audit-logs'),
    path('logs/facets/', views.AuditFacetsView.as_view(), name='audit-facets'),
]
