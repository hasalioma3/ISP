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


class SubscriberListRedesignTests(TestCase):
	"""Tab counts, expiring filter and bulk STK for the redesigned Subscribers page."""

	def setUp(self):
		for target in ('apps.billing.signals.sync_plan_to_routers.delay',
					   'apps.billing.signals.network_automation.activate_customer'):
			patcher = patch(target)
			self.addCleanup(patcher.stop)
			patcher.start()
		self.plan = BillingPlan.objects.create(
			name='Home 10', service_type='pppoe', download_speed=10,
			upload_speed=10, price='2500.00', mikrotik_profile='home-10',
		)
		self.client = APIClient()
		self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
		self.soon = Customer.objects.create(username='soon', phone_number='0722000001', service_type='pppoe')
		self.later = Customer.objects.create(username='later', phone_number='0722000002', service_type='pppoe')
		self.gone = Customer.objects.create(username='gone', service_type='pppoe')
		Subscription.objects.create(customer=self.soon, plan=self.plan, expiry_date=timezone.now() + timedelta(days=2))
		Subscription.objects.create(customer=self.later, plan=self.plan, expiry_date=timezone.now() + timedelta(days=20))
		Customer.objects.filter(pk__in=[self.soon.pk, self.later.pk]).update(status='active')
		Customer.objects.filter(pk=self.gone.pk).update(status='expired')

	def test_summary_counts_and_expiring_filter(self):
		counts = self.client.get('/api/customers/subscribers/summary/').data
		self.assertEqual(counts['all'], 3)
		self.assertEqual(counts['active'], 2)
		self.assertEqual(counts['expiring'], 1)
		self.assertEqual(counts['expired'], 1)
		rows = self.client.get('/api/customers/subscribers/', {'expiring': 'true'}).data['results']
		self.assertEqual([r['username'] for r in rows], ['soon'])
		self.assertEqual(rows[0]['current_plan_id'], self.plan.id)
		self.assertEqual(rows[0]['current_plan_price'], '2500.00')

	def test_bulk_stk_reminder_uses_current_plan_and_reports_skips(self):
		with patch('apps.payments.views.mpesa_service.initiate_stk_push',
				   return_value={'success': True, 'data': {'CheckoutRequestID': 'ws_1'}}) as stk:
			res = self.client.post('/api/customers/subscribers/bulk-stk-reminder/',
								   {'ids': [self.soon.pk, self.gone.pk]}, format='json')
		self.assertEqual(res.status_code, 200)
		stk.assert_called_once()
		self.assertEqual(stk.call_args.kwargs['phone_number'], '0722000001')
		self.assertEqual(len(res.data['success']), 1)
		self.assertIn('gone', res.data['failed'][0])

	def test_bulk_stk_reminder_is_admin_only(self):
		tech = Customer.objects.create(username='tech', is_staff=True, role='technician')
		self.client.force_authenticate(tech)
		res = self.client.post('/api/customers/subscribers/bulk-stk-reminder/', {'ids': [self.soon.pk]}, format='json')
		self.assertEqual(res.status_code, 403)


