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