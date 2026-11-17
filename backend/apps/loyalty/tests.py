"""Tests for the batch: phone normalisation, hotspot payment-failed SMS,
daily FUP, data usage alerts, top hotspot users, archival, loyalty and
invoicing/eTIMS. Kept in one module so they run together:
  manage.py test apps.loyalty"""
import gzip
import json
import os
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import BillingPlan, Subscription, Transaction, UsageRecord
from apps.customers.models import Customer

GB = 1024 ** 3


class Patched(TestCase):
    def setUp(self):
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer',
                       'apps.customers.signals.network_automation.activate_customer'):
            try:
                p = patch(target)
                p.start()
                self.addCleanup(p.stop)
            except AttributeError:
                pass
        self.admin = Customer.objects.create_superuser(username='boss', password='x', email='boss@example.com')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def plan(self, **kw):
        defaults = dict(name=f"Plan {BillingPlan.objects.count()}", service_type='pppoe', download_speed=10,
                        upload_speed=5, price='1000.00', mikrotik_profile=f"p{BillingPlan.objects.count()}")
        defaults.update(kw)
        return BillingPlan.objects.create(**defaults)

    def sub(self, customer, plan):
        return Subscription.objects.create(customer=customer, plan=plan, expiry_date=timezone.now() + timedelta(days=10))

    def usage(self, sub, nbytes):
        UsageRecord.objects.create(customer=sub.customer, subscription=sub, upload_bytes=0, download_bytes=nbytes,
                                   start_time=timezone.now())


class PhoneTests(TestCase):
    def test_normalize(self):
        from apps.payments.services.phone_hash import local_phone, normalize_phone
        for raw in ('725316559', '0725316559', '254725316559', '+254 725 316 559', '725-316-559'):
            self.assertEqual(normalize_phone(raw), '254725316559', raw)
            self.assertEqual(local_phone(raw), '0725316559', raw)
        self.assertEqual(normalize_phone('112345678'), '254112345678')

    def test_sms_accepts_nine_digits(self):
        from apps.notifications.services.africastalking_service import AfricasTalkingService
        svc = AfricasTalkingService.__new__(AfricasTalkingService)
        svc.username, svc.api_key, svc.sender_id, svc.base_url = 'u', 'k', '', 'https://x'
        resp = MagicMock(status_code=201)
        resp.json.return_value = {'SMSMessageData': {'Recipients': [{'status': 'Success', 'statusCode': 101}]}}
        with patch('apps.notifications.services.africastalking_service.requests.post', return_value=resp) as post:
            svc.send_sms('725316559', 'hi')
        self.assertEqual(post.call_args.kwargs['data']['to'], '+254725316559')

    def test_customer_phone_stored_local(self):
        c = Customer.objects.create(username='p1', phone_number='725316559')
        self.assertEqual(c.phone_number, '254725316559')
        self.assertEqual(Customer.objects.create(username='p2', phone_number='0725316559').phone_number, '0725316559')
        from apps.payments.services.phone_hash import hash_phone
        self.assertEqual(c.phone_hash, hash_phone('254725316559'))

    def test_stk_serializer(self):
        from apps.payments.serializers import InitiatePaymentSerializer
        s = InitiatePaymentSerializer(data={'plan_id': 1, 'phone_number': '725316559'})
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data['phone_number'], '0725316559')
        self.assertFalse(InitiatePaymentSerializer(data={'plan_id': 1, 'phone_number': '12345'}).is_valid())


class PaymentFailedTests(Patched):
    def test_hotspot_customers_get_no_failed_sms(self):
        from apps.notifications.tasks import send_payment_failed_notification
        hs = Customer.objects.create(username='0711000001', phone_number='0711000001', service_type='hotspot')
        pp = Customer.objects.create(username='pp', phone_number='0711000002', service_type='pppoe')
        hplan, pplan = self.plan(service_type='hotspot'), self.plan()
        with patch('apps.notifications.tasks.send_and_log') as send:
            send_payment_failed_notification(hs.pk, hplan.pk, 'cancelled')
            self.assertFalse(send.called)
            send_payment_failed_notification(pp.pk, pplan.pk, 'cancelled')
            self.assertTrue(send.called)


