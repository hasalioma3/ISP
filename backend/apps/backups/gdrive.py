"""
Google Drive over its REST API with plain requests (same style as the
M-Pesa and Africa's Talking integrations -- no Google SDK on the Pi).

Sign-in is Google's OAuth "device flow" (the TV-style "go to
google.com/device and enter this code"): it needs no redirect URL, so it
works whether the admin page is opened by LAN IP, VPN or domain. The scope
is drive.file -- the app can only see and manage the files and folder it
created itself, nothing else in the Drive.

Uploads are resumable and sent in 8 MiB pieces, so a large archive neither
loads into RAM nor restarts from zero after a dropped connection.
"""
import logging
import os

import requests

logger = logging.getLogger('backups')

SCOPE = 'https://www.googleapis.com/auth/drive.file'
DEVICE_URL = 'https://oauth2.googleapis.com/device/code'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
API = 'https://www.googleapis.com/drive/v3'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'
PIECE = 8 * 1024 * 1024  # must be a multiple of 256 KiB
TIMEOUT = 60


class DriveError(Exception):
    pass


def _error(resp):
    try:
        data = resp.json()
        err = data.get('error')
        if isinstance(err, dict):
            return err.get('message') or str(err)
        return data.get('error_description') or err or resp.text[:300]
    except ValueError:
        return resp.text[:300] or f'HTTP {resp.status_code}'


def start_device_flow(client_id):
    resp = requests.post(DEVICE_URL, data={'client_id': client_id, 'scope': SCOPE}, timeout=30)
    if resp.status_code != 200:
        raise DriveError(f'Google refused the sign-in request: {_error(resp)}. Check the Client ID, and that the '
                         'OAuth client type is "TVs and Limited Input devices".')
    return resp.json()  # device_code, user_code, verification_url, expires_in, interval


def poll_device_flow(client_id, client_secret, device_code):
    """Returns ('pending'|'slow_down'|'denied'|'expired', None) or ('ok', token dict)."""
    resp = requests.post(TOKEN_URL, data={
        'client_id': client_id, 'client_secret': client_secret, 'device_code': device_code,
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
    }, timeout=30)
    data = resp.json() if resp.content else {}
    if resp.status_code == 200:
        return 'ok', data
    err = data.get('error')
    if err == 'authorization_pending':
        return 'pending', None
    if err == 'slow_down':
        return 'slow_down', None
    if err == 'access_denied':
        return 'denied', None
    if err == 'expired_token':
        return 'expired', None
    raise DriveError(f'Google sign-in failed: {data.get("error_description") or err or resp.status_code}')


def revoke(refresh_token):
    try:
        requests.post(REVOKE_URL, params={'token': refresh_token}, timeout=15)
    except requests.RequestException:
        pass


class Drive:
    def __init__(self, cfg):
        if not (cfg.gdrive_client_id and cfg.gdrive_client_secret and cfg.gdrive_refresh_token):
            raise DriveError('Google Drive is not connected')
        self.cfg = cfg
        self._token = None

    def token(self):
        if self._token:
            return self._token
        resp = requests.post(TOKEN_URL, data={
            'client_id': self.cfg.gdrive_client_id, 'client_secret': self.cfg.gdrive_client_secret,
            'refresh_token': self.cfg.gdrive_refresh_token, 'grant_type': 'refresh_token',
        }, timeout=30)
        if resp.status_code != 200:
            msg = _error(resp)
            if 'invalid_grant' in resp.text:
                msg += (' -- the Google sign-in has expired or was revoked. Reconnect Google Drive. (If this '
                        'happens every 7 days, the OAuth consent screen is still in "Testing": publish it.)')
            raise DriveError(msg)
        self._token = resp.json()['access_token']
        return self._token

    def _headers(self, **extra):
        return {'Authorization': f'Bearer {self.token()}', **extra}

    def about(self):
        resp = requests.get(f'{API}/about', params={'fields': 'user(emailAddress,displayName),storageQuota'},
                            headers=self._headers(), timeout=TIMEOUT)
        if resp.status_code != 200:
            raise DriveError(_error(resp))
        return resp.json()

    def ensure_folder(self):
        """The app's own folder (created on first use; drive.file can only see folders it made)."""
        if self.cfg.gdrive_folder_id:
            resp = requests.get(f'{API}/files/{self.cfg.gdrive_folder_id}', params={'fields': 'id,trashed'},
                                headers=self._headers(), timeout=TIMEOUT)
            if resp.status_code == 200 and not resp.json().get('trashed'):
                return self.cfg.gdrive_folder_id
        resp = requests.post(f'{API}/files', json={
            'name': self.cfg.gdrive_folder_name or 'ISP Billing backups',
            'mimeType': 'application/vnd.google-apps.folder',
        }, params={'fields': 'id'}, headers=self._headers(), timeout=TIMEOUT)
        if resp.status_code not in (200, 201):
            raise DriveError(f'Could not create the backup folder: {_error(resp)}')
        self.cfg.gdrive_folder_id = resp.json()['id']
        self.cfg.save(update_fields=['gdrive_folder_id'])
        return self.cfg.gdrive_folder_id

    def upload(self, path, name, progress=None):
        folder = self.ensure_folder()
        size = os.path.getsize(path)
        init = requests.post(
            UPLOAD, params={'uploadType': 'resumable', 'fields': 'id'},
            json={'name': name, 'parents': [folder]},
            headers=self._headers(**{'X-Upload-Content-Type': 'application/octet-stream',
                                     'X-Upload-Content-Length': str(size)}),
            timeout=TIMEOUT,
        )
        if init.status_code != 200:
            raise DriveError(f'Upload could not start: {_error(init)}')
        session = init.headers['Location']
        sent = 0
        retries = 0
        with open(path, 'rb') as f:
            while True:
                f.seek(sent)
                piece = f.read(PIECE)
                end = sent + len(piece) - 1
                headers = {'Content-Length': str(len(piece)),
                           'Content-Range': f'bytes {sent}-{end}/{size}' if piece else f'bytes */{size}'}
                try:
                    resp = requests.put(session, data=piece, headers=headers, timeout=300)
                except requests.RequestException as e:
                    resp = None
                    err = str(e)
                if resp is not None and resp.status_code in (200, 201):
                    return resp.json()['id']
                if resp is not None and resp.status_code == 308:
                    rng = resp.headers.get('Range')  # e.g. 'bytes=0-8388607'
                    sent = int(rng.split('-')[1]) + 1 if rng else 0
                    retries = 0
                    if progress:
                        progress(sent, size)
                    continue
                # Network blip or 5xx: ask Google how much it has, resume from there.
                retries += 1
                if retries > 5:
                    raise DriveError(f'Upload failed: {_error(resp) if resp is not None else err}')
                status = requests.put(session, headers={'Content-Range': f'bytes */{size}', 'Content-Length': '0'},
                                      timeout=60)
                if status.status_code in (200, 201):
                    return status.json()['id']
                rng = status.headers.get('Range')
                sent = int(rng.split('-')[1]) + 1 if rng else 0

    def delete(self, file_id):
        resp = requests.delete(f'{API}/files/{file_id}', headers=self._headers(), timeout=TIMEOUT)
        if resp.status_code not in (200, 204, 404):
            raise DriveError(_error(resp))

    def download(self, file_id, dst):
        with requests.get(f'{API}/files/{file_id}', params={'alt': 'media'}, headers=self._headers(),
                          stream=True, timeout=300) as resp:
            if resp.status_code != 200:
                raise DriveError(_error(resp))
            with open(dst, 'wb') as f:
                for chunk in resp.iter_content(1024 * 1024):
                    f.write(chunk)