class StaffMoneyActionsTests(TestCase):
	"""todo 1-2: technicians can't move money; superadmin extend-to-date; customer + staff notified."""

	def setUp(self):
		for target in ('apps.billing.signals.sync_plan_to_routers.delay',
					   'apps.billing.signals.network_automation.activate_customer',
					   'apps.billing.signals.network_automation.suspend_customer'):
			patcher = patch(target)
			self.addCleanup(patcher.stop)
			mock = patcher.start()
			mock.return_value = {'success': True}
		self.plan = BillingPlan.objects.create(
			name='Home 10', service_type='pppoe', download_speed=10,
			upload_speed=10, price='2500.00', mikrotik_profile='home-10',
		)
		self.customer = Customer.objects.create(username='grace', phone_number='0722000001', service_type='pppoe')
		self.client = APIClient()

	def as_user(self, **kw):
		user = Customer.objects.create(username=kw.pop('username', 'staff'), is_staff=True, **kw)
		self.client.force_authenticate(user)
		return user

	def test_technician_blocked_from_topup_cash_and_switch(self):
		self.as_user(role='technician')
		base = f'/api/customers/subscribers/{self.customer.pk}'
		self.assertEqual(self.client.post(f'{base}/topup/', {'plan_id': self.plan.pk}).status_code, 403)
		self.assertEqual(self.client.post(f'{base}/add_balance/', {'amount': 100}).status_code, 403)
		self.assertEqual(self.client.post(f'{base}/switch_plan/', {'plan_id': self.plan.pk}).status_code, 403)
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.account_balance, 0)

	def test_add_balance_notifies_customer_and_staff(self):
		self.as_user(role='admin')
		with patch('apps.notifications.tasks.send_customer_account_notice.delay') as cust, \
			 patch('apps.notifications.tasks.send_staff_alert.delay') as staff, \
			 self.captureOnCommitCallbacks(execute=True):
			res = self.client.post(f'/api/customers/subscribers/{self.customer.pk}/add_balance/', {'amount': 300})
		self.assertEqual(res.status_code, 200)
		self.assertEqual(cust.call_args.args[1], 'cash_added')
		self.assertEqual(cust.call_args.args[2]['amount'], '300')
		self.assertEqual(cust.call_args.args[3], 'balance_credit')
		self.assertIn('grace', staff.call_args.args[0])

	def test_extend_is_superuser_only(self):
		Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(days=1))
		self.as_user(role='admin')
		res = self.client.post(f'/api/customers/subscribers/{self.customer.pk}/extend/', {'expiry_date': '2099-01-01'})
		self.assertEqual(res.status_code, 403)

	def test_extend_reactivates_expired_subscription(self):
		sub = Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() - timedelta(days=3))
		Subscription.objects.filter(pk=sub.pk).update(status='expired')
		Customer.objects.filter(pk=self.customer.pk).update(status='expired')
		self.as_user(username='root', is_superuser=True)
		target = (timezone.localdate() + timedelta(days=10)).isoformat()
		with patch('apps.notifications.tasks.send_customer_account_notice.delay') as cust, \
			 patch('apps.notifications.tasks.send_staff_alert.delay') as staff, \
			 self.captureOnCommitCallbacks(execute=True):
			res = self.client.post(f'/api/customers/subscribers/{self.customer.pk}/extend/', {'expiry_date': target})
		self.assertEqual(res.status_code, 200, res.data)
		self.assertTrue(res.data['reactivated'])
		sub.refresh_from_db()
		self.customer.refresh_from_db()
		self.assertEqual(sub.status, 'active')
		self.assertEqual(timezone.localtime(sub.expiry_date).date().isoformat(), target)
		self.assertEqual(self.customer.status, 'active')
		self.assertEqual(cust.call_args.args[1], 'subscription_extended')
		self.assertEqual(cust.call_args.args[2]['action'], 'reactivated')
		self.assertIn('reactivated', staff.call_args.args[0])

	def test_extend_rejects_past_dates(self):
		Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(days=1))
		self.as_user(username='root', is_superuser=True)
		res = self.client.post(f'/api/customers/subscribers/{self.customer.pk}/extend/', {'expiry_date': '2020-01-01'})
		self.assertEqual(res.status_code, 400)

	def test_staff_alert_task_uses_configured_number(self):
		from apps.notifications.models import NotificationSettings, NotificationLog
		from apps.notifications.tasks import send_staff_alert
		NotificationSettings.objects.update_or_create(pk=1, defaults={'staff_alert_phone': '0711000000'})
		with patch('apps.notifications.dispatch.AfricasTalkingService.send_sms', return_value={'success': True, 'data': {}}) as sms:
			send_staff_alert('hello', customer_id=self.customer.pk)
		sms.assert_called_once_with('0711000000', 'hello')
		self.assertEqual(NotificationLog.objects.get().event_type, 'staff_alert')

	def test_staff_alert_task_is_off_without_number(self):
		from apps.notifications.tasks import send_staff_alert
		with patch('apps.notifications.dispatch.AfricasTalkingService.send_sms') as sms:
			send_staff_alert('hello')
		sms.assert_not_called()

	def test_usage_tab_has_plan_and_all_time_totals(self):
		from apps.billing.models import UsageRecord
		old = Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() - timedelta(days=1))
		Subscription.objects.filter(pk=old.pk).update(status='expired')
		current = Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(days=5))
		GB = 1024 ** 3
		UsageRecord.objects.create(customer=self.customer, subscription=old, upload_bytes=GB, download_bytes=GB, start_time=timezone.now())
		UsageRecord.objects.create(customer=self.customer, subscription=current, upload_bytes=0, download_bytes=3 * GB, start_time=timezone.now())
		self.as_user(role='admin')
		data = self.client.get(f'/api/customers/subscribers/{self.customer.pk}/usage/').data
		self.assertEqual(data['totals']['total_gb'], 5.0)
		self.assertEqual(data['plan_totals']['total_gb'], 3.0)
		self.client.force_authenticate(self.customer)
		mine = self.client.get('/api/billing/usage/summary/').data
		self.assertEqual(mine['plan_totals']['total_gb'], 3.0)
		self.assertEqual(mine['totals']['total_gb'], 5.0)