class DailyFupTests(Patched):
    def setUp(self):
        super().setUp()
        p = patch('apps.network.tasks.network_automation.apply_customer_fup', return_value={'success': True})
        self.apply = p.start()
        self.addCleanup(p.stop)
        n = patch('apps.notifications.tasks.send_daily_fup_notice.delay')
        self.notice = n.start()
        self.addCleanup(n.stop)
        self.customer = Customer.objects.create(username='dfup', service_type='pppoe')
        self.p = self.plan(daily_fup_limit_gb=Decimal('5'), daily_fup_download_speed=2, daily_fup_upload_speed=1)
        self.s = self.sub(self.customer, self.p)

    def test_applies_after_daily_limit_and_lifts_next_day(self):
        from apps.network.tasks import enforce_daily_fup
        self.usage(self.s, 4 * GB)
        enforce_daily_fup()
        self.assertFalse(self.apply.called)
        self.usage(self.s, 2 * GB)
        enforce_daily_fup()
        self.apply.assert_called_once()
        self.assertEqual(self.apply.call_args.kwargs['profile_name'], self.p.get_daily_fup_mikrotik_profile())
        self.s.refresh_from_db()
        self.assertEqual(self.s.daily_fup_date, timezone.localdate())
        self.notice.assert_called_once()
        enforce_daily_fup()  # already throttled today: nothing new
        self.assertEqual(self.apply.call_count, 1)
        # Next day: lifted back to the plan's own profile.
        Subscription.objects.filter(pk=self.s.pk).update(daily_fup_date=timezone.localdate() - timedelta(days=1))
        UsageRecord.objects.update(created_at=timezone.now() - timedelta(days=1))
        enforce_daily_fup()
        self.assertEqual(self.apply.call_args.kwargs['profile_name'], self.p.mikrotik_profile)
        self.s.refresh_from_db()
        self.assertIsNone(self.s.daily_fup_date)

    def test_yesterdays_usage_does_not_count(self):
        from apps.network.tasks import enforce_daily_fup
        self.usage(self.s, 9 * GB)
        UsageRecord.objects.update(created_at=timezone.now() - timedelta(days=1))
        enforce_daily_fup()
        self.assertFalse(self.apply.called)

    def test_serializer_rules(self):
        from apps.billing.serializers import BillingPlanSerializer
        base = dict(name='X', service_type='hotspot', download_speed=10, upload_speed=5, price='10',
                    mikrotik_profile='x', daily_fup_limit_gb='2', daily_fup_download_speed=2, daily_fup_upload_speed=1)
        self.assertFalse(BillingPlanSerializer(data=base).is_valid())
        self.assertTrue(BillingPlanSerializer(data={**base, 'service_type': 'pppoe'}).is_valid())
        self.assertFalse(BillingPlanSerializer(data={**base, 'service_type': 'pppoe', 'daily_fup_upload_speed': 9}).is_valid())

    def test_reactivation_keeps_daily_profile(self):
        from apps.network.services.network_automation import network_automation
        Subscription.objects.filter(pk=self.s.pk).update(daily_fup_date=timezone.localdate())
        self.assertEqual(network_automation._pppoe_profile_for(self.customer, self.p), self.p.get_daily_fup_mikrotik_profile())


