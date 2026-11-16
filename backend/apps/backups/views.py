from datetime import timedelta

from django.utils import timezone
from django.http import FileResponse
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.views import IsSuperadmin
from apps.backups.models import Backup, BackupSettings


class SettingsSerializer(serializers.ModelSerializer):
    encryption_passphrase = serializers.CharField(write_only=True, required=False, allow_blank=True)
    gdrive_client_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    encryption_passphrase_set = serializers.SerializerMethodField()
    gdrive_client_secret_set = serializers.SerializerMethodField()
    gdrive_connected = serializers.SerializerMethodField()
    nas_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    nas_password_set = serializers.SerializerMethodField()

    class Meta:
        model = BackupSettings
        fields = ['schedule_enabled', 'frequency', 'hour', 'weekday', 'keep_local', 'keep_remote', 'include_routers',
                  'include_media', 'include_secrets', 'encryption_passphrase', 'encryption_passphrase_set',
                  'gdrive_enabled', 'gdrive_client_id', 'gdrive_client_secret', 'gdrive_client_secret_set',
                  'gdrive_connected', 'gdrive_account', 'gdrive_folder_name', 'nas_enabled', 'nas_mode', 'nas_quickconnect_id', 'nas_url',
                  'nas_username', 'nas_password', 'nas_password_set', 'nas_folder', 'nas_verify_tls', 'keep_nas',
                  'updated_at']
        read_only_fields = ['gdrive_account', 'updated_at']

    def get_encryption_passphrase_set(self, obj):
        return bool(obj.encryption_passphrase)

    def get_gdrive_client_secret_set(self, obj):
        return bool(obj.gdrive_client_secret)

    def get_gdrive_connected(self, obj):
        return bool(obj.gdrive_refresh_token)

    def get_nas_password_set(self, obj):
        return bool(obj.nas_password)

    def validate_nas_url(self, v):
        from urllib.parse import urlsplit
        v = (v or '').strip().rstrip('/')
        if not v:
            return v
        if '://' not in v:
            v = 'https://' + v
        parts = urlsplit(v)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise serializers.ValidationError('Use the WebDAV address, e.g. https://nas.example.com:5006')
        if 'quickconnect' in parts.hostname.lower():
            raise serializers.ValidationError("QuickConnect doesn't carry WebDAV -- choose QuickConnect as the "
                                              'connection type and enter just the ID.')
        return f'{parts.scheme}://{parts.netloc}'

    def validate_nas_folder(self, v):
        v = '/' + (v or '').strip().strip('/')
        if v == '/' or '..' in v.split('/'):
            raise serializers.ValidationError('Start with a shared folder, e.g. /backups/isp-billing')
        return v

    def validate_nas_quickconnect_id(self, v):
        from apps.backups.nas import NasError, normalize_quickconnect_id
        if not (v or '').strip():
            return ''
        try:
            return normalize_quickconnect_id(v)
        except NasError as e:
            raise serializers.ValidationError(str(e))

    def validate_keep_nas(self, v):
        return self.validate_keep_local(v)

    def validate(self, data):
        enabled = data.get('nas_enabled', self.instance.nas_enabled if self.instance else False)
        if enabled:
            from types import SimpleNamespace
            from apps.backups.nas import is_configured
            inst = self.instance
            merged = SimpleNamespace(**{f: data.get(f, getattr(inst, f, '')) for f in
                                        ('nas_mode', 'nas_url', 'nas_quickconnect_id', 'nas_username')},
                                     nas_password=data.get('nas_password') or getattr(inst, 'nas_password', ''))
            if not is_configured(merged):
                what = 'QuickConnect ID' if merged.nas_mode == 'quickconnect' else 'NAS address'
                raise serializers.ValidationError({'nas_enabled': f'Enter the {what}, username and password first.'})
        return data

    def validate_hour(self, v):
        if v > 23:
            raise serializers.ValidationError('Hour must be 0-23.')
        return v

    def validate_weekday(self, v):
        if v > 6:
            raise serializers.ValidationError('Weekday must be 0 (Mon) to 6 (Sun).')
        return v

    def validate_keep_local(self, v):
        if not 1 <= v <= 365:
            raise serializers.ValidationError('Keep between 1 and 365 backups.')
        return v

    def validate_keep_remote(self, v):
        return self.validate_keep_local(v)

    def validate_encryption_passphrase(self, v):
        if v and len(v) < 10:
            raise serializers.ValidationError('Use at least 10 characters.')
        return v

    def update(self, instance, data):
        # Blank secret fields in a PATCH mean "keep the stored one" unless
        # explicitly cleared with clear_passphrase.
        for secret in ('encryption_passphrase', 'gdrive_client_secret', 'nas_password'):
            if secret in data and not data[secret]:
                data.pop(secret)
        if self.initial_data.get('clear_passphrase'):
            data['encryption_passphrase'] = ''
        if 'gdrive_client_id' in data and data['gdrive_client_id'] != instance.gdrive_client_id:
            instance.gdrive_refresh_token = ''  # a new OAuth client needs a new sign-in
        return super().update(instance, data)


class BackupSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', default=None)
    status_label = serializers.CharField(source='get_status_display')
    remote_label = serializers.CharField(source='get_remote_status_display')
    nas_label = serializers.CharField(source='get_nas_status_display')
    downloadable = serializers.SerializerMethodField()

    class Meta:
        model = Backup
        fields = ['id', 'created_at', 'finished_at', 'kind', 'status', 'status_label', 'created_by', 'filename', 'size',
                  'sha256', 'encrypted', 'contents', 'warnings', 'error', 'local_deleted', 'remote_status',
                  'remote_label', 'remote_error', 'nas_status', 'nas_label', 'nas_path', 'nas_error', 'downloadable']

    def get_downloadable(self, obj):
        from apps.backups.runner import path_of
        p = path_of(obj)
        return bool(p and not obj.local_deleted and p.exists())


class BackupSettingsView(APIView):
    permission_classes = [IsSuperadmin]

    def get(self, request):
        return Response(SettingsSerializer(BackupSettings.load()).data)

    def patch(self, request):
        s = SettingsSerializer(BackupSettings.load(), data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class BackupListView(APIView):
    """GET: recent backups and disk usage. POST: back up now."""
    permission_classes = [IsSuperadmin]

    def get(self, request):
        import shutil
        from apps.backups.runner import backup_dir
        qs = Backup.objects.select_related('created_by')[:100]
        usage = shutil.disk_usage(backup_dir())
        return Response({
            'results': BackupSerializer(qs, many=True).data,
            'disk': {'free': usage.free, 'total': usage.total},
        })

    def post(self, request):
        from apps.backups.tasks import start_backup
        backup, error = start_backup('manual', request.user)
        if error:
            return Response({'error': error}, status=status.HTTP_409_CONFLICT)
        return Response(BackupSerializer(backup).data, status=status.HTTP_201_CREATED)


class BackupDetailView(APIView):
    permission_classes = [IsSuperadmin]

    def get(self, request, pk):
        """Download the archive."""
        from apps.backups.runner import path_of
        backup = Backup.objects.filter(pk=pk).first()
        p = path_of(backup) if backup else None
        if not p or backup.local_deleted or not p.exists():
            return Response({'error': 'This archive is no longer on the server'}, status=404)
        return FileResponse(open(p, 'rb'), as_attachment=True, filename=backup.filename)

    def delete(self, request, pk):
        from apps.backups.runner import path_of
        backup = Backup.objects.filter(pk=pk).first()
        if not backup:
            return Response(status=404)
        if backup.status == 'running':
            return Response({'error': 'Wait for the backup to finish'}, status=409)
        p = path_of(backup)
        if p:
            p.unlink(missing_ok=True)
        # remote=1 also removes the off-site copies. Each is tried even if the
        # other fails; the row is kept when one couldn't be removed, so the
        # copy left behind is still listed (and can be retried).
        problems = []
        if request.query_params.get('remote') in ('1', 'true'):
            cfg = BackupSettings.load()
            if backup.remote_file_id and backup.remote_status == 'ok':
                from apps.backups.gdrive import Drive, DriveError
                try:
                    Drive(cfg).delete(backup.remote_file_id)
                    backup.remote_status = 'deleted'
                except DriveError as e:
                    problems.append(f'Drive: {e}')
            if backup.nas_path and backup.nas_status == 'ok':
                from apps.backups.nas import Nas, NasError
                try:
                    nas = Nas(cfg)
                    try:
                        nas.delete(backup.nas_path)
                    finally:
                        nas.close()
                    backup.nas_status = 'deleted'
                except NasError as e:
                    problems.append(f'NAS: {e}')
        if problems:
            backup.local_deleted = True
            backup.save(update_fields=['local_deleted', 'remote_status', 'nas_status'])
            return Response({'error': 'Removed from this server, but not: ' + '; '.join(problems)}, status=502)
        backup.delete()
        return Response(status=204)


class BackupUploadView(APIView):
    """(Re)send one archive to Google Drive, or to the NAS with {"target": "nas"}."""
    permission_classes = [IsSuperadmin]

    def post(self, request, pk):
        from apps.backups.tasks import upload_backup
        backup = Backup.objects.filter(pk=pk, status__in=['ok', 'partial']).first()
        if not backup:
            return Response({'error': 'Backup not found'}, status=404)
        cfg = BackupSettings.load()
        target = 'nas' if request.data.get('target') == 'nas' else 'gdrive'
        if target == 'nas':
            from apps.backups.nas import is_configured
            if not is_configured(cfg):
                return Response({'error': 'Set up the NAS first'}, status=400)
            backup.nas_status = 'uploading'
            backup.save(update_fields=['nas_status'])
        else:
            if not cfg.gdrive_refresh_token:
                return Response({'error': 'Connect Google Drive first'}, status=400)
            backup.remote_status = 'uploading'
            backup.save(update_fields=['remote_status'])
        upload_backup.delay(backup.pk, target)
        return Response({'queued': True})


class DriveConnectView(APIView):
    """
    POST: start Google sign-in (device flow) -> {user_code, verification_url}.
    PUT: poll; once the admin has approved, stores the refresh token.
    DELETE: disconnect (revokes the token).
    """
    permission_classes = [IsSuperadmin]

    def post(self, request):
        from apps.backups.gdrive import DriveError, start_device_flow
        cfg = BackupSettings.load()
        if not (cfg.gdrive_client_id and cfg.gdrive_client_secret):
            return Response({'error': 'Save the Google OAuth Client ID and Client secret first'}, status=400)
        try:
            flow = start_device_flow(cfg.gdrive_client_id)
        except DriveError as e:
            return Response({'error': str(e)}, status=400)
        cfg.gdrive_device_code = flow['device_code']
        cfg.gdrive_device_expires = timezone.now() + timedelta(seconds=flow.get('expires_in', 1800))
        cfg.save(update_fields=['gdrive_device_code', 'gdrive_device_expires'])
        return Response({'user_code': flow['user_code'],
                         'verification_url': flow.get('verification_url') or flow.get('verification_uri'),
                         'interval': flow.get('interval', 5), 'expires_in': flow.get('expires_in', 1800)})

    def put(self, request):
        from apps.backups.gdrive import Drive, DriveError, poll_device_flow
        cfg = BackupSettings.load()
        device_code = cfg.gdrive_device_code
        if not device_code or not cfg.gdrive_device_expires or cfg.gdrive_device_expires < timezone.now():
            return Response({'state': 'expired'})
        try:
            state, token = poll_device_flow(cfg.gdrive_client_id, cfg.gdrive_client_secret, device_code)
        except DriveError as e:
            return Response({'error': str(e)}, status=400)
        if state != 'ok':
            return Response({'state': state})
        cfg.gdrive_device_code = ''
        cfg.gdrive_refresh_token = token.get('refresh_token', '')
        cfg.gdrive_folder_id = ''
        cfg.gdrive_enabled = True
        cfg.save()
        try:
            drive = Drive(cfg)
            cfg.gdrive_account = drive.about().get('user', {}).get('emailAddress', '')
            drive.ensure_folder()
            cfg.save(update_fields=['gdrive_account'])
        except DriveError as e:
            return Response({'state': 'ok', 'warning': str(e)})
        return Response({'state': 'ok', 'account': cfg.gdrive_account})

    def delete(self, request):
        from apps.backups.gdrive import revoke
        cfg = BackupSettings.load()
        if cfg.gdrive_refresh_token:
            revoke(cfg.gdrive_refresh_token)
        cfg.gdrive_refresh_token = ''
        cfg.gdrive_account = ''
        cfg.gdrive_folder_id = ''
        cfg.gdrive_enabled = False
        cfg.save()
        return Response(status=204)


class DriveTestView(APIView):
    permission_classes = [IsSuperadmin]

    def post(self, request):
        from apps.backups.gdrive import Drive, DriveError
        try:
            drive = Drive(BackupSettings.load())
            about = drive.about()
            drive.ensure_folder()
        except DriveError as e:
            return Response({'ok': False, 'error': str(e)}, status=400)
        q = about.get('storageQuota', {})
        return Response({'ok': True, 'account': about.get('user', {}).get('emailAddress'),
                         'used': int(q.get('usage') or 0), 'limit': int(q['limit']) if q.get('limit') else None})


class NasTestView(APIView):
    """Log in to the NAS and make sure the folder exists and is writable.
    Takes unsaved form values so the admin can test before saving."""
    permission_classes = [IsSuperadmin]

    def post(self, request):
        from types import SimpleNamespace
        from apps.backups.nas import Nas, NasError
        cfg = BackupSettings.load()
        s = SettingsSerializer(cfg, data={k: v for k, v in request.data.items() if k.startswith('nas_')}, partial=True)
        if not s.is_valid():
            return Response({'ok': False, 'error': next(iter(s.errors.values()))[0]}, status=400)
        d = s.validated_data
        trial = SimpleNamespace(nas_mode=d.get('nas_mode', cfg.nas_mode),
                                nas_quickconnect_id=d.get('nas_quickconnect_id', cfg.nas_quickconnect_id),
                                nas_url=d.get('nas_url', cfg.nas_url),
                                nas_username=d.get('nas_username', cfg.nas_username),
                                nas_password=d.get('nas_password') or cfg.nas_password,
                                nas_folder=d.get('nas_folder', cfg.nas_folder),
                                nas_verify_tls=d.get('nas_verify_tls', cfg.nas_verify_tls))
        nas = None
        try:
            nas = Nas(trial)
            info = nas.info()
            # A tiny write+delete: PROPFIND passing only proves read access.
            import tempfile
            from pathlib import Path
            with tempfile.NamedTemporaryFile(prefix='isp-nas-test-') as f:
                f.write(b'ISP billing NAS write test\n')
                f.flush()
                written = nas.upload(Path(f.name), '.isp-billing-write-test')
            nas.delete(written)
        except NasError as e:
            return Response({'ok': False, 'error': str(e)}, status=400)
        finally:
            if nas:
                nas.close()
        return Response({'ok': True, **info})


class MigrationCheckView(APIView):
    """Pre-flight for moving to a new host, as seen from this server."""
    permission_classes = [IsSuperadmin]

    def get(self, request):
        from apps.backups.preflight import run_checks
        return Response(run_checks(skip_routers=request.query_params.get('skip_routers') in ('1', 'true')))
