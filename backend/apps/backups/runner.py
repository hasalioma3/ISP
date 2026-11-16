"""
Builds one backup archive: everything needed to bring the system back on
a new host.

    manifest.json                what's inside, versions, counts
    database/database.dump       pg_dump custom format (or database.sqlite3)
    routers/<name>/...           see apps.backups.routers
    media/...                    uploaded logos, receipts, attachments
    secrets/env                  the server's env (encrypted archives only)
    secrets/whatsapp/...         the WhatsApp login (encrypted archives only)

Written to BACKUP_DIR as .tar.gz, or .tar.gz.enc when a passphrase is set
(apps.backups.crypto). Then copied to Google Drive and/or a Synology NAS
when those are set up, and old archives pruned everywhere.
"""
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.backups.models import Backup, BackupSettings

logger = logging.getLogger('backups')

ENV_SKIP = re.compile(r'^(PATH|HOME|HOSTNAME|LANG|LC_|GPG_KEY|PYTHON|PWD|OLDPWD|SHLVL|TERM|_|DEBIAN_FRONTEND|PIP_)')


def backup_dir():
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(text):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', text).strip('-')[:60] or 'router'


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def dump_database(work):
    db = settings.DATABASES['default']
    if 'sqlite' in db['ENGINE']:
        dst = work / 'database.sqlite3'
        # Through Django's own connection (sqlite3's online backup API), so
        # it's a consistent copy even while the app is writing.
        connection.ensure_connection()
        out = sqlite3.connect(str(dst))
        with out:
            connection.connection.backup(out)
        out.close()
        return dst, {'engine': 'sqlite'}
    dst = work / 'database.dump'
    env = {**os.environ, 'PGPASSWORD': db.get('PASSWORD') or ''}
    cmd = ['pg_dump', '-Fc', '--no-password', '-h', db.get('HOST') or 'localhost', '-p', str(db.get('PORT') or 5432),
           '-U', db.get('USER') or '', '-d', db['NAME'], '-f', str(dst)]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f'pg_dump failed: {proc.stderr.strip()[:500]}')
    with connection.cursor() as cur:
        cur.execute('SHOW server_version')
        version = cur.fetchone()[0]
    return dst, {'engine': 'postgresql', 'name': db['NAME'], 'server_version': version}


def _counts():
    from apps.billing.models import Subscription, Transaction, Voucher
    from apps.customers.models import Customer
    from apps.network.models import Router
    return {
        'customers': Customer.objects.filter(is_staff=False).count(),
        'staff': Customer.objects.filter(is_staff=True).count(),
        'subscriptions': Subscription.objects.count(),
        'transactions': Transaction.objects.count(),
        'vouchers': Voucher.objects.count(),
        'routers': Router.objects.count(),
    }


