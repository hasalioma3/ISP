from django.conf import settings
from django.db import models

from apps.notifications.fields import EncryptedCharField


class BackupSettings(models.Model):
    """Singleton (pk=1): schedule, retention, what to include, Google Drive, NAS."""
    FREQUENCIES = [('daily', 'Daily'), ('weekly', 'Weekly')]

    schedule_enabled = models.BooleanField(default=True)
    frequency = models.CharField(max_length=10, choices=FREQUENCIES, default='daily')
    hour = models.PositiveSmallIntegerField(default=2)          # Nairobi time
    weekday = models.PositiveSmallIntegerField(default=6)       # 0=Mon … 6=Sun, weekly only
    keep_local = models.PositiveSmallIntegerField(default=7)    # archives kept on this server
    keep_remote = models.PositiveSmallIntegerField(default=30)  # archives kept on Google Drive

    include_routers = models.BooleanField(default=True)
    include_media = models.BooleanField(default=True)
    # The WhatsApp login and the server's env (SECRET_KEY,
    # NOTIFICATIONS_ENCRYPTION_KEY, M-Pesa keys) make a restore complete --
    # without the encryption key every stored SMS/SMTP/M-Pesa credential
    # restores blank. They're secrets, so they're only ever put in an
    # archive that is encrypted with the passphrase.
    include_secrets = models.BooleanField(default=True)
    encryption_passphrase = EncryptedCharField(max_length=500, blank=True)

    gdrive_enabled = models.BooleanField(default=False)
    gdrive_client_id = models.CharField(max_length=255, blank=True)
    gdrive_client_secret = EncryptedCharField(max_length=500, blank=True)
    gdrive_refresh_token = EncryptedCharField(max_length=1000, blank=True)
    gdrive_account = models.CharField(max_length=255, blank=True)
    gdrive_folder_id = models.CharField(max_length=128, blank=True)
    gdrive_folder_name = models.CharField(max_length=255, default='ISP Billing backups', blank=True)
    # In-progress Google sign-in (device flow), kept in the DB rather than
    # the cache: there's no shared cache, and gunicorn may run >1 process.
    gdrive_device_code = models.CharField(max_length=255, blank=True)
    gdrive_device_expires = models.DateTimeField(null=True, blank=True)

    # Synology (or any WebDAV) NAS -- see apps.backups.nas.
    nas_enabled = models.BooleanField(default=False)
    # 'webdav': a direct address to DSM's WebDAV Server. 'quickconnect': a
    # QuickConnect ID, reached through Synology's directory/relay and the
    # File Station API -- no port forwarding or VPN needed.
    NAS_MODES = [('quickconnect', 'QuickConnect'), ('webdav', 'Direct address (WebDAV)')]
    nas_mode = models.CharField(max_length=12, choices=NAS_MODES, default='quickconnect')
    nas_quickconnect_id = models.CharField(max_length=63, blank=True)
    nas_url = models.CharField(max_length=255, blank=True)            # https://nas.example.com:5006
    nas_username = models.CharField(max_length=150, blank=True)
    nas_password = EncryptedCharField(max_length=500, blank=True)
    nas_folder = models.CharField(max_length=255, default='/backups/isp-billing', blank=True)
    nas_verify_tls = models.BooleanField(default=True)
    keep_nas = models.PositiveSmallIntegerField(default=30)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'backup_settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Backup settings'


class Backup(models.Model):
    KINDS = [('manual', 'Manual'), ('scheduled', 'Scheduled')]
    STATUSES = [('running', 'Running'), ('ok', 'Completed'), ('partial', 'Completed with warnings'), ('failed', 'Failed')]
    REMOTE = [('', 'Not uploaded'), ('uploading', 'Uploading'), ('ok', 'On Google Drive'), ('failed', 'Upload failed'),
              ('deleted', 'Removed from Drive')]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    kind = models.CharField(max_length=10, choices=KINDS, default='manual')
    status = models.CharField(max_length=10, choices=STATUSES, default='running')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    filename = models.CharField(max_length=255, blank=True)
    size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    encrypted = models.BooleanField(default=False)
    # What went in: {'database': {...}, 'routers': [{name, ok, files, error}], 'media': n, ...}
    contents = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    local_deleted = models.BooleanField(default=False)
    remote_status = models.CharField(max_length=10, choices=REMOTE, default='', blank=True)
    remote_file_id = models.CharField(max_length=128, blank=True)
    remote_error = models.TextField(blank=True)
    # The NAS copy is tracked separately from Drive: either can be on, and one
    # failing mustn't hide that the other worked.
    NAS = [('', 'Not uploaded'), ('uploading', 'Uploading'), ('ok', 'On NAS'), ('failed', 'Upload failed'),
           ('deleted', 'Removed from NAS')]
    nas_status = models.CharField(max_length=10, choices=NAS, default='', blank=True)
    nas_path = models.CharField(max_length=500, blank=True)
    nas_error = models.TextField(blank=True)

    class Meta:
        db_table = 'backups'
        ordering = ['-created_at']

    def __str__(self):
        return self.filename or f'Backup #{self.pk}'
