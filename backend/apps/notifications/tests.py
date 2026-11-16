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
             patch('apps.notifications.services.email_service.EmailMultiAlternatives.send', return_value=1) as send:
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
        self.settings.admin_emails = 'boss@example.com'
        self.settings.save()
        with patch('apps.notifications.services.email_service.EmailService.send_email',
                   return_value={'success': True, 'data': {}}) as send:
            send_staff_alert('admin added KES 300 cash')
        send.assert_called_once()
        self.assertEqual(send.call_args.args[:2], ('boss@example.com', 'admin added KES 300 cash'))
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
        NotificationSettings.objects.update_or_create(pk=1, defaults={
            'confirmation_service_types': 'pppoe', 'confirmation_channels': 'sms'})
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


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class SuperadminEmailTests(TestCase):
    def setUp(self):
        from apps.billing.models import BillingPlan
        from apps.customers.models import Customer
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        NotificationSettings.objects.update_or_create(pk=1, defaults={
            'email_enabled': True, 'smtp_username': 'isp@gmail.com', 'smtp_password': 'pw-123456'})
        self.boss = Customer.objects.create(username='boss', email='boss@example.com', is_staff=True, is_superuser=True)
        Customer.objects.create(username='nomail', is_staff=True, is_superuser=True)  # no address: skipped
        self.plan = BillingPlan.objects.create(name='Home 10', service_type='pppoe', download_speed=10,
                                               upload_speed=10, price='2500.00', mikrotik_profile='h10')

    def sent(self):
        return patch('apps.notifications.services.email_service.EmailService.send_email',
                     return_value={'success': True, 'data': {}})

    def test_daily_report_figures_and_pdf(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.billing.models import Subscription, Transaction
        from apps.customers.models import Customer
        from apps.notifications.admin_emails import daily_report, send_daily_report
        c = Customer.objects.create(username='grace')
        sub = Subscription.objects.create(customer=c, plan=self.plan, expiry_date=timezone.now() + timedelta(days=30))
        Transaction.objects.create(customer=c, subscription=sub, transaction_id='T1', amount=2500, payment_method='mpesa', status='completed')
        Transaction.objects.create(customer=c, transaction_id='T2', amount=100, payment_method='cash', status='completed')
        Transaction.objects.create(customer=c, transaction_id='T3', amount=2500, payment_method='balance', status='completed')
        summary, sections = daily_report(timezone.localdate())
        self.assertEqual(dict(summary)['Revenue'], 'KES 2,600.00')  # balance re-use not counted twice
        plans = {r[0]: r for r in sections[0][2]}
        self.assertEqual(plans['Home 10'][1], 1)
        self.assertIn('Credited to balance (no plan)', plans)
        with self.sent() as send:
            self.assertEqual(send_daily_report(force=True), 1)
        kwargs = send.call_args.kwargs
        self.assertEqual(send.call_args.args[0], 'boss@example.com')
        self.assertIn('Daily sales report', kwargs['subject'])
        self.assertTrue(kwargs['attachments'][0][1].startswith(b'%PDF'))

    def test_daily_report_respects_switch(self):
        from apps.notifications.admin_emails import send_daily_report
        NotificationSettings.objects.filter(pk=1).update(daily_report_enabled=False)
        with self.sent() as send:
            self.assertEqual(send_daily_report(), 0)
        send.assert_not_called()

    def test_new_pppoe_customer_emails_but_hotspot_does_not(self):
        from apps.customers.models import Customer
        with patch('apps.notifications.admin_emails.email_new_pppoe_customer.delay') as task, \
             self.captureOnCommitCallbacks(execute=True):
            pppoe = Customer.objects.create(username='newhome', service_type='pppoe')
            Customer.objects.create(username='0711_AAAA', service_type='hotspot')
        task.assert_called_once_with(pppoe.id)

    def test_suppressed_inside_bulk_import(self):
        from apps.customers.models import Customer
        from apps.notifications.admin_emails import suppress_new_customer_emails
        with patch('apps.notifications.admin_emails.email_new_pppoe_customer.delay') as task, \
             self.captureOnCommitCallbacks(execute=True):
            with suppress_new_customer_emails():
                Customer.objects.create(username='imported', service_type='pppoe')
        task.assert_not_called()

    def test_voucher_batch_email_has_codes_and_csv(self):
        from rest_framework.test import APIClient
        from apps.notifications.admin_emails import email_vouchers_generated
        client = APIClient()
        client.force_authenticate(self.boss)
        with patch('apps.notifications.admin_emails.email_vouchers_generated.delay') as task, \
             self.captureOnCommitCallbacks(execute=True):
            res = client.post('/api/billing/vouchers/generate/', {'quantity': 3, 'plan_id': self.plan.id}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        batch_id = task.call_args.args[0]
        with self.sent() as send:
            email_vouchers_generated(batch_id)
        text = send.call_args.args[1]
        for v in res.data['vouchers']:
            self.assertIn(v['code'], text)
        self.assertEqual(send.call_args.kwargs['attachments'][0][2], 'text/csv')

    def test_manual_topup_email(self):
        from rest_framework.test import APIClient
        from apps.customers.models import Customer
        client = APIClient()
        client.force_authenticate(self.boss)
        c = Customer.objects.create(username='topme', service_type='pppoe')
        with patch('apps.notifications.admin_emails.email_manual_topup.delay') as task, \
             patch('apps.notifications.tasks.send_customer_account_notice.delay'), \
             patch('apps.notifications.tasks.send_staff_alert.delay'), \
             self.captureOnCommitCallbacks(execute=True):
            client.post(f'/api/customers/subscribers/{c.id}/add_balance/', {'amount': 300}, format='json')
        task.assert_called_once()



@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class AdminContactsTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from apps.customers.models import Customer
        self.client = APIClient()
        self.client.force_authenticate(Customer.objects.create(username='root', email='root@example.com',
                                                               is_staff=True, is_superuser=True))

    def test_every_contact_on_every_channel(self):
        from apps.notifications.admin_emails import notify_admins
        NotificationSettings.objects.update_or_create(pk=1, defaults={
            'email_enabled': True, 'smtp_username': 'isp@gmail.com', 'smtp_password': 'pw-123456',
            'admin_phones': '0722000001\n0733000002', 'admin_emails': 'a@example.com, b@example.com',
            'admin_phone_channels': 'sms,whatsapp',
        })
        ok = {'success': True, 'data': {}}
        with patch('apps.notifications.dispatch.AfricasTalkingService.send_sms', return_value=ok) as sms, \
             patch('apps.notifications.dispatch._send_whatsapp', return_value=ok) as wa, \
             patch('apps.notifications.services.email_service.EmailService.send_email', return_value=ok) as email:
            delivered = notify_admins('staff_alert', 'Subject', 'Body text', sms_text='Short')
        self.assertEqual(sms.call_count, 2)
        self.assertEqual(wa.call_count, 2)
        self.assertEqual(sorted(c.args[0] for c in email.call_args_list), ['a@example.com', 'b@example.com', 'root@example.com'])
        self.assertEqual(delivered, 7)
        self.assertEqual(sms.call_args.args[1], 'Short')

    def test_validation_and_normalising(self):
        res = self.client.patch('/api/notifications/settings/', {'admin_emails': 'ok@example.com\nnot-an-email'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.patch('/api/notifications/settings/', {'admin_phones': '12345'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.patch('/api/notifications/settings/', {
            'admin_emails': 'A@Example.com, a@example.com', 'admin_phones': '0722000001; 0722000001',
            'admin_phone_channels': 'whatsapp,telegram',
        }, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['admin_emails'], 'a@example.com')
        self.assertEqual(res.data['admin_phones'], '0722000001')
        self.assertEqual(res.data['admin_phone_channels'], 'whatsapp')

    def test_old_single_contact_migrated(self):
        import importlib
        migration = importlib.import_module('apps.notifications.migrations.0012_admin_contacts')

        class Row:
            staff_alert_phone, staff_alert_email, staff_alert_channel = '0722000001', 'boss@example.com', 'whatsapp'
            def save(self, update_fields): self.saved = update_fields

        row = Row()

        class Apps:
            def get_model(self, *a):
                class M:
                    objects = type('Q', (), {'all': staticmethod(lambda: [row])})
                return M
        migration.copy_staff_alert_contact(Apps(), None)
        self.assertEqual((row.admin_phones, row.admin_emails, row.admin_phone_channels),
                         ('0722000001', 'boss@example.com', 'whatsapp'))


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class NotificationReportTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from apps.customers.models import Customer
        from apps.notifications.models import NotificationLog
        self.client = APIClient()
        self.client.force_authenticate(Customer.objects.create(username='root', is_staff=True, is_superuser=True))
        self.grace = Customer.objects.create(username='grace', first_name='Grace')
        L = NotificationLog.objects.create
        L(channel='sms', event_type='payment_confirmation', recipient='254722000001', message='Paid', status='sent', customer=self.grace)
        L(channel='sms', event_type='payment_reminder', recipient='254722000002', message='Pay up', status='failed',
          error='UserInBlacklist: the number has blocked promotional SMS')
        L(channel='sms', event_type='payment_reminder', recipient='254722000003', message='Pay up', status='failed',
          error='UserInBlacklist: the number has blocked promotional SMS')
        self.failed_email = L(channel='email', event_type='staff_alert', recipient='boss@example.com', message='Cash added',
                              status='failed', error='SMTPAuthenticationError: bad login')

    def test_summary_breakdowns_and_reasons(self):
        data = self.client.get('/api/notifications/report/').data
        self.assertEqual((data['summary']['total'], data['summary']['sent'], data['summary']['failed']), (4, 1, 3))
        self.assertEqual(data['summary']['delivery_rate'], 25.0)
        sms = next(c for c in data['by_channel'] if c['channel'] == 'sms')
        self.assertEqual((sms['sent'], sms['failed']), (1, 2))
        self.assertEqual(data['top_errors'][0], {'error': 'UserInBlacklist: the number has blocked promotional SMS', 'count': 2})

    def test_filters(self):
        failed = self.client.get('/api/notifications/report/', {'status': 'failed', 'channel': 'sms'}).data
        self.assertEqual(failed['count'], 2)
        self.assertEqual(failed['summary']['total'], 3)  # summary ignores the status filter
        self.assertEqual(self.client.get('/api/notifications/report/', {'search': 'Grace'}).data['count'], 1)

    def test_exports(self):
        for fmt, magic in (('csv', None), ('xlsx', b'PK'), ('pdf', b'%PDF')):
            res = self.client.get('/api/notifications/report/', {'export': fmt})
            self.assertEqual(res.status_code, 200, fmt)
            if magic:
                self.assertTrue(res.content.startswith(magic), fmt)

    def test_resend_logs_a_new_attempt(self):
        from apps.notifications.models import NotificationLog
        with patch('apps.notifications.services.email_service.EmailService.send_email',
                   return_value={'success': True, 'data': {}}) as send:
            res = self.client.post(f'/api/notifications/log/{self.failed_email.id}/resend/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(send.call_args.args[0], 'boss@example.com')
        self.assertEqual(NotificationLog.objects.filter(recipient='boss@example.com', status='sent').count(), 1)

    def test_technician_cannot_view(self):
        from apps.customers.models import Customer
        self.client.force_authenticate(Customer.objects.create(username='tech', is_staff=True, role='technician'))
        self.assertEqual(self.client.get('/api/notifications/report/').status_code, 403)



@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class ConfirmationChannelTests(TestCase):
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
        self.customer = Customer.objects.create(username='grace', first_name='Grace', phone_number='0722000001',
                                                email='grace@example.com', service_type='pppoe')
        self.sub = Subscription.objects.create(customer=self.customer, plan=plan, expiry_date=timezone.now() + timedelta(days=30))

    def confirm(self, wa_ok=True):
        from apps.notifications.tasks import send_payment_confirmation_sms
        ok, bad = {'success': True, 'data': {}}, {'success': False, 'error': 'WhatsApp is not connected', 'data': None}
        with patch('apps.notifications.dispatch._send_whatsapp', return_value=ok if wa_ok else bad) as wa, \
             patch('apps.notifications.dispatch.AfricasTalkingService.send_sms', return_value=ok) as sms, \
             patch('apps.notifications.dispatch.EmailService.send_email', return_value=ok) as email:
            send_payment_confirmation_sms(self.customer.id, 'payment_confirmation', '2500', self.sub.id)
        return wa, sms, email

    def test_whatsapp_is_the_default(self):
        self.assertEqual(NotificationSettings.load().confirmation_channel_list(), ['whatsapp'])
        wa, sms, _ = self.confirm()
        wa.assert_called_once()
        sms.assert_not_called()

    def test_falls_back_to_sms_when_whatsapp_fails(self):
        wa, sms, _ = self.confirm(wa_ok=False)
        wa.assert_called_once()
        sms.assert_called_once()

    def test_no_fallback_when_turned_off(self):
        NotificationSettings.objects.filter(pk=1).update(confirmation_sms_fallback=False)
        _, sms, _ = self.confirm(wa_ok=False)
        sms.assert_not_called()

    def test_several_channels(self):
        NotificationSettings.objects.filter(pk=1).update(confirmation_channels='sms,email')
        wa, sms, email = self.confirm()
        wa.assert_not_called()
        sms.assert_called_once()
        self.assertEqual(email.call_args.args[0], 'grace@example.com')

    def test_setting_needs_a_channel(self):
        from rest_framework.test import APIClient
        from apps.customers.models import Customer
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='root', is_staff=True, is_superuser=True))
        self.assertEqual(client.patch('/api/notifications/settings/', {'confirmation_channels': ''}, format='json').status_code, 400)
        res = client.patch('/api/notifications/settings/', {'confirmation_channels': 'whatsapp,sms,fax'}, format='json')
        self.assertEqual(res.data['confirmation_channels'], 'whatsapp,sms')


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class RenewalReminderTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.billing.models import BillingPlan, Subscription
        from apps.customers.models import Customer
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer',
                       'apps.customers.signals.network_automation.suspend_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        NotificationSettings.objects.update_or_create(pk=1, defaults={})
        self.plan = BillingPlan.objects.create(name='Home 10', service_type='pppoe', download_speed=10, upload_speed=10,
                                               price='2500.00', mikrotik_profile='h10')
        self.hotspot = BillingPlan.objects.create(name='1 Hour', service_type='hotspot', download_speed=2, upload_speed=2,
                                                  price='10.00', mikrotik_profile='hs')
        self.customer = Customer.objects.create(username='grace', first_name='Grace', phone_number='0722000001',
                                                service_type='pppoe')
        self.now = timezone.localtime()
        self.Subscription = Subscription
        self.timedelta = timedelta

    def sub_expiring_in(self, days, plan=None, customer=None):
        return self.Subscription.objects.create(
            customer=customer or self.customer, plan=plan or self.plan,
            expiry_date=self.now + self.timedelta(days=days, minutes=5))

    def run_task(self, wa_ok=True):
        from apps.notifications.tasks import send_expiry_reminders
        ok, bad = {'success': True, 'data': {}}, {'success': False, 'error': 'down', 'data': None}
        with patch('apps.notifications.dispatch._send_whatsapp', return_value=ok if wa_ok else bad) as wa, \
             patch('apps.notifications.dispatch.AfricasTalkingService.send_sms', return_value=ok) as sms:
            count = send_expiry_reminders(force=True)
        return count, wa, sms

    def test_schedule_offsets(self):
        ns = NotificationSettings.load()
        self.assertEqual(ns.reminder_offsets(), [3, 0])
        ns.reminder_days_before, ns.reminder_every_days = 7, 2
        self.assertEqual(ns.reminder_offsets(), [7, 5, 3, 1, 0])
        ns.reminder_on_expiry_day = False
        self.assertEqual(ns.reminder_offsets(), [7, 5, 3, 1])

    def test_sends_on_schedule_days_only_once_via_whatsapp(self):
        self.sub_expiring_in(3)
        count, wa, sms = self.run_task()
        self.assertEqual(count, 1)
        wa.assert_called_once()
        sms.assert_not_called()
        self.assertIn('expires in 3 days', wa.call_args.args[1])
        self.assertEqual(self.run_task()[0], 0)  # dedup same day

    def test_off_schedule_day_and_hotspot_skipped(self):
        self.sub_expiring_in(2)
        other = self.customer.__class__.objects.create(username='hs1', phone_number='0722000002', service_type='hotspot')
        self.sub_expiring_in(3, plan=self.hotspot, customer=other)
        self.assertEqual(self.run_task()[0], 0)

    def test_sms_fallback_and_renewed_customers_skipped(self):
        old = self.sub_expiring_in(3)
        count, wa, sms = self.run_task(wa_ok=False)
        self.assertEqual(count, 1)
        sms.assert_called_once()
        from apps.notifications.models import NotificationLog
        NotificationLog.objects.all().delete()
        self.Subscription.objects.create(customer=self.customer, plan=self.plan,
                                         expiry_date=old.expiry_date + self.timedelta(days=30))
        self.assertEqual(self.run_task()[0], 0)

    def test_hour_gate_and_disabled(self):
        from apps.notifications.tasks import send_expiry_reminders
        self.sub_expiring_in(3)
        NotificationSettings.objects.filter(pk=1).update(reminder_hour=(self.now.hour + 1) % 24)
        self.assertEqual(send_expiry_reminders(), 0)
        NotificationSettings.objects.filter(pk=1).update(reminder_enabled=False)
        self.assertEqual(self.run_task()[0], 0)

    def test_settings_validation(self):
        from rest_framework.test import APIClient
        from apps.customers.models import Customer
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='root', is_staff=True, is_superuser=True))
        self.assertEqual(client.patch('/api/notifications/settings/', {'reminder_every_days': 0}, format='json').status_code, 400)
        res = client.patch('/api/notifications/settings/', {'reminder_days_before': 5, 'reminder_every_days': 2,
                                                            'reminder_service_types': 'pppoe,fax'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['reminder_schedule'], [5, 3, 1, 0])
        self.assertEqual(res.data['reminder_service_types'], 'pppoe')

    def test_expired_followup_goes_to_admins_and_sales(self):
        from apps.notifications.tasks import send_expired_followup, expired_today
        NotificationSettings.objects.filter(pk=1).update(admin_phones='0711000001', sales_phones='0711000002')
        self.Subscription.objects.create(customer=self.customer, plan=self.plan, status='expired',
                                         expiry_date=self.now - self.timedelta(seconds=30))
        # A hotspot customer who expired today is left off the sales list.
        walkup = self.customer.__class__.objects.create(username='walkup', phone_number='0711999999',
                                                        service_type='hotspot')
        self.Subscription.objects.create(customer=walkup, plan=self.hotspot, status='expired',
                                         expiry_date=self.now - self.timedelta(seconds=60))
        self.assertEqual([r['username'] for r in expired_today()], ['grace'])
        with patch('apps.notifications.dispatch.AfricasTalkingService.send_sms',
                   return_value={'success': True, 'data': {}}) as sms:
            self.assertEqual(send_expired_followup(force=True), 2)
        self.assertEqual(sorted(c.args[0] for c in sms.call_args_list), ['0711000001', '0711000002'])
        self.assertIn('Grace', sms.call_args.args[1])