class UsageAlertTests(Patched):
    def test_thresholds_sent_once_highest_only(self):
        from apps.network.tasks import send_data_usage_alerts
        c = Customer.objects.create(username='0722000000', phone_number='0722000000', service_type='hotspot')
        s = self.sub(c, self.plan(service_type='hotspot', data_limit_gb=Decimal('10')))
        with patch('apps.notifications.tasks.send_data_usage_alert.delay') as alert:
            self.usage(s, 4 * GB)
            send_data_usage_alerts()
            self.assertFalse(alert.called)
            self.usage(s, int(3.8 * GB))  # 78%: crosses 50 and 75 at once
            send_data_usage_alerts()
            alert.assert_called_once()
            self.assertEqual(alert.call_args.args[1], 75)
            send_data_usage_alerts()
            self.assertEqual(alert.call_count, 1)
            self.usage(s, 2 * GB)  # 98%
            send_data_usage_alerts()
            self.assertEqual(alert.call_args.args[1], 95)
        s.refresh_from_db()
        self.assertEqual(s.usage_alerts_sent, [50, 75, 95])

    def test_message(self):
        from apps.notifications.tasks import send_data_usage_alert
        c = Customer.objects.create(username='0722000001', phone_number='0722000001', service_type='hotspot')
        s = self.sub(c, self.plan(service_type='hotspot', data_limit_gb=Decimal('2')))
        with patch('apps.notifications.tasks.send_with_fallback') as send:
            send_data_usage_alert(s.pk, 50, GB)
        self.assertIn('50%', send.call_args.args[1])
        self.assertIn('1 GB left', send.call_args.args[1])


class TopHotspotTests(Patched):
    def test_ranking(self):
        hp = self.plan(service_type='hotspot')
        subs = []
        for i, amount in enumerate([3, 9, 1]):
            c = Customer.objects.create(username=f'07000000{i}', service_type='hotspot')
            s = self.sub(c, hp)
            self.usage(s, amount * GB)
            subs.append(s)
        r = self.api.get('/api/analytics/top-hotspot-users/?period=daily')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([row['username'] for row in r.data['results']], ['070000001', '070000000', '070000002'])
        self.assertEqual(r.data['results'][0]['total_gb'], 9.0)


class ArchiveTests(Patched):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_archive_and_restore(self):
        from apps.archive import service
        from apps.archive.models import ArchiveSettings
        from apps.notifications.models import NotificationLog
        c = Customer.objects.create(username='arch')
        old = NotificationLog.objects.create(customer=c, event_type='welcome', message='old', status='sent')
        NotificationLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=400))
        NotificationLog.objects.create(customer=c, event_type='welcome', message='new', status='sent')
        cfg = ArchiveSettings.load()
        cfg.datasets, cfg.months = 'notification_logs', 12
        cfg.save()
        with override_settings(BACKUP_DIR=self.tmp):
            r = self.api.get('/api/archive/settings/')
            self.assertEqual(next(d for d in r.data['preview']['datasets'] if d['key'] == 'notification_logs')['rows'], 1)
            runs = service.run_all('test', force=True)
            self.assertEqual(runs[0].rows, 1)
            self.assertEqual(list(NotificationLog.objects.values_list('message', flat=True)), ['new'])
            with gzip.open(service.file_path(runs[0]), 'rt') as fh:
                self.assertEqual(json.loads(fh.readline())['fields']['message'], 'old')
            self.assertEqual(self.api.post(f'/api/archive/runs/{runs[0].pk}/').data['restored'], 1)
            self.assertEqual(NotificationLog.objects.count(), 2)

    def test_superadmin_only(self):
        staff = Customer.objects.create(username='tech', is_staff=True, role='admin')
        api = APIClient()
        api.force_authenticate(staff)
        self.assertEqual(api.get('/api/archive/settings/').status_code, 403)


