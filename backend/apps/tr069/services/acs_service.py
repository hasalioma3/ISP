"""
Talks to GenieACS's NBI (Northbound Interface) over HTTP -- modeled on
apps.notifications.services.whatsapp_service.WhatsAppService: one shared
sidecar base URL from settings (not per-device credentials, like
MikroTikService -- there's one ACS, not one per device), same
never-raises, {'success': bool, ...} contract used everywhere else in this
codebase. NBI is internal-only (no auth of its own, no published port) --
same network-isolation-as-access-control pattern as the WhatsApp sidecar.
"""
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger('tr069')


class ACSService:
    def __init__(self):
        self.base_url = settings.ACS_NBI_URL.rstrip('/')

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(method, f'{self.base_url}{path}', timeout=kwargs.pop('timeout', 30), **kwargs)
            if response.ok:
                # GenieACS returns an empty body for some 200s (e.g. a
                # successful connection-request task) -- never raise just
                # because there's nothing to parse.
                data = response.json() if response.content else None
                return {'success': True, 'data': data, 'status_code': response.status_code}
            return {'success': False, 'error': response.text or f'HTTP {response.status_code}', 'status_code': response.status_code}
        except requests.exceptions.RequestException as e:
            logger.error(f"ACS NBI {method} {path} failed: {e}")
            return {'success': False, 'error': str(e), 'data': None}

    def list_devices(self, query=None, projection=None):
        """query is a dict (MongoDB-style filter), e.g. {'_deviceId._SerialNumber': 'ABC123'}."""
        params = {}
        if query:
            params['query'] = json.dumps(query)
        if projection:
            params['projection'] = ','.join(projection)
        return self._request('GET', '/devices/', params=params)

    def get_device(self, device_id):
        result = self.list_devices(query={'_id': device_id})
        if result['success']:
            result['data'] = result['data'][0] if result['data'] else None
        return result

    def _create_task(self, device_id, task, wait_for_execution=True):
        """
        wait_for_execution=True issues a connection request so the task
        runs now (while the admin is waiting on it in the UI) instead of
        sitting queued until the device's next periodic inform (which
        could be hours away) -- GenieACS returns 200 if it actually ran,
        202 if it only got queued (device didn't respond to the connection
        request in time, e.g. it's offline or behind NAT weirdness).
        """
        params = {}
        if wait_for_execution:
            params = {'connection_request': '', 'timeout': 10000}
        result = self._request(
            'POST', f'/devices/{device_id}/tasks', params=params, json=task, timeout=15,
        )
        if result['success']:
            result['queued_only'] = result.get('status_code') == 202
        return result

    def reboot(self, device_id):
        return self._create_task(device_id, {'name': 'reboot'})

    def factory_reset(self, device_id):
        return self._create_task(device_id, {'name': 'factoryReset'})

    def set_wifi(self, device_id, ssid, password, wlan_index=1):
        """
        Standard TR-098 data model paths -- work on most Huawei/Tenda/
        TP-Link devices as-is, but some firmware exposes WiFi under
        vendor-specific paths instead/also (X_HW_*, X_TP_* extensions).
        Treat this as the default; devices that don't apply the change
        need a GenieACS provision/preset calibrated against their actual
        parameter tree (see get_device's raw parameter dump).
        """
        base = f'InternetGatewayDevice.LANDevice.1.WLANConfiguration.{wlan_index}'
        return self._create_task(device_id, {
            'name': 'setParameterValues',
            'parameterValues': [
                [f'{base}.SSID', ssid, 'xsd:string'],
                [f'{base}.PreSharedKey.1.PreSharedKey', password, 'xsd:string'],
                [f'{base}.KeyPassphrase', password, 'xsd:string'],
            ],
        })

    def get_diagnostics(self, device_id):
        """Pulls the handful of parameters useful for a support-facing
        diagnostics panel -- connected hosts, uptime. Return value may be
        incomplete per-brand; the UI should render whatever came back
        rather than assume every field is present."""
        return self._create_task(device_id, {
            'name': 'getParameterValues',
            'parameterNames': [
                'InternetGatewayDevice.DeviceInfo.UpTime',
                'InternetGatewayDevice.LANDevice.1.Hosts.HostNumberOfEntries',
                'InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.1.ExternalIPAddress',
            ],
        })

    def push_firmware(self, device_id, file_name):
        """file_name must already be uploaded to GenieACS (see
        upload_firmware) before this is called."""
        return self._create_task(device_id, {'name': 'download', 'file': file_name})

    def upload_firmware(self, file_name, content, oui, product_class, version):
        try:
            response = requests.put(
                f'{self.base_url}/files/{file_name}',
                data=content,
                headers={
                    'fileType': '1 Firmware Upgrade Image',
                    'oui': oui,
                    'productClass': product_class,
                    'version': version,
                },
                timeout=120,
            )
            if response.ok:
                return {'success': True}
            return {'success': False, 'error': response.text or f'HTTP {response.status_code}'}
        except requests.exceptions.RequestException as e:
            logger.error(f"ACS firmware upload failed: {e}")
            return {'success': False, 'error': str(e)}
