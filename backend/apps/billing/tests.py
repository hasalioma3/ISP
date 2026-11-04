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
