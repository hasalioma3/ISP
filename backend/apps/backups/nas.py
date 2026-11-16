"""
Off-site copies on a Synology NAS. Two ways in, same interface
(ensure_folder / info / upload / delete / download / close):

WebDav -- a direct address (https://nas.example.com:5006) to DSM's "WebDAV
  Server" package. Plain HTTPS PUT, streamed from disk. Needs a route to the
  NAS: same LAN, a VPN, or DDNS + a forwarded port. Works with any WebDAV
  server (Nextcloud, QNAP, ...).

FileStation -- a QuickConnect ID. QuickConnect only tunnels DSM's own web
  port, never WebDAV, so this speaks DSM's File Station web API instead --
  the same thing Synology's own apps do over QuickConnect. The ID is resolved
  the way those apps resolve it (_resolve below): ask Synology's directory
  (global.quickconnect.to/Serv.php) where the NAS is, try its direct
  addresses first (LAN, the *.direct.quickconnect.to names, DDNS), and only
  if none answers, open a relay tunnel through Synology's servers
  (https://<id>.<region>.quickconnect.to). No port forwarding, no VPN, no
  DDNS needed. Relayed traffic is speed-limited by Synology, so a big
  archive can take a while; the archive is already encrypted (when a
  passphrase is set) before it ever leaves this server, and the relay hop is
  HTTPS with a valid Synology certificate.

  File Station logins can't answer a 2-step-verification prompt, so the NAS
  account used here must not have 2FA (use a dedicated, limited account).

Why not File Station for direct addresses too: its upload is a multipart
form, and while we stream that ourselves (_MultipartBody), WebDAV is the
simpler, more widely supported thing when there IS a route.

DSM ships a self-signed certificate, hence the verify-TLS switch for direct
addresses; turning it off still encrypts, it just doesn't prove it's your NAS.
The QuickConnect relay is always verified.
"""
import io
import json
import logging
import posixpath
import re
import secrets
import time
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

import requests

logger = logging.getLogger('backups')

# (connect, read) -- reads are generous because a NAS whose disks are asleep
# can take 20-30 s to answer the first request after spinning up.
TIMEOUT = (10, 120)
UPLOAD_TIMEOUT = (10, 900)
PROBE_TIMEOUT = (4, 10)
QC_DIRECTORY = 'global.quickconnect.to'


class NasError(Exception):
    pass


def Nas(cfg):
    """The right client for the configured connection type."""
    if getattr(cfg, 'nas_mode', 'webdav') == 'quickconnect':
        return FileStation(cfg)
    return WebDav(cfg)


def is_configured(cfg):
    if not (cfg.nas_username and cfg.nas_password):
        return False
    return bool(cfg.nas_quickconnect_id if cfg.nas_mode == 'quickconnect' else cfg.nas_url)


def normalize_folder(folder):
    folder = '/' + (folder or '').strip().strip('/')
    if folder == '/':
        raise NasError('Choose a folder on the NAS, starting with a shared folder (e.g. /backups/isp-billing)')
    return folder


QC_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,62}$')


def normalize_quickconnect_id(text):
    """Accepts 'myid', 'myid.quickconnect.to', 'https://quickconnect.to/myid', or a relay URL."""
    text = (text or '').strip()
    if '://' not in text and '/' not in text and '.' not in text:
        qc = text
    else:
        parts = urlsplit(text if '://' in text else 'https://' + text)
        host = (parts.hostname or '').lower()
        path = parts.path.strip('/')
        if host in ('quickconnect.to', 'www.quickconnect.to', 'global.quickconnect.to') and path:
            qc = path.split('/')[0]
        elif host.endswith('.quickconnect.to'):
            qc = host.split('.')[0]
        else:
            qc = ''
    if not QC_ID.match(qc or ''):
        raise NasError('Enter the QuickConnect ID (the part in quickconnect.to/<ID>)')
    return qc


# --------------------------------------------------------------------------
# WebDAV (direct address)
# --------------------------------------------------------------------------

