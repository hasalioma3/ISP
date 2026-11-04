from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import BillingPlan, Subscription
from apps.customers.models import Customer


class MacOwnershipTests(TestCase):
	MAC = '72:A3:CB:88:E0:03'

	def setUp(self):
		for target in ('apps.billing.signals.sync_plan_to_routers.delay',
					   'apps.billing.signals.network_automation.activate_customer'):
			patcher = patch(target)
			self.addCleanup(patcher.stop)
			patcher.start()
		self.plan = BillingPlan.objects.create(
			name='MAC plan', service_type='hotspot', download_speed=10,
			upload_speed=5, price='10.00', mikrotik_profile='mac-plan',
		)

	def test_new_owner_takes_mac_from_customer_without_live_subscription(self):
		old = Customer.objects.create(username='OLDVOUCHER', hotspot_mac_address=self.MAC)
		new = Customer.objects.create(username='buyer', hotspot_mac_address=self.MAC.lower())

		old.refresh_from_db()
		new.refresh_from_db()
		self.assertIsNone(old.hotspot_mac_address)
		self.assertEqual(new.hotspot_mac_address, self.MAC.lower())

	def test_customer_with_live_subscription_keeps_mac(self):
		holder = Customer.objects.create(username='holder', hotspot_mac_address=self.MAC)
		Subscription.objects.create(
			customer=holder, plan=self.plan, expiry_date=timezone.now() + timedelta(days=1),
		)
		Customer.objects.create(username='second', hotspot_mac_address=self.MAC)

		holder.refresh_from_db()
		self.assertEqual(holder.hotspot_mac_address, self.MAC)


class PppoeOnlyRegistrationTests(TestCase):
	def test_registration_ignores_submitted_hotspot_service_type(self):
		client = APIClient()
		response = client.post('/api/customers/register/', {
			'username': 'register-pppoe-only',
			'email': 'pppoe@example.test',
			'password': 'StrongPassphrase#2026',
			'password2': 'StrongPassphrase#2026',
			'phone_number': '0712345678',
			'first_name': 'Test',
			'last_name': 'Customer',
			'service_type': 'hotspot',
		}, format='json')

		self.assertEqual(response.status_code, 201)
		customer = Customer.objects.get(username='register-pppoe-only')
		self.assertEqual(customer.service_type, 'pppoe')
		self.assertEqual(customer.pppoe_username, customer.username)
		self.assertEqual(customer.pppoe_password, 'StrongPassphrase#2026')
		self.assertIsNone(customer.hotspot_username)