def run(backup):
    cfg = BackupSettings.load()
    encrypt = bool(cfg.encryption_passphrase)
    stamp = timezone.localtime(backup.created_at).strftime('%Y%m%d-%H%M%S')
    tenant = _slug(os.environ.get('ISP_COMPOSE_NAME') or settings.DATABASES['default'].get('NAME') or 'isp')
    base = f'isp-backup-{tenant}-{stamp}'
    root = backup_dir()
    work = root / f'.work-{backup.pk}'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    warnings, contents = [], {}
    archive = root / f'{base}.tar.gz'
    try:
        with tarfile.open(archive, 'w:gz', compresslevel=6) as tar:
            dump, info = dump_database(work)
            tar.add(dump, arcname=f'database/{dump.name}')
            info['size'] = dump.stat().st_size
            contents['database'] = info
            dump.unlink()

            if cfg.include_routers:
                from apps.network.models import Router
                from apps.backups.routers import backup_router
                routers = []
                for router in Router.objects.filter(is_active=True) if hasattr(Router, 'is_active') else Router.objects.all():
                    res = backup_router(router)
                    folder = f'routers/{_slug(router.name)}-{router.pk}'
                    for arc, data in res['files'].items():
                        p = work / 'r.tmp'
                        p.write_bytes(data)
                        tar.add(p, arcname=f'{folder}/{arc}')
                        p.unlink()
                    routers.append({'name': router.name, 'ip': router.ip_address, 'ok': res['ok'],
                                    'files': sorted(res['files']), 'version': res.get('version', ''),
                                    'error': res['error'], 'warnings': res['warnings']})
                    if not res['ok']:
                        warnings.append(f"Router {router.name}: {res['error']}")
                    warnings += [f'Router {router.name}: {w}' for w in res['warnings']]
                contents['routers'] = routers

            if cfg.include_media and Path(settings.MEDIA_ROOT).is_dir():
                media = Path(settings.MEDIA_ROOT)
                n = sum(1 for p in media.rglob('*') if p.is_file())
                tar.add(media, arcname='media')
                contents['media_files'] = n

            if cfg.include_secrets:
                if not encrypt:
                    warnings.append('Server secrets and the WhatsApp login were left out: set an encryption '
                                    'passphrase to include them (needed for a complete restore).')
                else:
                    env = ''.join(f'{k}={v}\n' for k, v in sorted(os.environ.items()) if not ENV_SKIP.match(k))
                    p = work / 'env'
                    p.write_text(env)
                    tar.add(p, arcname='secrets/env')
                    p.unlink()
                    contents['secrets'] = ['env']
                    wa = Path(settings.WHATSAPP_AUTH_BACKUP_DIR)
                    if wa.is_dir() and any(wa.iterdir()):
                        tar.add(wa, arcname='secrets/whatsapp')
                        contents['secrets'].append('whatsapp')

            contents['counts'] = _counts()
            manifest = {
                'format': 1, 'created_at': backup.created_at.isoformat(), 'kind': backup.kind,
                'tenant': tenant, 'contents': contents, 'warnings': warnings,
                'app_version': os.environ.get('GIT_COMMIT', ''),
            }
            p = work / 'manifest.json'
            p.write_text(json.dumps(manifest, indent=2, default=str))
            tar.add(p, arcname='manifest.json')

        final = archive
        if encrypt:
            from apps.backups.crypto import encrypt_file
            final = root / f'{base}.tar.gz.enc'
            encrypt_file(archive, final, cfg.encryption_passphrase)
            archive.unlink()
        backup.filename = final.name
        backup.size = final.stat().st_size
        backup.sha256 = _sha256(final)
        backup.encrypted = encrypt
        backup.contents = contents
        backup.warnings = warnings
        backup.status = 'partial' if warnings else 'ok'
    except Exception as e:
        logger.exception('Backup %s failed', backup.pk)
        backup.status = 'failed'
        backup.error = str(e)[:2000]
        backup.contents = contents
        backup.warnings = warnings
        for leftover in (archive, root / f'{base}.tar.gz.enc'):
            leftover.unlink(missing_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        backup.finished_at = timezone.now()
        backup.save()
    return backup


def path_of(backup):
    return backup_dir() / backup.filename if backup.filename else None


def upload(backup):
    from apps.backups.gdrive import Drive
    cfg = BackupSettings.load()
    path = path_of(backup)
    if not path or not path.exists():
        backup.remote_status, backup.remote_error = 'failed', 'the archive is no longer on this server'
        backup.save(update_fields=['remote_status', 'remote_error'])
        return backup
    backup.remote_status, backup.remote_error = 'uploading', ''
    backup.save(update_fields=['remote_status', 'remote_error'])
    try:
        backup.remote_file_id = Drive(cfg).upload(path, backup.filename)
        backup.remote_status = 'ok'
    except Exception as e:
        logger.exception('Drive upload of backup %s failed', backup.pk)
        backup.remote_status, backup.remote_error = 'failed', str(e)[:2000]
    backup.save(update_fields=['remote_status', 'remote_error', 'remote_file_id'])
    return backup


def upload_nas(backup):
    from apps.backups.nas import Nas
    path = path_of(backup)
    if not path or not path.exists():
        backup.nas_status, backup.nas_error = 'failed', 'the archive is no longer on this server'
        backup.save(update_fields=['nas_status', 'nas_error'])
        return backup
    backup.nas_status, backup.nas_error = 'uploading', ''
    backup.save(update_fields=['nas_status', 'nas_error'])
    try:
        nas = Nas(BackupSettings.load())
        try:
            backup.nas_path = nas.upload(path, backup.filename)
        finally:
            nas.close()
        backup.nas_status = 'ok'
    except Exception as e:
        logger.exception('NAS upload of backup %s failed', backup.pk)
        backup.nas_status, backup.nas_error = 'failed', str(e)[:2000]
    backup.save(update_fields=['nas_status', 'nas_error', 'nas_path'])
    return backup


def prune():
    """Keep the newest keep_local archives on disk, keep_remote on Drive, keep_nas on the NAS."""
    cfg = BackupSettings.load()
    good = Backup.objects.filter(status__in=['ok', 'partial'])
    for old in good.filter(local_deleted=False)[cfg.keep_local:]:
        p = path_of(old)
        if p:
            p.unlink(missing_ok=True)
        old.local_deleted = True
        old.save(update_fields=['local_deleted'])
    on_drive = good.filter(remote_status='ok').exclude(remote_file_id='')
    stale = list(on_drive[cfg.keep_remote:])
    if stale and cfg.gdrive_refresh_token:
        from apps.backups.gdrive import Drive
        try:
            drive = Drive(cfg)
            for old in stale:
                drive.delete(old.remote_file_id)
                old.remote_status = 'deleted'
                old.save(update_fields=['remote_status'])
        except Exception:
            logger.exception('Pruning Drive backups failed')
    on_nas = good.filter(nas_status='ok').exclude(nas_path='')
    stale = list(on_nas[cfg.keep_nas:])
    from apps.backups.nas import Nas, is_configured
    if stale and is_configured(cfg):
        try:
            nas = Nas(cfg)
            try:
                for old in stale:
                    nas.delete(old.nas_path)
                    old.nas_status = 'deleted'
                    old.save(update_fields=['nas_status'])
            finally:
                nas.close()
        except Exception:
            logger.exception('Pruning NAS backups failed')
    # Archives of failed runs, and stuck runs (worker killed mid-backup).
    Backup.objects.filter(status='running', created_at__lt=timezone.now() - timedelta(hours=6)).update(
        status='failed', error='did not finish (the worker restarted or was stopped)', finished_at=timezone.now())