def _explain(resp):
    code = resp.status_code
    if code == 401:
        return 'the NAS rejected the username or password (HTTP 401)'
    if code == 403:
        return ('the NAS account has no write permission on that folder (HTTP 403) -- give it Read/Write on the '
                'shared folder in Control Panel -> Shared Folder -> Edit -> Permissions')
    if code == 404:
        return ('folder not found (HTTP 404) -- the path must start with an existing shared folder, '
                'e.g. /backups/isp-billing')
    if code == 507:
        return 'the NAS is out of space (HTTP 507)'
    return f'HTTP {code}: {resp.text[:200].strip()}'


class WebDav:
    def __init__(self, cfg):
        if not (cfg.nas_url and cfg.nas_username and cfg.nas_password):
            raise NasError('Enter the NAS address, username and password first')
        parts = urlsplit(cfg.nas_url.strip())
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise NasError('The NAS address must look like https://nas.example.com:5006')
        self.base = f'{parts.scheme}://{parts.netloc}'
        self.folder = normalize_folder(cfg.nas_folder)
        self.session = requests.Session()
        self.session.auth = (cfg.nas_username, cfg.nas_password)
        self.session.verify = bool(cfg.nas_verify_tls)
        if not self.session.verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def close(self):
        self.session.close()

    def _url(self, path):
        return self.base + quote(path)

    def _request(self, method, path, timeout=TIMEOUT, **kw):
        try:
            return self.session.request(method, self._url(path), timeout=timeout, **kw)
        except requests.exceptions.SSLError as e:
            raise NasError('The NAS certificate could not be verified (DSM uses a self-signed one by default) -- '
                           'install a Let\'s Encrypt certificate on the NAS, or turn off "Verify certificate". '
                           f'({e.__class__.__name__})')
        except requests.exceptions.ConnectionError as e:
            raise NasError(f'Could not reach the NAS at {self.base} -- is WebDAV Server enabled, the port right, '
                           f'and is there a route/VPN from this server? Or use QuickConnect instead. '
                           f'({e.__class__.__name__})')
        except requests.exceptions.Timeout:
            raise NasError(f'The NAS at {self.base} did not answer in time')

    def ensure_folder(self):
        """MKCOL each level below the shared folder; 405 means it already exists."""
        parts = [p for p in self.folder.split('/') if p]
        # The first part is the shared folder itself -- WebDAV can't create
        # those, and a 404 on it is the clearest error for a typo.
        current = ''
        for i, part in enumerate(parts):
            current += '/' + part
            resp = self._request('PROPFIND', current + '/', headers={'Depth': '0'})
            if resp.status_code in (200, 207):
                continue
            if i == 0 or resp.status_code != 404:
                raise NasError(f'{current}: {_explain(resp)}')
            made = self._request('MKCOL', current + '/')
            if made.status_code not in (201, 405):
                raise NasError(f'Could not create {current}: {_explain(made)}')

    def info(self):
        """Checks the login and folder; returns free/used bytes when the NAS reports them."""
        self.ensure_folder()
        body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                '<d:quota-available-bytes/><d:quota-used-bytes/></d:prop></d:propfind>')
        resp = self._request('PROPFIND', self.folder + '/', headers={'Depth': '0', 'Content-Type': 'application/xml'},
                             data=body)
        out = {'folder': self.folder, 'free': None, 'used': None, 'via': self.base}
        if resp.status_code == 207:
            try:
                tree = ElementTree.fromstring(resp.content)
                for key, tag in (('free', 'quota-available-bytes'), ('used', 'quota-used-bytes')):
                    el = tree.find(f'.//{{DAV:}}{tag}')
                    if el is not None and (el.text or '').strip().isdigit():
                        out[key] = int(el.text)
            except ElementTree.ParseError:
                pass
        return out

    def upload(self, path, name):
        """Streams the file up under a temporary name, then renames it, so an
        interrupted upload never leaves a half archive that looks complete."""
        self.ensure_folder()
        final = posixpath.join(self.folder, name)
        partial = final + '.part'
        size = path.stat().st_size
        with open(path, 'rb') as f:
            resp = self._request('PUT', partial, timeout=UPLOAD_TIMEOUT, data=f,
                                 headers={'Content-Type': 'application/octet-stream', 'Content-Length': str(size)})
        if resp.status_code not in (200, 201, 204):
            self._request('DELETE', partial)
            raise NasError(f'Upload failed: {_explain(resp)}')
        moved = self._request('MOVE', partial, headers={'Destination': self._url(final), 'Overwrite': 'T'})
        if moved.status_code not in (201, 204):
            raise NasError(f'Upload finished but could not be renamed: {_explain(moved)}')
        # Make sure what landed is the whole file (a proxy or a full disk can
        # truncate silently).
        head = self._request('PROPFIND', final, headers={'Depth': '0'})
        if head.status_code == 207:
            try:
                el = ElementTree.fromstring(head.content).find('.//{DAV:}getcontentlength')
                if el is not None and el.text and int(el.text) != size:
                    raise NasError(f'The NAS has {el.text} bytes of a {size}-byte archive -- upload was truncated')
            except (ElementTree.ParseError, ValueError):
                pass
        return final

    def delete(self, remote_path):
        resp = self._request('DELETE', remote_path)
        if resp.status_code not in (200, 204, 404):
            raise NasError(f'Could not delete {remote_path}: {_explain(resp)}')

    def download(self, remote_path, dest):
        try:
            with self.session.get(self._url(remote_path), stream=True, timeout=UPLOAD_TIMEOUT) as resp:
                if resp.status_code != 200:
                    raise NasError(_explain(resp))
                with open(dest, 'wb') as out:
                    for chunk in resp.iter_content(1024 * 1024):
                        out.write(chunk)
        except requests.exceptions.RequestException as e:
            raise NasError(str(e))
        return dest


