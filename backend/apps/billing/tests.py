from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.billing.models import BillingPlan
from apps.billing.serializers import BillingPlanSerializer
from apps.customers.models import Customer


class PublicBillingPlanVisibilityTests(TestCase):
	def setUp(self):
		patcher = patch('apps.billing.signals.sync_plan_to_routers.delay')
		self.addCleanup(patcher.stop)
		patcher.start()

		self.public_plan = BillingPlan.objects.create(
			name='Public hotspot plan',
			service_type='hotspot',
			download_speed=10,
			upload_speed=5,
			price='100.00',
			mikrotik_profile='public-profile',
		)
		self.promo_plan = BillingPlan.objects.create(
			name='Voucher promo plan',
			service_type='hotspot',
			download_speed=10,
			upload_speed=5,
			price='50.00',
			mikrotik_profile='promo-profile',
			is_active=True,
			is_promo=True,
		)
		self.client = APIClient()

	def test_public_list_and_retrieve_hide_active_promo_plan(self):
		response = self.client.get('/api/billing/plans/')
		plans = response.data.get('results', response.data)

		self.assertEqual(response.status_code, 200)
		self.assertEqual([plan['id'] for plan in plans], [self.public_plan.id])
		self.assertEqual(
			self.client.get(f'/api/billing/plans/{self.promo_plan.id}/').status_code,
			404,
		)

	def test_staff_can_still_see_active_promo_plan(self):
		admin = Customer.objects.create_user(
			username='billing-plan-admin',
			password='test-password',
			role='admin',
			is_staff=True,
		)
		self.client.force_authenticate(user=admin)

		response = self.client.get('/api/billing/plans/')
		plans = response.data.get('results', response.data)

		self.assertEqual(response.status_code, 200)
		self.assertIn(self.promo_plan.id, [plan['id'] for plan in plans])


class FupPlanValidationTests(TestCase):
	def setUp(self):
		self.plan_data = {
			'name': 'FUP plan',
			'service_type': 'pppoe',
			'download_speed': 20,
			'upload_speed': 10,
			'price': '100.00',
			'mikrotik_profile': 'fup-profile',
		}

	def test_fup_is_optional(self):
		serializer = BillingPlanSerializer(data=self.plan_data)
		self.assertTrue(serializer.is_valid(), serializer.errors)
		self.assertIsNone(serializer.validated_data.get('fup_limit_gb'))

	def test_fractional_data_limit_is_accepted(self):
		serializer = BillingPlanSerializer(data={**self.plan_data, 'data_limit_gb': '0.5'})
		self.assertTrue(serializer.is_valid(), serializer.errors)
		self.assertEqual(str(serializer.validated_data['data_limit_gb']), '0.500')

	def test_fup_requires_limit_and_both_speeds(self):
		serializer = BillingPlanSerializer(data={**self.plan_data, 'fup_limit_gb': 10})
		self.assertFalse(serializer.is_valid())
		self.assertIn('fup_limit_gb', serializer.errors)

	def test_fup_speeds_must_not_exceed_plan_speeds(self):
		serializer = BillingPlanSerializer(data={
			**self.plan_data,
			'fup_limit_gb': 10,
			'fup_download_speed': 21,
			'fup_upload_speed': 5,
		})
		self.assertFalse(serializer.is_valid())
		self.assertIn('fup_download_speed', serializer.errors)

	def test_valid_fup_configuration_is_accepted(self):
		serializer = BillingPlanSerializer(data={
			**self.plan_data,
			'fup_limit_gb': 10,
			'fup_download_speed': 5,
			'fup_upload_speed': 2,
		})
		self.assertTrue(serializer.is_valid(), serializer.errors)

	def test_fup_threshold_must_be_below_hard_data_limit(self):
		serializer = BillingPlanSerializer(data={
			**self.plan_data,
			'data_limit_gb': 10,
			'fup_limit_gb': 10,
			'fup_download_speed': 5,
			'fup_upload_speed': 2,
		})
		self.assertFalse(serializer.is_valid())
		self.assertIn('fup_limit_gb', serializer.errors)


