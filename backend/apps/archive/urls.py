from django.urls import path

from apps.archive import views

urlpatterns = [
    path('settings/', views.ArchiveSettingsView.as_view(), name='archive-settings'),
    path('runs/', views.ArchiveRunListView.as_view(), name='archive-runs'),
    path('runs/<int:pk>/', views.ArchiveRunDetailView.as_view(), name='archive-run'),
]