# --------------------------------------------------------------------------
# QuickConnect + File Station
# --------------------------------------------------------------------------

# Last address that worked per QuickConnect ID, so each backup doesn't
# re-walk the whole candidate list (per process; a restart just re-resolves).
_resolved = {}


def _serv(host, payload):
    try:
        resp = requests.post(f'https://{host}/Serv.php', data=json.dumps(payload), timeout=(8, 20))
        return resp.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise NasError(f'Could not reach Synology QuickConnect ({host}): {e.__class__.__name__}')


def _server_info(qc_id):
    payload = {'version': 1, 'command': 'get_server_info', 'stop_when_error': False, 'stop_when_success': False,
               'id': 'dsm_portal_https', 'serverID': qc_id, 'is_gofile': False}
    data = _serv(QC_DIRECTORY, payload)
    # The global directory answers "ask this regional site instead" for IDs
    # registered elsewhere.
    if data.get('errno') and data.get('sites'):
        for site in data['sites']:
            data = _serv(site, payload)
            if not data.get('errno'):
                break
    if data.get('errno'):
        raise NasError(f'QuickConnect ID "{qc_id}" was not found, or QuickConnect is off on the NAS '
                       '(Control Panel -> External Access -> QuickConnect)')
    return payload, data


def _probe(session, base):
    try:
        r = session.get(f'{base}/webapi/query.cgi', params={'api': 'SYNO.API.Info', 'version': 1, 'method': 'query',
                                                            'query': 'SYNO.API.Auth'}, timeout=PROBE_TIMEOUT)
        return r.status_code == 200 and r.json().get('success') is True
    except (requests.exceptions.RequestException, ValueError):
        return False


def _direct_candidates(data):
    server, service = data.get('server') or {}, data.get('service') or {}
    smart = data.get('smartdns') or {}
    port = service.get('port') or 5001
    ext_port = service.get('ext_port') or port
    out = []
    # *.direct.quickconnect.to names carry a valid Synology certificate, so
    # they come first: verified even with "verify certificate" on.
    out += [f'https://{h}:{port}' for h in smart.get('lan') or []]
    if smart.get('host'):
        out.append(f'https://{smart["host"]}:{port}')
    if smart.get('external'):
        out.append(f'https://{smart["external"]}:{ext_port}')
    ddns = server.get('ddns')
    if ddns and ddns != 'NULL':
        out.append(f'https://{ddns}:{ext_port}')
    # Raw IPs only pass TLS with verification off (the cert never names an IP).
    out += [f'https://{i["ip"]}:{port}' for i in server.get('interface') or [] if i.get('ip')]
    ext_ip = (server.get('external') or {}).get('ip')
    if ext_ip:
        out.append(f'https://{ext_ip}:{ext_port}')
    return list(dict.fromkeys(out))