class LoyaltyTests(Patched):
    def setUp(self):
        super().setUp()
        from apps.loyalty.models import LoyaltySettings
        cfg = LoyaltySettings.load()
        cfg.enabled, cfg.kes_per_point, cfg.min_redeem_points, cfg.welcome_bonus = True, Decimal('100'), 10, 5
        cfg.save()
        self.c = Customer.objects.create(username='loyal', phone_number='0733000000', service_type='pppoe')

    def pay(self, amount, method='mpesa', ref=None):
        n = Transaction.objects.count()
        with self.captureOnCommitCallbacks(execute=True):
            return Transaction.objects.create(customer=self.c, transaction_id=ref or f'T{n}', amount=amount,
                                              payment_method=method, status='completed')

    def test_earn_redeem(self):
        from apps.loyalty.services import balance
        with patch('apps.loyalty.tasks.notify.delay') as notify:
            t = self.pay('2550')
            self.assertEqual(balance(self.c), 25 + 5)  # 25 earned + welcome bonus
            t.save()  # re-save never earns twice
            self.pay('500', method='balance')  # balance-funded: no points
            self.assertEqual(balance(self.c), 30)
            self.assertTrue(notify.called)
            r = self.api.post(f'/api/loyalty/customers/{self.c.pk}/', {'action': 'redeem', 'points': 20}, format='json')
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data['account_balance'], '20.00')
            r = self.api.post(f'/api/loyalty/customers/{self.c.pk}/', {'action': 'redeem', 'points': 20}, format='json')
            self.assertEqual(r.status_code, 400)  # only 10 left

    def test_self_redeem_and_hotspot_excluded(self):
        with patch('apps.loyalty.tasks.notify.delay'):
            self.pay('1000')
            hs = Customer.objects.create(username='hs', service_type='hotspot')
            Transaction.objects.create(customer=hs, transaction_id='H1', amount=1000, status='completed')
        from apps.loyalty.services import balance
        self.assertEqual(balance(hs), 0)
        api = APIClient()
        api.force_authenticate(self.c)
        r = api.get('/api/loyalty/me/')
        self.assertEqual(r.data['points'], 15)
        with patch('apps.loyalty.tasks.notify.delay'):
            r = api.post('/api/loyalty/me/', {'points': 15}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['points'], 0)

    def test_expiry_fifo(self):
        from apps.loyalty.models import LoyaltySettings, LoyaltyTransaction
        from apps.loyalty.services import balance, expire_points, redeem
        with patch('apps.loyalty.tasks.notify.delay'):
            self.pay('5000')  # 50 + 5 bonus
            LoyaltyTransaction.objects.update(created_at=timezone.now() - timedelta(days=400))
            redeem(self.c, 20)
            self.pay('1000')  # 10 new
        cfg = LoyaltySettings.load()
        cfg.expiry_months = 12
        cfg.save()
        self.assertEqual(expire_points(), 35)  # 55 old - 20 spent
        self.assertEqual(balance(self.c), 10)


