from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import BillingPlan, Voucher, VoucherBatch
from apps.customers.models import Customer


class VoucherUsageReportTests(TestCase):
    def setUp(self):
        patcher = patch('apps.billing.signals.sync_plan_to_routers.delay')
        self.addCleanup(patcher.stop)
        patcher.start()

        self.admin = Customer.objects.create_user(
            username='voucher-report-admin',
            password='test-password',
            role='admin',
            is_staff=True,
        )
        customer = Customer.objects.create(username='voucher-customer', first_name='Voucher User')
        plan = BillingPlan.objects.create(
            name='Voucher plan',
            service_type='hotspot',
            download_speed=10,
            upload_speed=5,
            price='100.00',
            mikrotik_profile='voucher-profile',
        )
        batch = VoucherBatch.objects.create(quantity=2, value='100.00', plan=plan)
        now = timezone.now()
        Voucher.objects.create(
            batch=batch,
            plan=plan,
            code='RECENT1',
            amount='100.00',
            status='used',
            used_by=customer,
            used_at=now,
            used_mac='AA:BB:CC:DD:EE:FF',
        )
        Voucher.objects.create(
            batch=batch,
            plan=plan,
            code='OLDER01',
            amount='100.00',
            status='used',
            used_by=customer,
            used_at=now - timedelta(days=40),
            used_mac='11:22:33:44:55:66',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_report_filters_by_date_and_exports_mac(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(
            '/api/analytics/voucher-usage/',
            {'start_date': today, 'end_date': today},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['voucher_code'], 'RECENT1')
        self.assertEqual(response.data['results'][0]['mac_address'], 'AA:BB:CC:DD:EE:FF')

        csv_response = self.client.get('/api/analytics/voucher-usage/', {'export': 'csv'})
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(b'AA:BB:CC:DD:EE:FF', csv_response.content)
        self.assertIn(b'RECENT1', csv_response.content)

class GatewayStatusTests(TestCase):
    """The dashboard must never wait on Daraja (it froze the page for up to 30s)."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)

    def test_cached_token_means_connected_without_a_request(self):
        from django.core.cache import cache
        from apps.analytics.views import _gateway_status
        cache.set('mpesa_access_token', 'tok', 60)
        with patch('threading.Thread') as thread:
            self.assertIs(_gateway_status(), True)
        thread.assert_not_called()

    def test_no_token_starts_one_background_check_and_reports_checking(self):
        from apps.analytics.views import _gateway_status
        with patch('threading.Thread') as thread:
            self.assertIsNone(_gateway_status())
            self.assertIsNone(_gateway_status())
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_failed_check_is_remembered(self):
        from apps.analytics.views import _check_gateway, _gateway_status
        with patch('apps.payments.services.mpesa_service.mpesa_service.get_access_token', return_value=None):
            _check_gateway()
        with patch('threading.Thread') as thread:
            self.assertIs(_gateway_status(), False)
        thread.assert_not_called()


class SavannaDashboardDataTests(TestCase):
    """Fields added for the redesigned dashboard."""

    def setUp(self):
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            patcher = patch(target)
            self.addCleanup(patcher.stop)
            patcher.start()
        from apps.billing.models import Transaction
        self.Transaction = Transaction
        self.admin = Customer.objects.create(username='boss', is_staff=True, is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.customer = Customer.objects.create(
            username='grace', first_name='Grace', last_name='Wanjiru', phone_number='254722618418',
        )

    def pay(self, amount, days_ago=0, **extra):
        t = self.Transaction.objects.create(
            customer=self.customer, transaction_id=f'T{self.Transaction.objects.count()}',
            amount=amount, payment_method='mpesa', status='completed', **extra,
        )
        self.Transaction.objects.filter(pk=t.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return t

    def test_mask_msisdn(self):
        from apps.analytics.views import mask_msisdn
        self.assertEqual(mask_msisdn('254722618418'), '0722 ••• 418')
        self.assertEqual(mask_msisdn('0722618418'), '0722 ••• 418')
        self.assertEqual(mask_msisdn('a' * 20 + '1234567890' + 'f' * 34), '')  # a hash, not a number
        self.assertEqual(mask_msisdn(''), '')

    def test_revenue_window_and_stk_rate(self):
        from apps.payments.models import PaymentRequest
        from apps.billing.models import BillingPlan
        plan = BillingPlan.objects.create(
            name='Daily', service_type='hotspot', download_speed=5, upload_speed=5,
            price='50.00', mikrotik_profile='daily',
        )
        self.pay(1000, days_ago=1)
        self.pay(500, days_ago=40)
        for state in ('completed', 'completed', 'failed', 'pending'):
            PaymentRequest.objects.create(
                customer=self.customer, plan=plan, phone_number='254722618418', amount=10,
                account_reference='x', transaction_desc='x', status=state,
            )
        data = self.client.get('/api/analytics/dashboard/').data
        self.assertEqual(data['revenue_30d'], 1000.0)
        self.assertEqual(data['revenue_prev_30d'], 500.0)
        self.assertEqual(data['avg_ticket_30d'], 1000.0)
        # pending is still open, so 2 of 3 finished prompts were paid
        self.assertEqual(data['stk_success_rate'], 66.7)

    def test_payments_feed_section_is_masked_and_light(self):
        self.pay(2500, mpesa_receipt_number='SKC4H7XQ2P', mpesa_phone_number='254722618418')
        data = self.client.get('/api/analytics/dashboard/extra/', {'section': 'payments'}).data
        self.assertEqual(list(data.keys()), ['last_transactions'])
        row = data['last_transactions'][0]
        self.assertEqual(row['phone'], '0722 ••• 418')
        self.assertEqual(row['receipt'], 'SKC4H7XQ2P')
        self.assertEqual(row['name'], 'Grace Wanjiru')
        self.assertNotIn('254722618418', str(data))


class ReportsDrilldownAndPaymentsTests(TestCase):
    def setUp(self):
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            patcher = patch(target)
            self.addCleanup(patcher.stop)
            patcher.start()
        from apps.billing.models import BillingPlan, Subscription, Transaction, UsageRecord
        self.client = APIClient()
        self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        self.customer = Customer.objects.create(username='grace', first_name='Grace', service_type='pppoe')
        plan = BillingPlan.objects.create(name='Home 10', service_type='pppoe', download_speed=10,
                                          upload_speed=10, price='2500.00', mikrotik_profile='h10')
        self.sub = Subscription.objects.create(customer=self.customer, plan=plan, expiry_date=timezone.now() + timedelta(days=5))
        Transaction.objects.create(customer=self.customer, subscription=self.sub, transaction_id='SKC1', amount=2500,
                                   payment_method='mpesa', status='completed', mpesa_receipt_number='SKC1')
        Transaction.objects.create(customer=self.customer, transaction_id='BAL-1', amount=500,
                                   payment_method='cash', status='completed')
        UsageRecord.objects.create(customer=self.customer, subscription=self.sub, upload_bytes=1024 ** 3,
                                   download_bytes=2 * 1024 ** 3, start_time=timezone.now())
        self.today = timezone.localdate().isoformat()

    def test_revenue_breakdown(self):
        data = self.client.get('/api/analytics/day-breakdown/', {'kind': 'revenue', 'date': self.today}).data
        self.assertEqual(data['total'], 3000.0)
        self.assertEqual({r['name'] for r in data['by_plan']}, {'Home 10', 'Balance / no plan'})
        self.assertEqual({r['name'] for r in data['by_method']}, {'M-Pesa', 'Cash'})
        self.assertEqual(len(data['items']), 2)

    def test_usage_breakdown_and_daily_series(self):
        data = self.client.get('/api/analytics/day-breakdown/', {'kind': 'usage', 'date': self.today}).data
        self.assertEqual(data['total_gb'], 3.0)
        self.assertEqual(data['items'][0]['username'], 'grace')
        days = self.client.get('/api/analytics/usage-daily/', {'start_date': self.today, 'end_date': self.today}).data
        self.assertEqual(days, [{'date': self.today, 'upload_gb': 1.0, 'download_gb': 2.0, 'total_gb': 3.0, 'users': 1}])

    def test_technician_cannot_see_revenue_breakdown(self):
        self.client.force_authenticate(Customer.objects.create(username='tech', is_staff=True, role='technician'))
        res = self.client.get('/api/analytics/day-breakdown/', {'kind': 'revenue', 'date': self.today})
        self.assertEqual(res.status_code, 403)

    def test_recent_payments_lists_matched_c2b_once(self):
        from apps.billing.models import Transaction
        from apps.payments.models import C2BPayment
        C2BPayment.objects.create(transaction_id='SKC9', amount=1000, msisdn='hash', matched_customer=self.customer, raw_data={},
                                  status='activated')
        # The processor writes a Transaction twin with the same code.
        Transaction.objects.create(customer=self.customer, transaction_id='SKC9', amount=1000,
                                   payment_method='mpesa', status='completed', mpesa_receipt_number='SKC9')
        data = self.client.get('/api/analytics/recent-payments/').data
        codes = [r['transaction_id'] for r in data['results']]
        self.assertEqual(sorted(codes), ['SKC1', 'SKC9'])
        self.assertEqual(data['count'], 2)
        self.assertEqual([r['method'] for r in data['results'] if r['transaction_id'] == 'SKC9'], ['c2b'])