def _resolve(qc_id, verify_direct):
    """Returns (base_url, verify) of the first way in that answers."""
    session = requests.Session()
    cached = _resolved.get(qc_id)
    if cached:
        session.verify = cached[1]
        if _probe(session, cached[0]):
            return cached
    payload, data = _server_info(qc_id)

    session.verify = verify_direct
    if not verify_direct:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for base in _direct_candidates(data):
        if _probe(session, base):
            _resolved[qc_id] = (base, verify_direct)
            logger.info('QuickConnect %s: direct via %s', qc_id, base)
            return _resolved[qc_id]

    # No direct route: ask Synology to open a relay tunnel. It takes a moment
    # to come up, hence the retries.
    control = (data.get('env') or {}).get('control_host') or QC_DIRECTORY
    tunnel = _serv(control, {**payload, 'command': 'request_tunnel'})
    env = tunnel.get('env') or data.get('env') or {}
    region = env.get('relay_region')
    if tunnel.get('errno') or not region:
        raise NasError('The NAS is not reachable directly and QuickConnect could not open a relay to it -- is the NAS '
                       'online, and is relay allowed (Control Panel -> External Access -> QuickConnect -> Advanced)?')
    relay = f'https://{qc_id}.{region}.quickconnect.to'
    session.verify = True
    for _ in range(4):
        if _probe(session, relay):
            _resolved[qc_id] = (relay, True)
            logger.info('QuickConnect %s: via relay %s', qc_id, relay)
            return _resolved[qc_id]
        time.sleep(2)
    raise NasError(f'QuickConnect relay {relay} did not answer -- check that DSM is allowed over QuickConnect '
                   '(Control Panel -> External Access -> QuickConnect -> Advanced -> Permission settings)')


AUTH_ERRORS = {
    400: 'the NAS rejected the username or password',
    401: 'that NAS account is disabled',
    402: 'that NAS account is not allowed to use File Station (Control Panel -> User -> Applications)',
    403: 'that NAS account has 2-step verification on -- use a dedicated account without it',
    404: 'that NAS account has 2-step verification on -- use a dedicated account without it',
    406: 'the NAS enforces 2-step verification for this account -- exempt a dedicated backup account',
    407: 'the NAS has blocked this server\'s IP after failed logins (Control Panel -> Security -> Protection)',
    408: 'the NAS account password has expired',
    409: 'the NAS account password has expired',
    410: 'the NAS account password must be changed before it can be used',
}
FS_ERRORS = {
    105: 'permission denied', 119: 'session expired', 106: 'session expired', 107: 'session expired',
    400: 'invalid parameter', 401: 'unknown file operation error', 402: 'the NAS is too busy',
    403: 'this account may not do that', 407: 'operation not permitted', 408: 'no such file or folder',
    411: 'the folder is read-only', 414: 'file already exists', 415: 'the account\'s disk quota is exceeded',
    416: 'the NAS is out of space', 417: 'I/O error on the NAS', 418: 'illegal name or path',
    1100: 'could not create the folder (does the shared folder exist, and does the account have Read/Write on it?)',
    1101: 'too many folders at once', 1200: 'could not rename the file', 1800: 'upload had no length',
    1801: 'upload timed out', 1802: 'upload had no file name', 1803: 'upload was cancelled',
    1805: 'could not overwrite the file',
}
SESSION_CODES = {106, 107, 119}
WANT = {'SYNO.API.Auth': 6, 'SYNO.FileStation.CreateFolder': 2, 'SYNO.FileStation.Upload': 2,
        'SYNO.FileStation.Rename': 2, 'SYNO.FileStation.Delete': 2, 'SYNO.FileStation.List': 2,
        'SYNO.FileStation.Download': 2}


