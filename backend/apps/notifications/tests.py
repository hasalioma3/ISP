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


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class EmailChannelTests(TestCase):
    """SMTP email: Gmail by default, custom server optional."""

    def setUp(self):
        from apps.notifications.models import NotificationSettings
        self.settings, _ = NotificationSettings.objects.update_or_create(pk=1, defaults={
            'email_enabled': True, 'smtp_username': 'isp@gmail.com', 'smtp_password': 'app-pass-1234',
            'email_from_name': 'Hasanet',
        })

    def connection_kwargs(self):
        from apps.notifications.services.email_service import EmailService
        with patch('apps.notifications.services.email_service.get_connection') as conn, \
             patch('apps.notifications.services.email_service.EmailMessage.send', return_value=1) as send:
            result = EmailService().send_email('grace@example.com', 'Your plan was extended. It runs until 1 Jan.')
        return conn.call_args.kwargs, result, send

    def test_gmail_defaults(self):
        kwargs, result, _ = self.connection_kwargs()
        self.assertTrue(result['success'])
        self.assertEqual((kwargs['host'], kwargs['port'], kwargs['use_tls'], kwargs['use_ssl']), ('smtp.gmail.com', 587, True, False))
        self.assertEqual(kwargs['username'], 'isp@gmail.com')

    def test_custom_smtp(self):
        self.settings.smtp_provider = 'custom'
        self.settings.smtp_host = 'mail.example.com'
        self.settings.smtp_port = 465
        self.settings.smtp_security = 'ssl'
        self.settings.save()
        kwargs, result, _ = self.connection_kwargs()
        self.assertEqual((kwargs['host'], kwargs['port'], kwargs['use_tls'], kwargs['use_ssl']), ('mail.example.com', 465, False, True))

    def test_disabled_is_a_config_error(self):
        from apps.notifications.services.email_service import EmailService
        self.settings.email_enabled = False
        self.settings.save()
        result = EmailService().send_email('grace@example.com', 'hi')
        self.assertFalse(result['success'])
        self.assertTrue(result['config_error'])

    def test_password_kept_when_form_saved_blank_and_never_returned(self):
        from apps.notifications.models import NotificationSettings
        from apps.customers.models import Customer
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        res = client.patch('/api/notifications/settings/', {'smtp_password': '', 'email_from_name': 'New'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertNotIn('smtp_password', res.data)
        self.assertTrue(res.data['smtp_password_is_set'])
        self.assertEqual(NotificationSettings.load().smtp_password, 'app-pass-1234')

    def test_staff_alert_by_email(self):
        from apps.notifications.models import NotificationLog
        from apps.notifications.tasks import send_staff_alert
        self.settings.staff_alert_channel = 'email'
        self.settings.staff_alert_email = 'boss@example.com'
        self.settings.save()
        with patch('apps.notifications.dispatch.EmailService.send_email', return_value={'success': True, 'data': {}}) as send:
            send_staff_alert('admin added KES 300 cash')
        send.assert_called_once_with('boss@example.com', 'admin added KES 300 cash')
        log = NotificationLog.objects.get()
        self.assertEqual((log.channel, log.event_type), ('email', 'staff_alert'))


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class ConfirmationAndTemplateTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.billing.models import BillingPlan, Subscription
        from apps.customers.models import Customer
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        NotificationSettings.objects.update_or_create(pk=1, defaults={'confirmation_service_types': 'pppoe'})
        plan = BillingPlan.objects.create(name='Home 10', service_type='pppoe', download_speed=10, upload_speed=10,
                                          price='2500.00', mikrotik_profile='h10')
        self.pppoe = Customer.objects.create(username='grace', first_name='Grace', phone_number='0722000001', service_type='pppoe')
        self.hotspot = Customer.objects.create(username='0711_AAAA', phone_number='0711000000', service_type='hotspot')
        self.sub = Subscription.objects.create(customer=self.pppoe, plan=plan, expiry_date=timezone.now() + timedelta(days=30))
        self.hsub = Subscription.objects.create(customer=self.hotspot, plan=plan, expiry_date=timezone.now() + timedelta(days=1))

    def confirm(self, customer, sub):
        from apps.notifications.tasks import send_payment_confirmation_sms
        with patch('apps.notifications.tasks.AfricasTalkingService.send_sms', return_value={'success': True, 'data': {}}) as sms:
            send_payment_confirmation_sms(customer.id, 'payment_confirmation', '2500', sub.id)
        return sms

    def test_pppoe_gets_confirmation_hotspot_does_not(self):
        self.assertTrue(self.confirm(self.pppoe, self.sub).called)
        self.assertFalse(self.confirm(self.hotspot, self.hsub).called)

    def test_hotspot_confirmations_can_be_turned_on(self):
        NotificationSettings.objects.filter(pk=1).update(confirmation_service_types='pppoe,hotspot')
        self.assertTrue(self.confirm(self.hotspot, self.hsub).called)

    def test_custom_template_is_used(self):
        from apps.notifications.models import MessageTemplate
        MessageTemplate.objects.create(kind='system', key='payment_confirmation', name='x',
                                       body='Asante {first_name}! {plan} is on until {expiry}. {unknown}')
        message = self.confirm(self.pppoe, self.sub).call_args.args[1]
        self.assertTrue(message.startswith('Asante Grace! Home 10 is on until '))
        self.assertTrue(message.endswith('{unknown}'))  # misspelt placeholder kept, not a crash

    def test_malformed_template_falls_back_to_default(self):
        from apps.notifications.models import MessageTemplate
        MessageTemplate.objects.create(kind='system', key='payment_confirmation', name='x', body='Broken {plan')
        message = self.confirm(self.pppoe, self.sub).call_args.args[1]
        self.assertTrue(message.startswith('Payment of KES 2500'))

    def test_template_api(self):
        from rest_framework.test import APIClient
        from apps.customers.models import Customer
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        res = client.put('/api/notifications/templates/system/voucher_send/', {'body': 'Code {code} for {plan}'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(next(t for t in res.data['system'] if t['key'] == 'voucher_send')['is_custom'])
        self.assertEqual(client.put('/api/notifications/templates/system/voucher_send/', {'body': 'bad {'}, format='json').status_code, 400)
        res = client.delete('/api/notifications/templates/system/voucher_send/')
        self.assertFalse(next(t for t in res.data['system'] if t['key'] == 'voucher_send')['is_custom'])
        promo = client.post('/api/notifications/templates/promo/', {'name': 'Weekend', 'body': 'Hi {first_name}, 50% off!'}, format='json')
        self.assertEqual(promo.status_code, 201)
        listing = client.get('/api/notifications/templates/').data
        self.assertEqual([p['name'] for p in listing['promo']], ['Weekend'])
        preview = client.post('/api/notifications/templates/preview/', {'body': 'Hi {first_name}'}, format='json').data
        self.assertEqual(preview['preview'], 'Hi Grace')
        self.assertEqual(client.delete(f"/api/notifications/templates/promo/{promo.data['id']}/").status_code, 204)

    def test_broadcast_is_personalised(self):
        from apps.notifications.tasks import send_promo_broadcast
        from apps.customers.models import Customer
        Customer.objects.filter(pk=self.pppoe.pk).update(status='active')
        with patch('apps.notifications.dispatch.AfricasTalkingService.send_sms', return_value={'success': True, 'data': {}}) as sms:
            send_promo_broadcast('Hi {first_name}, renew today!', ['sms'], 'pppoe')
        self.assertEqual(sms.call_args.args[1], 'Hi Grace, renew today!')


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class AfricasTalkingSettingsGuardTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from apps.customers.models import Customer
        self.client = APIClient()
        self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))

    def patch(self, **data):
        return self.client.patch('/api/notifications/settings/', data, format='json')

    def test_truncated_key_rejected(self):
        res = self.patch(at_username='hasanet', at_environment='production', at_api_key='UMigfm88s')
        self.assertEqual(res.status_code, 400)
        self.assertIn('only 9 characters', str(res.data))

    def test_username_and_environment_must_agree(self):
        self.assertEqual(self.patch(at_username='sandbox', at_environment='production').status_code, 400)
        self.assertEqual(self.patch(at_username='hasanet', at_environment='sandbox').status_code, 400)
        full_key = 'atsk_' + 'a' * 64
        self.assertEqual(self.patch(at_username='hasanet', at_environment='production', at_api_key=full_key).status_code, 200)

    def test_connection_error_is_retried_once(self):
        NotificationSettings.objects.update_or_create(pk=1, defaults=dict(
            at_username='hasanet', at_api_key='atsk_' + 'a' * 64, at_environment='production'))
        ok = MagicMock(status_code=201)
        ok.json.return_value = {'SMSMessageData': {'Recipients': [{'status': 'Success', 'messageId': 'x'}]}}
        with patch('apps.notifications.services.africastalking_service.requests.post',
                   side_effect=[requests.exceptions.SSLError('record layer failure'), ok]) as post:
            result = AfricasTalkingService().send_sms('0722000001', 'hi')
        self.assertTrue(result['success'])
        self.assertEqual(post.call_count, 2)


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class AfricasTalkingStatusHelpTests(TestCase):
    def test_blacklisted_number_is_explained(self):
        NotificationSettings.objects.update_or_create(pk=1, defaults=dict(
            at_username='hasanet', at_api_key='atsk_' + 'a' * 72, at_environment='production'))
        resp = MagicMock(status_code=201)
        resp.json.return_value = {'SMSMessageData': {'Message': 'Sent to 0/1', 'Recipients': [
            {'status': 'UserInBlacklist', 'statusCode': 406, 'number': '+254794907020'}]}}
        with patch('apps.notifications.services.africastalking_service.requests.post', return_value=resp):
            result = AfricasTalkingService().send_sms('0794907020', 'hi')
        self.assertFalse(result['success'])
        self.assertIn('UserInBlacklist', result['error'])
        self.assertIn('*456*9*5#', result['error'])
