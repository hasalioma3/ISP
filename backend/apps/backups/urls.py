from django.urls import path

from apps.backups import views

urlpatterns = [
    path('', views.BackupListView.as_view(), name='backups'),
    path('settings/', views.BackupSettingsView.as_view(), name='backup-settings'),
    path('gdrive/', views.DriveConnectView.as_view(), name='backup-gdrive'),
    path('gdrive/test/', views.DriveTestView.as_view(), name='backup-gdrive-test'),
    path('nas/test/', views.NasTestView.as_view(), name='backup-nas-test'),
    path('migration-check/', views.MigrationCheckView.as_view(), name='backup-migration-check'),
    path('<int:pk>/', views.BackupDetailView.as_view(), name='backup-detail'),
    path('<int:pk>/upload/', views.BackupUploadView.as_view(), name='backup-upload'),
]