class BillingPlanCreateReliabilityTests(TestCase):
	def setUp(self):
		self.admin = Customer.objects.create_user(
			username='plan-create-admin',
			password='test-password',
			role='admin',
			is_staff=True,
		)
		self.client = APIClient()
		self.client.force_authenticate(user=self.admin)
		self.plan_data = {
			'name': 'Reliable plan',
			'service_type': 'pppoe',
			'download_speed': 10,
			'upload_speed': 5,
			'price': '100.00',
			'mikrotik_profile': 'reliable-profile',
		}

	def test_duplicate_name_is_rejected_case_insensitively(self):
		BillingPlan.objects.create(**self.plan_data)
		serializer = BillingPlanSerializer(data={**self.plan_data, 'name': ' reliable PLAN '})

		self.assertFalse(serializer.is_valid())
		self.assertIn('name', serializer.errors)

	def test_plan_create_succeeds_when_celery_broker_is_unavailable(self):
		with patch(
			'apps.billing.signals.sync_plan_to_routers.delay',
			side_effect=RuntimeError('Redis unavailable'),
		), self.captureOnCommitCallbacks(execute=True):
			response = self.client.post('/api/billing/plans/', self.plan_data, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertTrue(BillingPlan.objects.filter(name='Reliable plan').exists())


class FourLetterVoucherTests(TestCase):
	"""Voucher codes are 4 letters, case-insensitive, and wrong guesses are limited."""

	def setUp(self):
		from django.core.cache import cache
		cache.clear()
		self.addCleanup(cache.clear)
		for target in ('apps.billing.signals.sync_plan_to_routers.delay',
					   'apps.billing.signals.network_automation.activate_customer',
					   'apps.customers.signals.network_automation.activate_customer'):
			patcher = patch(target)
			self.addCleanup(patcher.stop)
			patcher.start()
		self.plan = BillingPlan.objects.create(
			name='Daily', service_type='hotspot', download_speed=5, upload_speed=5,
			price='50.00', mikrotik_profile='daily',
		)
		self.client = APIClient()

	def generate(self, n=20):
		self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
		res = self.client.post('/api/billing/vouchers/generate/', {'quantity': n, 'plan_id': self.plan.pk}, format='json')
		self.client.force_authenticate(None)
		self.assertEqual(res.status_code, 201, res.data)
		return [v['code'] for v in res.data['vouchers']]

	def test_codes_are_four_unambiguous_letters(self):
		codes = self.generate(50)
		self.assertEqual(len(set(codes)), 50)
		for code in codes:
			self.assertRegex(code, r'^[A-HJ-NP-Z]{4}$')

	def test_redeem_is_case_insensitive_and_login_too(self):
		code = self.generate(1)[0]
		res = self.client.post('/api/billing/vouchers/redeem/', {'code': f'  {code.lower()} '}, format='json')
		self.assertEqual(res.status_code, 200, res.data)
		login = self.client.post('/api/customers/login/', {'username': code.lower(), 'password': code.lower()}, format='json')
		self.assertEqual(login.status_code, 200, login.data)

	def test_old_six_character_codes_still_redeem(self):
		from apps.billing.models import Voucher, VoucherBatch
		batch = VoucherBatch.objects.create(quantity=1, value=50, plan=self.plan)
		Voucher.objects.create(batch=batch, code='AB12CD', amount=50, plan=self.plan, status='active')
		res = self.client.post('/api/billing/vouchers/redeem/', {'code': 'ab12cd'}, format='json')
		self.assertEqual(res.status_code, 200, res.data)

	def test_wrong_guesses_are_limited_per_device(self):
		code = self.generate(1)[0]
		wrong = 'ZZZZ' if code != 'ZZZZ' else 'YYYY'
		for _ in range(5):
			res = self.client.post('/api/billing/vouchers/redeem/', {'code': wrong, 'mac_address': 'AA:BB:CC:DD:EE:FF'}, format='json')
			self.assertEqual(res.status_code, 400)
		res = self.client.post('/api/billing/vouchers/redeem/', {'code': code, 'mac_address': 'aa-bb-cc-dd-ee-ff'}, format='json')
		self.assertEqual(res.status_code, 429)
		# Another device on the same site isn't blocked.
		res = self.client.post('/api/billing/vouchers/redeem/', {'code': code, 'mac_address': '11:22:33:44:55:66'}, format='json')
		self.assertEqual(res.status_code, 200, res.data)


class VoucherBatchToSalesTests(TestCase):
    def setUp(self):
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        from apps.billing.models import Voucher, VoucherBatch
        from apps.notifications.models import NotificationSettings
        NotificationSettings.objects.update_or_create(pk=1, defaults={'sales_phones': '0711000009'})
        self.plan = BillingPlan.objects.create(name='Daily', service_type='hotspot', download_speed=5, upload_speed=5,
                                               price='50.00', mikrotik_profile='d')
        self.batch = VoucherBatch.objects.create(quantity=3, value=50, plan=self.plan)
        for code, st in (('ABCD', 'active'), ('EFGH', 'active'), ('JKLM', 'used')):
            Voucher.objects.create(batch=self.batch, code=code, amount=50, plan=self.plan, status=st)
        self.seller = Customer.objects.create(username='mo', first_name='Mo', is_staff=True, role='sales',
                                              phone_number='0711000001')
        self.client = APIClient()
        self.client.force_authenticate(self.seller)

    def test_contacts_include_sales_staff_and_settings(self):
        res = self.client.get('/api/billing/batches/sales-contacts/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual({c['value'] for c in res.data['contacts']}, {'0711000001', '0711000009'})

    def test_send_unused_codes(self):
        from apps.notifications.admin_emails import send_voucher_batch
        with patch('apps.notifications.dispatch.AfricasTalkingService.send_sms',
                   return_value={'success': True, 'data': {}}) as sms, \
             patch('apps.notifications.admin_emails.send_voucher_batch.delay', side_effect=send_voucher_batch):
            res = self.client.post(f'/api/billing/batches/{self.batch.id}/send/',
                                   {'phones': ['0711000009'], 'channels': ['sms']}, format='json')
        self.assertEqual(res.status_code, 200)
        text = sms.call_args.args[1]
        self.assertIn('ABCD', text)
        self.assertNotIn('JKLM', text)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.sent_to, '0711000009')

    def test_needs_a_recipient(self):
        res = self.client.post(f'/api/billing/batches/{self.batch.id}/send/', {'phones': []}, format='json')
        self.assertEqual(res.status_code, 400)
