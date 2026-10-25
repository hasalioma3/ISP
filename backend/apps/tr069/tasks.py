import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import CPEDevice
from .services.acs_service import ACSService

logger = logging.getLogger('tr069')

ONLINE_THRESHOLD = timedelta(hours=1)


def _brand_from_manufacturer(manufacturer):
    m = (manufacturer or '').lower()
    if 'huawei' in m:
        return 'huawei'
    if 'tenda' in m:
        return 'tenda'
    if 'tp-link' in m or 'tplink' in m:
        return 'tplink'
    return 'other'


@shared_task
def sync_cpe_devices():
    """
    Pulls the device list from GenieACS NBI and updates/creates CPEDevice
    rows -- known devices (matched by genieacs_device_id) get their
    last_inform/is_online/software_version refreshed; devices GenieACS has
    seen that aren't in our table yet are created unlinked (customer=None),
    so they show up in the admin "unlinked" filter for an admin to assign
    to a customer. Scheduled periodically in celery.py -- mirrors
    apps.network.tasks.collect_usage_statistics's role for ActiveSession.
    """
    result = ACSService().list_devices()
    if not result['success']:
        logger.error(f"sync_cpe_devices: failed to list devices from ACS: {result.get('error')}")
        return 0

    now = timezone.now()
    synced = 0
    for doc in result.get('data') or []:
        device_id = doc.get('_id')
        if not device_id:
            continue

        device_info = doc.get('_deviceId', {}) or {}
        last_inform_raw = doc.get('_lastInform')
        last_inform = None
        if last_inform_raw:
            try:
                last_inform = timezone.datetime.fromisoformat(last_inform_raw.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                last_inform = None

        is_online = bool(last_inform and (now - last_inform) < ONLINE_THRESHOLD)

        CPEDevice.objects.update_or_create(
            genieacs_device_id=device_id,
            defaults={
                'serial_number': device_info.get('_SerialNumber', '') or '',
                'manufacturer': device_info.get('_Manufacturer', '') or '',
                'model_name': device_info.get('_ProductClass', '') or '',
                'brand': _brand_from_manufacturer(device_info.get('_Manufacturer')),
                'last_inform': last_inform,
                'is_online': is_online,
            },
        )
        synced += 1

    logger.info(f"sync_cpe_devices: synced {synced} devices")
    return synced