class SubscriberExportAndReminderTests(TestCase):
	def setUp(self):
		for target in ('apps.billing.signals.sync_plan_to_routers.delay',
					   'apps.billing.signals.network_automation.activate_customer'):
			patcher = patch(target)
			self.addCleanup(patcher.stop)
			patcher.start()
		self.plan = BillingPlan.objects.create(
			name='Home 10', service_type='pppoe', download_speed=10,
			upload_speed=10, price='2500.00', mikrotik_profile='home-10',
		)
		self.grace = Customer.objects.create(username='grace', first_name='Grace', phone_number='254722618418', service_type='pppoe')
		self.nophone = Customer.objects.create(username='nophone', service_type='pppoe')
		self.noplan = Customer.objects.create(username='noplan', phone_number='0711000000', service_type='pppoe')
		for c in (self.grace, self.nophone):
			Subscription.objects.create(customer=c, plan=self.plan, expiry_date=timezone.now() + timedelta(days=3))
		self.client = APIClient()
		self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))

	def test_export_selected_and_filtered(self):
		res = self.client.get('/api/customers/subscribers/export/', {'ids': str(self.grace.pk), 'export': 'csv'})
		body = res.content.decode()
		self.assertIn('grace', body)
		self.assertNotIn('nophone', body)
		self.assertIn('254722618418', body)  # full number in the admin download
		pdf = self.client.get('/api/customers/subscribers/export/', {'export': 'pdf'})
		self.assertTrue(pdf.content.startswith(b'%PDF'))

	@patch('django.conf.settings.MPESA_SHORTCODE_TYPE', 'till')
	@patch('django.conf.settings.MPESA_TILL_NUMBER', '4993011')
	def test_reminder_preview_uses_buy_goods_and_registered_number(self):
		res = self.client.post('/api/customers/subscribers/bulk-reminder/',
							   {'ids': [self.grace.pk], 'channel': 'sms', 'preview': True}, format='json')
		message = res.data['preview']
		self.assertIn('Hi Grace', message)
		self.assertIn('Buy Goods, Till 4993011', message)
		self.assertIn('from 0722618418', message)
		self.assertIn('KES 2,500', message)

	def test_reminder_queues_and_skips(self):
		with patch('apps.notifications.tasks.send_payment_reminder.delay') as task:
			res = self.client.post('/api/customers/subscribers/bulk-reminder/',
								   {'ids': [self.grace.pk, self.nophone.pk, self.noplan.pk], 'channel': 'whatsapp'}, format='json')
		self.assertEqual(res.data['queued'], 1)
		task.assert_called_once_with(self.grace.pk, 'whatsapp')
		self.assertEqual(len(res.data['skipped']), 2)

	def test_reminder_task_sends_and_logs(self):
		from apps.notifications.models import NotificationLog
		from apps.notifications.tasks import send_payment_reminder
		with patch('apps.notifications.dispatch.AfricasTalkingService.send_sms', return_value={'success': True, 'data': {}}) as sms:
			send_payment_reminder(self.grace.pk, 'sms')
		self.assertEqual(sms.call_args.args[0], '254722618418')
		self.assertEqual(NotificationLog.objects.get().event_type, 'payment_reminder')

	def test_technician_cannot_send_reminders(self):
		self.client.force_authenticate(Customer.objects.create(username='tech', is_staff=True, role='technician'))
		res = self.client.post('/api/customers/subscribers/bulk-reminder/', {'ids': [self.grace.pk]}, format='json')
		self.assertEqual(res.status_code, 403)


class RenewedCustomerStatusTests(TestCase):
	"""An old subscription expiring after a renewal must not mark the customer expired or cut them off."""

	def setUp(self):
		patcher = patch('apps.billing.signals.sync_plan_to_routers.delay')
		self.addCleanup(patcher.stop)
		patcher.start()
		self.activate = patch('apps.billing.signals.network_automation.activate_customer').start()
		self.suspend = patch('apps.billing.signals.network_automation.suspend_customer', return_value={'success': True}).start()
		self.addCleanup(patch.stopall)
		self.plan = BillingPlan.objects.create(
			name='Home 10', service_type='pppoe', download_speed=10,
			upload_speed=10, price='1500.00', mikrotik_profile='home-10',
		)
		self.customer = Customer.objects.create(username='esther', service_type='pppoe')

	def test_old_subscription_expiring_after_renewal(self):
		renewed = Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(days=60))
		old = Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(hours=1))
		# The old row is the newest by created_at -- the case that used to flip the status.
		Subscription.objects.filter(pk=renewed.pk).update(created_at=timezone.now() - timedelta(days=1))
		self.suspend.reset_mock()
		old.status = 'expired'
		old.save()
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.status, 'active')
		self.suspend.assert_not_called()

	def test_reconcile_fixes_stale_status(self):
		from apps.billing.services import reconcile_customer_statuses
		Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(days=5))
		Customer.objects.filter(pk=self.customer.pk).update(status='expired')
		self.assertEqual(reconcile_customer_statuses(), 1)
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.status, 'active')

	def test_lone_expiry_still_suspends(self):
		sub = Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(hours=1))
		sub.status = 'expired'
		sub.save()
		self.suspend.assert_called()
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.status, 'expired')
