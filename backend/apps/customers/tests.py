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


class PppoeCredentialsEndpointTests(TestCase):
	def setUp(self):
		from apps.network.models import PPPoESecret, Router
		router = Router.objects.create(name='r1', ip_address='10.0.0.1', username='u', password='p')
		self.customer = Customer.objects.create(
			username='cyrus', service_type='pppoe', pppoe_username='Cyrus', pppoe_password='old1234',
		)
		PPPoESecret.objects.create(customer=self.customer, router=router, username='Cyrus', password='old1234', profile='p5')
		Customer.objects.create(username='other', service_type='pppoe', pppoe_username='Taken')
		self.url = f'/api/customers/subscribers/{self.customer.pk}/pppoe-credentials/'
		self.client = APIClient()

	def _login(self, **flags):
		user = Customer.objects.create(username=f"staff{len(flags)}", is_staff=True, **flags)
		self.client.force_authenticate(user)

	def test_superuser_change_is_saved_and_pushed(self):
		from apps.network.models import PPPoESecret
		self._login(is_superuser=True)
		with patch('apps.network.services.network_automation.network_automation.push_pppoe_secret',
				   return_value={'success': True}) as push:
			res = self.client.post(self.url, {'pppoe_username': 'CyrusK', 'pppoe_password': 'new1234'}, format='json')
		self.assertEqual(res.status_code, 200)
		self.assertTrue(res.data['router_synced'])
		self.assertEqual(push.call_args.kwargs['previous_username'], 'Cyrus')
		self.customer.refresh_from_db()
		self.assertEqual((self.customer.pppoe_username, self.customer.pppoe_password), ('CyrusK', 'new1234'))
		self.assertEqual(PPPoESecret.objects.get(customer=self.customer).username, 'CyrusK')

	def test_regular_admin_is_refused(self):
		self._login(role='admin')
		res = self.client.post(self.url, {'pppoe_username': 'CyrusK', 'pppoe_password': 'new1234'}, format='json')
		self.assertEqual(res.status_code, 403)
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.pppoe_password, 'old1234')

	def test_username_of_another_customer_is_rejected(self):
		self._login(is_superuser=True)
		res = self.client.post(self.url, {'pppoe_username': 'Taken', 'pppoe_password': 'new1234'}, format='json')
		self.assertEqual(res.status_code, 400)
