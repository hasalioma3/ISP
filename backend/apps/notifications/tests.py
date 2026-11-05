from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings
from cryptography.fernet import Fernet

from apps.notifications.models import NotificationSettings
from apps.notifications.services.africastalking_service import AfricasTalkingService


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class AfricasTalkingSmsTests(TestCase):
    def test_missing_api_key_fails_without_calling_at(self):
        NotificationSettings.objects.update_or_create(pk=1, defaults=dict(at_username='myapp', at_api_key=''))
        with patch('apps.notifications.services.africastalking_service.requests.post') as post:
            result = AfricasTalkingService().send_sms('0712345678', 'hi')
        post.assert_not_called()
        self.assertFalse(result['success'])
        self.assertTrue(result['config_error'])

    def test_invalid_number_is_rejected_locally(self):
        NotificationSettings.objects.update_or_create(pk=1, defaults=dict(at_username='myapp', at_api_key='key123'))
        with patch('apps.notifications.services.africastalking_service.requests.post') as post:
            result = AfricasTalkingService().send_sms('12345', 'hi')
        post.assert_not_called()
        self.assertTrue(result['config_error'])

    def test_401_error_is_readable_and_redacts_key(self):
        NotificationSettings.objects.update_or_create(pk=1, defaults=dict(at_username='myapp', at_api_key='key123', at_environment='production'))
        response = MagicMock(status_code=401, text='The supplied authentication is invalid (key123)')
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response)
        with patch('apps.notifications.services.africastalking_service.requests.post', return_value=response):
            result = AfricasTalkingService().send_sms('0712345678', 'hi')
        self.assertFalse(result['success'])
        self.assertIn('The supplied authentication is invalid ([redacted])', result['error'])
        self.assertNotIn('key123', result['error'])
        self.assertIn('production', result['error'])
