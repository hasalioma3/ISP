"""
Checks that matter before (and right after) moving to a new host, run from
the server itself -- so on the new host they answer "can THIS machine reach
the routers, the database, M-Pesa, WhatsApp?". Used by the Backups page and
by `manage.py migration_check` (which migrate_host.sh runs on the new host
before cutting over).
"""
import shutil
import socket
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone


def _tcp(host, port, timeout=4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ''
    except OSError as e:
        return False, str(e)


def run_checks(skip_routers=False):
    from apps.backups.models import Backup, BackupSettings
    from apps.network.models import Router
    checks = []

    def add(name, ok, detail='', level='error'):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail, 'level': 'ok' if ok else level})

    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
        add('Database', True, connection.vendor)
    except Exception as e:
        add('Database', False, str(e))

    if not skip_routers:
        for r in Router.objects.all().order_by('name'):
            ok, err = _tcp(r.ip_address, r.port)
            add(f'Router API: {r.name} ({r.ip_address}:{r.port})', ok,
                'reachable' if ok else f'{err} -- check the router firewall / WAN management access allows this '
                                       "server's IP, and the VPN/route to the router exists on this host")

    ok, err = _tcp('api.safaricom.co.ke', 443)
    add('M-Pesa (Daraja) reachable', ok, err, level='warn')
    ok, err = _tcp('www.googleapis.com', 443)
    add('Google APIs reachable', ok, err, level='warn')

    try:
        import requests
        r = requests.get('http://whatsapp_service:3000/status', timeout=3)
        st = r.json()
        add('WhatsApp service', st.get('connected'), 'connected' if st.get('connected') else
            'not connected -- scan the QR code in Settings -> Notifications (or restore the session)', level='warn')
    except Exception as e:
        add('WhatsApp service', False, f'unreachable: {e}', level='warn')

    cfg = BackupSettings.load()
    last = Backup.objects.filter(status__in=['ok', 'partial']).first()
    add('Recent backup (last 24 h)', last and last.created_at > timezone.now() - timedelta(hours=24),
        f'last: {timezone.localtime(last.created_at):%d %b %H:%M}' if last else 'none yet', level='warn')
    add('Backups encrypted (secrets included)', bool(cfg.encryption_passphrase),
        '' if cfg.encryption_passphrase else 'without a passphrase, backups leave out the env and WhatsApp login',
        level='warn')
    add('Google Drive connected', bool(cfg.gdrive_refresh_token), cfg.gdrive_account, level='warn')
    if cfg.nas_enabled and cfg.nas_mode == 'quickconnect' and cfg.nas_quickconnect_id:
        # The full resolve (direct or relay) is what the NAS "Test" button
        # does; here it's enough that Synology's directory is reachable.
        ok, err = _tcp('global.quickconnect.to', 443)
        add(f'NAS via QuickConnect ({cfg.nas_quickconnect_id})', ok, err or 'QuickConnect reachable', level='warn')
    elif cfg.nas_enabled and cfg.nas_url:
        from urllib.parse import urlsplit
        u = urlsplit(cfg.nas_url)
        ok, err = _tcp(u.hostname, u.port or (443 if u.scheme == 'https' else 80))
        add(f'NAS reachable ({u.netloc})', ok, err or 'reachable', level='warn')

    from apps.backups.runner import backup_dir
    free = shutil.disk_usage(backup_dir()).free
    add('Free disk space', free > 2 * 1024 ** 3, f'{free / 1024 ** 3:.1f} GB free', level='warn')

    add('Encryption key set', bool(getattr(settings, 'NOTIFICATIONS_ENCRYPTION_KEY', '')),
        'NOTIFICATIONS_ENCRYPTION_KEY must be the SAME on the new host, or stored credentials restore blank')
    return {'checks': checks, 'ok': all(c['ok'] or c['level'] == 'warn' for c in checks),
            'host': socket.gethostname(), 'checked_at': timezone.now()}
