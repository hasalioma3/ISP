"""
Per-router configuration backup, over the RouterOS API plus FTP (Python's
stdlib ftplib -- no new dependency):

1. config.json -- the important menus read over the API (interfaces,
   addresses, pools, DHCP, hotspot, PPP, firewall, NAT, queues, users...).
   Always works when the API does; readable, but not a script you can
   paste back in.
2. export.rsc -- a full `/export` (with secrets on RouterOS 7), made on the
   router by a temporary script and fetched over FTP. Paste-able onto a
   reset router.
3. router.backup -- RouterOS's own binary backup (`/system backup save`),
   restorable on the same model. Also left on the router's flash as
   isp-billing.backup (one file, overwritten each time, so flash never
   fills up).

(2) and (3) need the router's FTP service reachable from this server; when
it isn't, the archive still has (1) and the binary backup stays on the
router, and the warning says so.
"""
import ftplib
import io
import json
import logging
import time

logger = logging.getLogger('backups')

MENUS = [
    '/system/identity', '/system/resource', '/system/routerboard', '/system/clock', '/system/ntp/client',
    '/interface', '/interface/bridge', '/interface/bridge/port', '/interface/vlan', '/interface/ethernet',
    '/interface/wireless', '/interface/pppoe-client', '/interface/list', '/interface/list/member',
    '/ip/address', '/ip/route', '/ip/dns', '/ip/pool', '/ip/dhcp-server', '/ip/dhcp-server/network',
    '/ip/dhcp-server/lease', '/ip/dhcp-client', '/ip/hotspot', '/ip/hotspot/profile', '/ip/hotspot/user/profile',
    '/ip/hotspot/walled-garden', '/ip/hotspot/walled-garden/ip', '/ip/hotspot/ip-binding',
    '/ppp/profile', '/ppp/secret', '/interface/pppoe-server/server',
    '/ip/firewall/filter', '/ip/firewall/nat', '/ip/firewall/mangle', '/ip/firewall/address-list',
    '/queue/simple', '/queue/tree', '/queue/type', '/ip/service', '/user', '/system/scheduler', '/system/script',
    '/snmp', '/radius',
]
EXPORT_NAME = 'isp-billing-export'
BACKUP_NAME = 'isp-billing'


def _items(res, **query):
    """res.get(**query) without the placeholder item. RouterOS 7.18+ answers a
    search that matches nothing with an empty reply, which routeros-api hands
    back as [{}] -- indexing that for 'id' is the KeyError: 'id' it caused."""
    return [item for item in res.get(**query) if item.get('id')]


def _find_file(files_res, suffix):
    for f in _items(files_res):
        name = f.get('name') or ''
        if name.endswith(suffix):
            return name, int(f.get('size') or 0)
    return None, 0


def _wait_for(files_res, suffix, timeout=25):
    deadline = time.time() + timeout
    last = -1
    while time.time() < deadline:
        name, size = _find_file(files_res, suffix)
        if name and size and size == last:
            return name
        last = size if name else -1
        time.sleep(1.5)
    name, _ = _find_file(files_res, suffix)
    return name


def backup_router(router):
    """Returns {'name', 'ok', 'files': {arcname: bytes}, 'warnings': [...], 'error'}."""
    from apps.network.services.mikrotik_service import MikroTikService
    from apps.network.services.router_status import known_offline

    out = {'name': router.name, 'ip': router.ip_address, 'ok': False, 'files': {}, 'warnings': [], 'error': ''}
    if known_offline(router):
        out['error'] = 'router is offline'
        return out
    svc = MikroTikService(host=router.ip_address, username=router.username, password=router.password,
                          port=router.port, use_ssl=router.use_ssl)
    try:
        conn = svc._get_connection()
        api = conn.get_api()
    except Exception as e:
        out['error'] = f'could not connect: {e}'
        return out
    try:
        dump = {}
        for menu in MENUS:
            try:
                dump[menu] = api.get_resource(menu).get()
            except Exception as e:  # menu missing on this model/version
                dump[menu] = {'_error': str(e)[:200]}
        out['files']['config.json'] = json.dumps(dump, indent=1, default=str).encode()
        out['ok'] = True
        version = ''
        res = dump.get('/system/resource')
        if isinstance(res, list) and res:
            version = res[0].get('version', '')
        out['version'] = version

        files_res = api.get_resource('/file')
        scripts = api.get_resource('/system/script')
        # Fresh export + binary backup on the router.
        try:
            for s in _items(scripts, name=EXPORT_NAME):
                scripts.remove(id=s['id'])
            source = f'/export file={EXPORT_NAME}' + (' show-sensitive' if version.startswith('7') else '')
            scripts.add(name=EXPORT_NAME, source=source)
            scripts.call('run', {'number': EXPORT_NAME})
        except Exception as e:
            out['warnings'].append(f'export did not run: {e}')
        try:
            api.get_resource('/system/backup').call('save', {'name': BACKUP_NAME, 'dont-encrypt': 'yes'})
        except Exception as e:
            out['warnings'].append(f'binary backup did not save: {e}')
        rsc = _wait_for(files_res, f'{EXPORT_NAME}.rsc')
        bkp = _wait_for(files_res, f'{BACKUP_NAME}.backup', timeout=10)
        try:
            for s in _items(scripts, name=EXPORT_NAME):
                scripts.remove(id=s['id'])
        except Exception:
            pass

        wanted = [(rsc, 'export.rsc'), (bkp, 'router.backup')]
        if any(n for n, _ in wanted):
            try:
                ftp = ftplib.FTP()
                ftp.connect(router.ip_address, 21, timeout=15)
                ftp.login(router.username, router.password)
                for remote, arc in wanted:
                    if not remote:
                        continue
                    buf = io.BytesIO()
                    ftp.retrbinary(f'RETR {remote}', buf.write)
                    out['files'][arc] = buf.getvalue()
                ftp.quit()
            except Exception as e:
                out['warnings'].append(
                    f'could not fetch the export/backup files over FTP ({e}); the binary backup is kept on the '
                    f'router as {BACKUP_NAME}.backup -- enable /ip service ftp for this server to include them')
            if rsc:
                try:
                    for f in _items(files_res, name=rsc):
                        files_res.remove(id=f['id'])
                except Exception:
                    pass
        else:
            out['warnings'].append('the router did not produce export/backup files in time')
    except Exception as e:
        out['error'] = str(e)
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
    return out
