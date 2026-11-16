import json
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.backups.models import Backup, BackupSettings
from apps.customers.models import Customer

TMP = tempfile.mkdtemp(prefix='isp-backup-test-')


@override_settings(BACKUP_DIR=TMP, NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                   MEDIA_ROOT=tempfile.mkdtemp(), WHATSAPP_AUTH_BACKUP_DIR='/nonexistent')
class BackupTests(TransactionTestCase):
    def setUp(self):
        self.root = Customer.objects.create(username='root', is_staff=True, is_superuser=True)
        cfg = BackupSettings.load()
        cfg.include_routers = False
        cfg.save()

    def make(self):
        from apps.backups import runner
        b = Backup.objects.create(kind='manual')
        return runner.run(b)

    def test_crypto_roundtrip_and_tamper(self):
        from apps.backups.crypto import DecryptionError, decrypt_file, encrypt_file
        d = Path(tempfile.mkdtemp())
        (d / 'a').write_bytes(b'x' * (2 * 1024 * 1024 + 17))
        encrypt_file(d / 'a', d / 'a.enc', 'correct horse battery')
        decrypt_file(d / 'a.enc', d / 'b', 'correct horse battery')
        self.assertEqual((d / 'a').read_bytes(), (d / 'b').read_bytes())
        with self.assertRaises(DecryptionError):
            decrypt_file(d / 'a.enc', d / 'c', 'wrong passphrase!')
        data = (d / 'a.enc').read_bytes()
        (d / 't.enc').write_bytes(data[:-100])  # truncated
        with self.assertRaises(DecryptionError):
            decrypt_file(d / 't.enc', d / 'c', 'correct horse battery')

    def test_plain_backup_has_db_and_manifest_but_no_secrets(self):
        b = self.make()
        self.assertIn(b.status, ('ok', 'partial'))
        self.assertTrue(any('passphrase' in w for w in b.warnings))
        with tarfile.open(Path(TMP) / b.filename) as tar:
            names = tar.getnames()
            manifest = json.load(tar.extractfile('manifest.json'))
        self.assertIn('database/database.sqlite3', names)
        self.assertFalse(any(n.startswith('secrets') for n in names))
        self.assertEqual(manifest['contents']['counts']['staff'], 1)

    def test_encrypted_backup_includes_env_and_restores(self):
        from django.core.management import call_command
        from apps.backups.crypto import decrypt_file
        cfg = BackupSettings.load()
        cfg.encryption_passphrase = 'a long passphrase'
        cfg.save()
        b = self.make()
        self.assertTrue(b.encrypted and b.filename.endswith('.enc'))
        plain = Path(tempfile.mkdtemp()) / 'x.tar.gz'
        decrypt_file(Path(TMP) / b.filename, plain, 'a long passphrase')
        with tarfile.open(plain) as tar:
            self.assertIn('secrets/env', tar.getnames())
        call_command('restore_backup', str(Path(TMP) / b.filename), passphrase='a long passphrase',
                     skip_db=True, yes=True, stdout=MagicMock())

    def test_routers_are_backed_up_and_offline_ones_warned(self):
        from apps.network.models import Router
        cfg = BackupSettings.load()
        cfg.include_routers = True
        cfg.save()
        with patch('apps.billing.signals.sync_plan_to_routers.delay'):
            Router.objects.create(name='Main', ip_address='10.0.0.1', username='a', password='b')
            Router.objects.create(name='Far', ip_address='10.0.0.2', username='a', password='b')

        def fake(router):
            if router.name == 'Far':
                return {'name': 'Far', 'ok': False, 'files': {}, 'warnings': [], 'error': 'router is offline'}
            return {'name': 'Main', 'ok': True, 'files': {'config.json': b'{}', 'export.rsc': b'/ip address'},
                    'warnings': [], 'error': '', 'version': '7.15'}
        with patch('apps.backups.routers.backup_router', side_effect=fake):
            b = self.make()
        self.assertEqual(b.status, 'partial')
        with tarfile.open(Path(TMP) / b.filename) as tar:
            self.assertTrue(any(n.endswith('export.rsc') for n in tar.getnames()))
        self.assertTrue(any('Far' in w for w in b.warnings))

    def test_router_export_survives_empty_replies(self):
        """RouterOS 7.18+ returns [{}] for a search with no match; that used to
        abort the export with KeyError 'id'."""
        from types import SimpleNamespace
        from apps.backups.routers import backup_router
        scripts, files = MagicMock(), MagicMock()
        scripts.get.return_value = [{}]
        files.get.side_effect = lambda **q: [{}] if q else [
            {'id': '*1', 'name': 'isp-billing-export.rsc', 'size': '10'},
            {'id': '*2', 'name': 'isp-billing.backup', 'size': '20'}]
        resources = {'/system/script': scripts, '/file': files,
                     '/system/resource': MagicMock(get=lambda: [{'version': '7.19.1'}])}
        api = MagicMock()
        api.get_resource.side_effect = lambda m: resources.get(m, MagicMock(get=lambda **q: [{}]))
        svc = MagicMock()
        svc._get_connection.return_value.get_api.return_value = api
        ftp = MagicMock()
        ftp.retrbinary.side_effect = lambda cmd, write: write(b'data')
        router = SimpleNamespace(name='T', ip_address='10.0.0.9', username='u', password='p', port=8728, use_ssl=False)
        with patch('apps.network.services.mikrotik_service.MikroTikService', return_value=svc), \
             patch('apps.network.services.router_status.known_offline', return_value=False), \
             patch('apps.backups.routers.ftplib.FTP', return_value=ftp), \
             patch('apps.backups.routers.time.sleep'):
            res = backup_router(router)
        self.assertEqual(res['warnings'], [])
        scripts.add.assert_called_once()
        self.assertIn('show-sensitive', scripts.add.call_args.kwargs['source'])
        self.assertEqual(set(res['files']), {'config.json', 'export.rsc', 'router.backup'})

    def test_prune_keeps_newest(self):
        from apps.backups import runner
        cfg = BackupSettings.load()
        cfg.keep_local = 2
        cfg.save()
        made = [self.make() for _ in range(3)]
        runner.prune()
        made[0].refresh_from_db()
        self.assertTrue(made[0].local_deleted)
        self.assertFalse((Path(TMP) / made[0].filename).exists())
        made[2].refresh_from_db()
        self.assertFalse(made[2].local_deleted)

    def test_drive_upload_resumes(self):
        from apps.backups import runner
        cfg = BackupSettings.load()
        cfg.gdrive_client_id, cfg.gdrive_client_secret, cfg.gdrive_refresh_token = 'cid', 'sec', 'rt'
        cfg.gdrive_folder_id = 'folder1'
        cfg.save()
        b = self.make()
        token = MagicMock(status_code=200, json=lambda: {'access_token': 'at'})
        folder = MagicMock(status_code=200, json=lambda: {'id': 'folder1', 'trashed': False})
        init = MagicMock(status_code=200, headers={'Location': 'https://upload/session'})
        done = MagicMock(status_code=200, json=lambda: {'id': 'drive-file-1'})
        with patch('apps.backups.gdrive.requests.post', side_effect=[token, init]), \
             patch('apps.backups.gdrive.requests.get', return_value=folder), \
             patch('apps.backups.gdrive.requests.put', return_value=done):
            runner.upload(b)
        self.assertEqual((b.remote_status, b.remote_file_id), ('ok', 'drive-file-1'))

    def _nas_cfg(self):
        cfg = BackupSettings.load()
        cfg.nas_enabled, cfg.nas_url, cfg.nas_username, cfg.nas_password = True, 'https://nas.lan:5006', 'isp', 'pw'
        cfg.nas_folder, cfg.nas_mode = '/backups/isp', 'webdav'
        cfg.save()
        return cfg

    def _qc_cfg(self):
        cfg = BackupSettings.load()
        cfg.nas_enabled, cfg.nas_mode, cfg.nas_quickconnect_id = True, 'quickconnect', 'mynas'
        cfg.nas_username, cfg.nas_password, cfg.nas_folder = 'isp', 'pw', '/backups/isp'
        cfg.save()
        return cfg

    def _fake_synology(self, otp=False):
        """A NAS with no direct route (only reachable through the relay), and its File Station API."""
        import requests as rq
        from apps.backups import nas
        nas._resolved.clear()
        seen = {'serv': [], 'calls': [], 'uploaded': b''}
        apis = {k: {'path': 'auth.cgi' if k == 'SYNO.API.Auth' else 'entry.cgi', 'minVersion': 1, 'maxVersion': 7}
                for k in nas.WANT}

        def serv(url, data=None, **kw):
            body = json.loads(data)
            seen['serv'].append(body['command'])
            if body['command'] == 'get_server_info':
                return MagicMock(json=lambda: {'errno': 0, 'server': {'interface': [{'ip': '192.168.1.9'}], 'ddns': 'NULL'},
                                               'service': {'port': 5001}, 'smartdns': {'host': 'mynas.direct.quickconnect.to'},
                                               'env': {'control_host': 'ke.quickconnect.to', 'relay_region': 'za1'}})
            return MagicMock(json=lambda: {'errno': 0, 'env': {'relay_region': 'za1'}})

        def get(session, url, params=None, **kw):
            if not url.startswith('https://mynas.za1.quickconnect.to'):
                raise rq.exceptions.ConnectionError('no route')
            if params.get('query') == 'SYNO.API.Auth':
                return MagicMock(status_code=200, json=lambda: {'success': True, 'data': {}})
            return MagicMock(status_code=200, json=lambda: {'success': True, 'data': apis})

        def post(session, url, data=None, params=None, **kw):
            fields = params if params and 'api' in params else data
            api, method = fields['api'], fields['method']
            seen['calls'].append((api, method))
            if api == 'SYNO.API.Auth' and method == 'login':
                if otp:
                    return MagicMock(json=lambda: {'success': False, 'error': {'code': 403}})
                return MagicMock(json=lambda: {'success': True, 'data': {'sid': 'S1'}})
            if api == 'SYNO.FileStation.Upload':
                self.assertEqual(params['_sid'], 'S1')
                seen['uploaded'] = data.read()
            if api == 'SYNO.FileStation.List':
                return MagicMock(json=lambda: {'success': True, 'data': {'files': [{'additional': {'size': seen['size']}}]}})
            return MagicMock(json=lambda: {'success': True, 'data': {}})
        return seen, serv, get, post

    def test_nas_upload_streams_to_part_then_renames_and_prunes(self):
        from apps.backups import runner
        cfg = self._nas_cfg()
        cfg.keep_nas = 1
        cfg.save()
        calls = []

        def fake(method, url, **kw):
            calls.append((method, url, kw.get('headers', {})))
            if method == 'PROPFIND':
                return MagicMock(status_code=207, content=b'<d:multistatus xmlns:d="DAV:"/>')
            return MagicMock(status_code={'PUT': 201, 'MOVE': 201, 'DELETE': 204}[method])
        with patch('apps.backups.nas.requests.Session.request', side_effect=fake):
            first = self.make()
            runner.upload_nas(first)
            second = self.make()
            runner.upload_nas(second)
            runner.prune()
        self.assertEqual((second.nas_status, second.nas_path), ('ok', f'/backups/isp/{second.filename}'))
        put = [c for c in calls if c[0] == 'PUT']
        self.assertTrue(put[0][1].endswith('.part'))
        move = [c for c in calls if c[0] == 'MOVE'][0]
        self.assertTrue(move[2]['Destination'].endswith(first.filename))
        first.refresh_from_db()
        self.assertEqual(first.nas_status, 'deleted')  # keep_nas=1
        self.assertIn(('DELETE', f'https://nas.lan:5006/backups/isp/{first.filename}'), [c[:2] for c in calls])

    def test_nas_failure_is_recorded_and_admins_told(self):
        from apps.backups.tasks import run_backup
        self._nas_cfg()
        b = Backup.objects.create(kind='manual')
        resp = MagicMock(status_code=401, text='')
        with patch('apps.backups.nas.requests.Session.request', return_value=resp), \
             patch('apps.notifications.admin_emails.notify_admins') as notify:
            run_backup(b.pk)
        b.refresh_from_db()
        self.assertIn(b.status, ('ok', 'partial'))  # the local backup is still good
        self.assertEqual(b.nas_status, 'failed')
        self.assertIn('username or password', b.nas_error)
        self.assertIn('NAS upload failed', notify.call_args[0][2])

    def test_quickconnect_falls_back_to_relay_and_streams_upload(self):
        from apps.backups import runner
        self._qc_cfg()
        b = self.make()
        seen, serv, get, post = self._fake_synology()
        seen['size'] = b.size
        with patch('apps.backups.nas.requests.post', side_effect=serv), \
             patch('apps.backups.nas.requests.Session.get', autospec=True, side_effect=get), \
             patch('apps.backups.nas.requests.Session.post', autospec=True, side_effect=post), \
             patch('apps.backups.nas.time.sleep'):
            runner.upload_nas(b)
        self.assertEqual((b.nas_status, b.nas_error), ('ok', ''))
        self.assertEqual(b.nas_path, f'/backups/isp/{b.filename}')
        self.assertEqual(seen['serv'], ['get_server_info', 'request_tunnel'])
        self.assertIn(('SYNO.FileStation.Rename', 'rename'), seen['calls'])
        self.assertIn(('SYNO.API.Auth', 'logout'), seen['calls'])
        # The multipart body carried the whole archive, byte for byte.
        self.assertIn((Path(TMP) / b.filename).read_bytes(), seen['uploaded'])
        self.assertIn(b.filename.encode() + b'.part', seen['uploaded'])

    def test_quickconnect_two_factor_account_is_explained(self):
        from apps.backups import runner
        self._qc_cfg()
        b = self.make()
        seen, serv, get, post = self._fake_synology(otp=True)
        with patch('apps.backups.nas.requests.post', side_effect=serv), \
             patch('apps.backups.nas.requests.Session.get', autospec=True, side_effect=get), \
             patch('apps.backups.nas.requests.Session.post', autospec=True, side_effect=post), \
             patch('apps.backups.nas.time.sleep'):
            runner.upload_nas(b)
        self.assertEqual(b.nas_status, 'failed')
        self.assertIn('2-step verification', b.nas_error)

    def test_quickconnect_id_normalised(self):
        from apps.backups.nas import NasError, normalize_quickconnect_id as n
        for text in ('mynas', 'https://quickconnect.to/mynas', 'quickconnect.to/mynas/', 'mynas.quickconnect.to',
                     'https://mynas.za1.quickconnect.to/'):
            self.assertEqual(n(text), 'mynas')
        with self.assertRaises(NasError):
            n('https://example.com')
        client = APIClient()
        client.force_authenticate(self.root)
        res = client.patch('/api/backups/settings/', {'nas_mode': 'quickconnect', 'nas_quickconnect_id': 'QuickConnect.to/MyNas',
                                                      'nas_username': 'isp', 'nas_password': 'pw', 'nas_enabled': True},
                           format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['nas_quickconnect_id'], 'MyNas')

    def test_nas_settings_validation(self):
        client = APIClient()
        client.force_authenticate(self.root)
        res = client.patch('/api/backups/settings/', {'nas_enabled': True}, format='json')
        self.assertEqual(res.status_code, 400)
        client.patch('/api/backups/settings/', {'nas_mode': 'webdav'}, format='json')
        res = client.patch('/api/backups/settings/', {'nas_url': 'myname.quickconnect.to'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = client.patch('/api/backups/settings/', {'nas_url': 'nas.lan:5006/', 'nas_username': 'isp',
                                                      'nas_password': 'pw', 'nas_folder': 'backups/isp/',
                                                      'nas_enabled': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['nas_url'], res.data['nas_folder']), ('https://nas.lan:5006', '/backups/isp'))
        self.assertNotIn('nas_password', res.data)
        self.assertTrue(res.data['nas_password_set'])

    def test_schedule_gate(self):
        from apps.backups.tasks import scheduled_backup
        cfg = BackupSettings.load()
        from django.utils import timezone
        cfg.hour = (timezone.localtime().hour + 1) % 24
        cfg.save()
        self.assertIsNone(scheduled_backup())
        with patch('apps.backups.tasks.run_backup.delay') as run:
            self.assertIsNotNone(scheduled_backup(force=True))
            run.assert_called_once()
            self.assertIsNone(scheduled_backup())  # a backup is "running" -> not stacked
        self.assertEqual(Backup.objects.filter(kind='scheduled').count(), 1)

    def test_api_superadmin_only_and_secrets_write_only(self):
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='ops', is_staff=True, role='admin'))
        self.assertEqual(client.get('/api/backups/').status_code, 403)
        client.force_authenticate(self.root)
        res = client.patch('/api/backups/settings/', {'encryption_passphrase': 'super secret pass', 'hour': 3}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('encryption_passphrase', res.data)
        self.assertTrue(res.data['encryption_passphrase_set'])
        # Blank keeps it
        client.patch('/api/backups/settings/', {'encryption_passphrase': ''}, format='json')
        self.assertEqual(BackupSettings.load().encryption_passphrase, 'super secret pass')
        with patch('apps.backups.tasks.run_backup.delay'):
            self.assertEqual(client.post('/api/backups/').status_code, 201)
            self.assertEqual(client.post('/api/backups/').status_code, 409)
        self.assertEqual(client.get('/api/backups/migration-check/', {'skip_routers': 1}).status_code, 200)