class _MultipartBody:
    """multipart/form-data streamed from disk with a known Content-Length:
    requests would otherwise read the whole archive into RAM to build the form."""

    def __init__(self, fields, filename, path):
        self.boundary = 'ispbackup' + secrets.token_hex(12)
        head = ''.join(f'--{self.boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
                       for k, v in fields.items())
        head += (f'--{self.boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n')
        tail = f'\r\n--{self.boundary}--\r\n'.encode()
        self._parts = [io.BytesIO(head.encode()), open(path, 'rb'), io.BytesIO(tail)]
        self._len = len(head.encode()) + path.stat().st_size + len(tail)

    def __len__(self):
        return self._len

    def read(self, n=-1):
        out = b''
        while self._parts and (n < 0 or len(out) < n):
            chunk = self._parts[0].read(-1 if n < 0 else n - len(out))
            if chunk:
                out += chunk
            else:
                self._parts.pop(0).close()
        return out

    def close(self):
        for p in self._parts:
            p.close()
        self._parts = []

    @property
    def content_type(self):
        return f'multipart/form-data; boundary={self.boundary}'


class FileStation:
    def __init__(self, cfg):
        if not (cfg.nas_quickconnect_id and cfg.nas_username and cfg.nas_password):
            raise NasError('Enter the QuickConnect ID, username and password first')
        self.qc_id = normalize_quickconnect_id(cfg.nas_quickconnect_id)
        self.folder = normalize_folder(cfg.nas_folder)
        self.username, self.password = cfg.nas_username, cfg.nas_password
        self.verify_direct = bool(cfg.nas_verify_tls)
        self.session = requests.Session()
        self.base = None
        self.sid = None
        self.apis = {}

    # -- plumbing --

    def _connect(self):
        if self.sid:
            return
        self.base, self.session.verify = _resolve(self.qc_id, self.verify_direct)
        try:
            r = self.session.get(f'{self.base}/webapi/query.cgi', timeout=TIMEOUT, params={
                'api': 'SYNO.API.Info', 'version': 1, 'method': 'query', 'query': ','.join(WANT)})
            info = r.json().get('data') or {}
        except (requests.exceptions.RequestException, ValueError) as e:
            raise NasError(f'The NAS did not answer the API query via {self.base}: {e.__class__.__name__}')
        for api, want in WANT.items():
            if api not in info:
                raise NasError(f'The NAS does not offer {api} -- is File Station enabled?')
            meta = info[api]
            self.apis[api] = (meta['path'], max(meta.get('minVersion', 1), min(want, meta.get('maxVersion', want))))
        data = self._call('SYNO.API.Auth', 'login', account=self.username, passwd=self.password,
                          session='FileStation', format='sid', _auth=True)
        self.sid = data['sid']

    def _params(self, api, method, params):
        path, version = self.apis[api]
        out = {'api': api, 'version': version, 'method': method}
        for k, v in params.items():
            out[k] = json.dumps(v) if isinstance(v, (list, dict)) else v
        return f'{self.base}/webapi/{path}', out

    def _check(self, api, resp, auth=False):
        try:
            body = resp.json()
        except ValueError:
            raise NasError(f'{api}: unexpected reply from the NAS (HTTP {resp.status_code})')
        if body.get('success'):
            return body.get('data') or {}
        err = body.get('error') or {}
        code = err.get('code')
        if not auth and code in SESSION_CODES:
            raise _SessionExpired()
        detail = (AUTH_ERRORS if auth else FS_ERRORS).get(code, f'error {code}')
        extra = ', '.join(f"{e.get('path', '')} ({FS_ERRORS.get(e.get('code'), e.get('code'))})"
                          for e in err.get('errors') or [])
        raise NasError(f'{detail}{": " + extra if extra else ""}')

    def _call(self, api, method, _auth=False, **params):
        if not _auth:
            self._connect()
        for attempt in (1, 2):
            url, data = self._params(api, method, params)
            if self.sid:
                data['_sid'] = self.sid
            try:
                # POST keeps the password (and paths) out of the NAS's URL logs.
                resp = self.session.post(url, data=data, timeout=TIMEOUT)
            except requests.exceptions.RequestException as e:
                _resolved.pop(self.qc_id, None)
                raise NasError(f'Lost the connection to the NAS via {self.base}: {e.__class__.__name__}')
            try:
                return self._check(api, resp, auth=_auth)
            except _SessionExpired:
                if attempt == 2:
                    raise NasError('The NAS keeps ending the session')
                self.sid = None
                self._connect()

    def close(self):
        if self.sid:
            try:
                self._call('SYNO.API.Auth', 'logout', session='FileStation')
            except NasError:
                pass
            self.sid = None
        self.session.close()

    # -- the interface --

    def ensure_folder(self):
        parent, name = posixpath.split(self.folder)
        if parent == '/':
            # Just a shared folder: it can't be created over the API, only checked.
            self._call('SYNO.FileStation.List', 'getinfo', path=[self.folder])
            return
        try:
            self._call('SYNO.FileStation.CreateFolder', 'create', folder_path=[parent], name=[name],
                       force_parent=True)
        except NasError as e:
            share = '/' + self.folder.strip('/').split('/')[0]
            raise NasError(f'{self.folder}: {e} -- the path must start with an existing shared folder ({share})')

    def info(self):
        self.ensure_folder()
        out = {'folder': self.folder, 'free': None, 'used': None, 'via': self.base}
        try:
            data = self._call('SYNO.FileStation.List', 'list_share', additional=['volume_status'])
            share = '/' + self.folder.strip('/').split('/')[0]
            for s in data.get('shares') or []:
                if s.get('path') == share:
                    vol = (s.get('additional') or {}).get('volume_status') or {}
                    out['free'] = vol.get('freespace')
                    if vol.get('totalspace') and vol.get('freespace') is not None:
                        out['used'] = vol['totalspace'] - vol['freespace']
        except NasError:
            pass
        return out

    def upload(self, path, name):
        """Upload as <name>.part, rename when complete, then check the size."""
        self.ensure_folder()
        final = posixpath.join(self.folder, name)
        partial_name = name + '.part'
        size = path.stat().st_size
        for attempt in (1, 2):
            url, query = self._params('SYNO.FileStation.Upload', 'upload', {})
            query['_sid'] = self.sid
            body = _MultipartBody({'path': self.folder, 'create_parents': 'true', 'overwrite': 'true'},
                                  partial_name, path)
            try:
                resp = self.session.post(url, params=query, data=body, timeout=UPLOAD_TIMEOUT,
                                         headers={'Content-Type': body.content_type, 'Content-Length': str(len(body))})
            except requests.exceptions.RequestException as e:
                _resolved.pop(self.qc_id, None)
                raise NasError(f'Upload to the NAS via {self.base} failed: {e.__class__.__name__}')
            finally:
                body.close()
            try:
                self._check('SYNO.FileStation.Upload', resp)
                break
            except _SessionExpired:
                if attempt == 2:
                    raise NasError('The NAS keeps ending the session')
                self.sid = None
                self._connect()
        self._call('SYNO.FileStation.Rename', 'rename', path=[f'{final}.part'], name=[name])
        try:
            got = self._call('SYNO.FileStation.List', 'getinfo', path=[final], additional=['size'])
            remote = ((got.get('files') or [{}])[0].get('additional') or {}).get('size')
        except NasError:
            remote = None
        if remote is not None and int(remote) != size:
            raise NasError(f'The NAS has {remote} bytes of a {size}-byte archive -- upload was truncated')
        return final

    def delete(self, remote_path):
        try:
            self._call('SYNO.FileStation.Delete', 'delete', path=[remote_path], recursive=False)
        except NasError as e:
            if 'no such file' not in str(e):
                raise NasError(f'Could not delete {remote_path}: {e}')

    def download(self, remote_path, dest):
        self._connect()
        url, params = self._params('SYNO.FileStation.Download', 'download', {'path': [remote_path], 'mode': 'download'})
        params['_sid'] = self.sid
        try:
            with self.session.get(url, params=params, stream=True, timeout=UPLOAD_TIMEOUT) as resp:
                if resp.status_code != 200 or 'json' in resp.headers.get('Content-Type', ''):
                    raise NasError(f'Download failed (HTTP {resp.status_code})')
                with open(dest, 'wb') as out:
                    for chunk in resp.iter_content(1024 * 1024):
                        out.write(chunk)
        except requests.exceptions.RequestException as e:
            raise NasError(str(e))
        return dest


class _SessionExpired(Exception):
    pass