@override_settings(NOTIFICATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode())
class InvoiceTests(Patched):
    def setUp(self):
        super().setUp()
        from apps.invoicing.models import InvoiceSettings
        cfg = InvoiceSettings.load()
        cfg.vat_registered, cfg.company_pin = True, 'P051234567X'
        cfg.save()
        self.c = Customer.objects.create(username='inv', first_name='Jane', last_name='W', phone_number='0712345678',
                                         service_type='pppoe')
        self.p = self.plan(name='Fibre 20')
        self.s = self.sub(self.c, self.p)
        self.t = Transaction.objects.create(customer=self.c, subscription=self.s, transaction_id='SKL1', amount='2320',
                                            payment_method='mpesa', mpesa_receipt_number='SKL1', status='completed')

    def test_from_transaction_vat_inclusive_and_pdfs(self):
        r = self.api.post('/api/invoicing/invoices/from-transaction/', {'transaction_id': self.t.pk, 'customer_pin': 'a123456789z'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['total'], '2320.00')
        self.assertEqual(r.data['tax'], '320.00')
        self.assertEqual(r.data['status'], 'paid')
        self.assertEqual(r.data['customer_pin'], 'A123456789Z')
        self.assertIn('Fibre 20', r.data['lines'][0]['description'])
        again = self.api.post('/api/invoicing/invoices/from-transaction/', {'transaction_id': self.t.pk}, format='json')
        self.assertEqual(again.status_code, 200)
        for template in ('classic', 'modern', 'minimal', 'bold', 'compact'):
            pdf = self.api.get(f"/api/invoicing/invoices/{r.data['id']}/pdf/?template={template}")
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b'%PDF'), template)
            preview = self.api.get(f'/api/invoicing/templates/preview/?template={template}')
            self.assertTrue(preview.content.startswith(b'%PDF'))

    def test_hotspot_not_invoiced(self):
        from apps.invoicing.services import InvoiceError, invoice_for_transaction
        hs = Customer.objects.create(username='hs1', service_type='hotspot')
        t = Transaction.objects.create(customer=hs, transaction_id='H9', amount=50, status='completed')
        with self.assertRaises(InvoiceError):
            invoice_for_transaction(t)

    def test_etims_sign_and_credit_note(self):
        from apps.invoicing.models import InvoiceSettings
        from apps.invoicing.services import invoice_for_transaction, void
        cfg = InvoiceSettings.load()
        cfg.etims_enabled, cfg.etims_cmc_key, cfg.etims_auto_sign = True, 'KEY', False
        cfg.save()
        inv, _ = invoice_for_transaction(self.t)
        self.assertEqual(inv.etims_status, 'none')
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'resultCd': '000', 'resultMsg': 'ok', 'data': {
            'curRcptNo': 7, 'totRcptNo': 7, 'intrlData': 'INTRL', 'rcptSign': 'SIGN123', 'sdcDateTime': '20261117120000'}}
        with patch('apps.invoicing.etims.requests.post', return_value=resp) as post:
            r = self.api.post(f'/api/invoicing/invoices/{inv.pk}/action/', {'action': 'sign'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        payload = post.call_args.kwargs['json']
        self.assertEqual(post.call_args.kwargs['headers']['cmcKey'], 'KEY')
        self.assertEqual(payload['invcNo'], 1)
        self.assertEqual(payload['rcptTyCd'], 'S')
        self.assertEqual(payload['pmtTyCd'], '06')
        self.assertEqual(payload['totAmt'], 2320.0)
        self.assertEqual(payload['taxAmtB'], 320.0)
        self.assertEqual(r.data['etims_signature'], 'SIGN123')
        self.assertIn('SIGN123', r.data['etims_qr_url'])
        self.assertTrue(self.api.get(f'/api/invoicing/invoices/{inv.pk}/pdf/').content.startswith(b'%PDF'))
        inv.refresh_from_db()
        with patch('apps.invoicing.etims.requests.post', return_value=resp) as post:
            void(inv)
        self.assertEqual(post.call_args.kwargs['json']['rcptTyCd'], 'R')
        self.assertEqual(post.call_args.kwargs['json']['orgInvcNo'], 1)
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.etims_status), ('void', 'credited'))

    def test_etims_failure_kept_for_retry(self):
        from apps.invoicing import etims
        from apps.invoicing.models import InvoiceSettings
        from apps.invoicing.services import invoice_for_transaction
        cfg = InvoiceSettings.load()
        cfg.etims_enabled, cfg.etims_cmc_key = True, 'KEY'
        cfg.save()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'resultCd': '910', 'resultMsg': 'Request parameter error'}
        with patch('apps.invoicing.etims.requests.post', return_value=resp):
            inv, _ = invoice_for_transaction(self.t)  # auto-sign fails, invoice still made
        self.assertEqual(inv.etims_status, 'failed')
        self.assertIn('910', inv.etims_error)
        self.assertEqual(inv.etims_invoice_no, 1)

    def test_customer_sees_own_invoices_only(self):
        from apps.invoicing.services import invoice_for_transaction
        inv, _ = invoice_for_transaction(self.t)
        api = APIClient()
        api.force_authenticate(self.c)
        self.assertEqual(len(api.get('/api/invoicing/mine/').data), 1)
        self.assertEqual(api.get(f'/api/invoicing/mine/{inv.pk}/pdf/').status_code, 200)
        other = Customer.objects.create(username='other')
        api.force_authenticate(other)
        self.assertEqual(api.get(f'/api/invoicing/mine/{inv.pk}/pdf/').status_code, 404)
        self.assertEqual(api.get('/api/invoicing/invoices/').status_code, 403)

    def test_auto_invoice_signal(self):
        from apps.invoicing.models import InvoiceSettings
        cfg = InvoiceSettings.load()
        cfg.auto_invoice = True
        cfg.save()
        with patch('apps.invoicing.tasks.invoice_transaction.apply_async') as task, \
                self.captureOnCommitCallbacks(execute=True):
            Transaction.objects.create(customer=self.c, transaction_id='SKL2', amount=100, status='completed')
        task.assert_called_once()
