from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import BillingPlan, Subscription, UsageRecord
from apps.customers.models import Customer
from apps.network.services.mikrotik_service import MikroTikService
from apps.network.tasks import (
	collect_usage_statistics, enforce_subscription_data_limits, enforce_subscription_fup,
	update_usage_record,
)


class StaticPlanSyncTests(TestCase):
	def test_plan_speed_is_pushed_to_active_static_customers_only(self):
		from apps.network.services.network_automation import network_automation
		with patch('apps.billing.signals.sync_plan_to_routers.delay'), \
			 patch('apps.billing.signals.network_automation.activate_customer'):
			plan = BillingPlan.objects.create(
				name='Static 20', service_type='static', download_speed=20,
				upload_speed=8, price='50.00', mikrotik_profile='static-20',
			)
			active = Customer.objects.create(username='static-active', service_type='static', static_ip_address='10.9.0.5')
			expired = Customer.objects.create(username='static-expired', service_type='static', static_ip_address='10.9.0.6')
			Subscription.objects.create(customer=active, plan=plan, expiry_date=timezone.now() + timedelta(days=5))
			Subscription.objects.create(customer=expired, plan=plan, status='expired', expiry_date=timezone.now() - timedelta(days=1))

		mikrotik = MagicMock()
		mikrotik.add_simple_queue.return_value = {'success': True}
		mikrotik.add_ip_binding_bypass.return_value = {'success': True}
		result = network_automation.sync_static_plan(plan, MagicMock(), mikrotik)

		self.assertEqual(result, {'success': ['static-active'], 'failed': []})
		mikrotik.add_simple_queue.assert_called_once_with(
			name='static-active', target='10.9.0.5/32', max_limit='8M/20M', comment='ISP Billing - Static 20',
		)
		mikrotik.add_ip_binding_bypass.assert_called_once_with('10.9.0.5', comment='static-static-active')


class StaticOnlineDetectionTests(TestCase):
	def test_only_live_addresses_are_online(self):
		resources = {
			'/ip/hotspot/host': MagicMock(**{'get.return_value': [
				{'address': '10.9.0.5', 'mac-address': 'AA:BB:CC:00:00:05', 'uptime': '1h', 'idle-time': '3s'},
				{'address': '10.9.0.6', 'mac-address': 'AA:BB:CC:00:00:06', 'uptime': '2h', 'idle-time': '4m10s'},
			]}),
			'/ip/arp': MagicMock(**{'get.return_value': [
				{'address': '10.9.0.9', 'mac-address': 'AA:BB:CC:00:00:09', 'complete': 'true', 'status': 'reachable'},
				{'address': '10.9.0.10', 'mac-address': 'AA:BB:CC:00:00:10', 'complete': 'true', 'status': 'stale'},
				{'address': '10.9.0.11', 'mac-address': 'AA:BB:CC:00:00:11', 'complete': 'true', 'dynamic': 'false'},
			]}),
			'/queue/simple': MagicMock(**{'get.return_value': [
				{'name': 'online-by-host', 'bytes': '1000/2000', 'rate': '0/0'},
				{'name': 'idle-host', 'bytes': '50/60', 'rate': '0/0'},
				{'name': 'stale-arp', 'bytes': '5/5', 'rate': '0/0'},
				{'name': 'static-arp-busy', 'bytes': '7/8', 'rate': '1200/56000'},
				{'name': 'unseen', 'bytes': '300/400', 'rate': '0/0'},
			]}),
		}
		api = MagicMock()
		api.get_resource.side_effect = lambda path: resources[path]
		connection = MagicMock()
		connection.get_api.return_value = api
		service = MikroTikService(host='127.0.0.1', username='u', password='p')
		targets = [
			{'username': 'online-by-host', 'ip': '10.9.0.5'},
			{'username': 'idle-host', 'ip': '10.9.0.6'},
			{'username': 'online-by-arp', 'ip': '10.9.0.9'},
			{'username': 'stale-arp', 'ip': '10.9.0.10'},
			{'username': 'static-arp-busy', 'ip': '10.9.0.11'},
			{'username': 'unseen', 'ip': '10.9.0.12'},
			{'username': 'no-queue-offline', 'ip': '10.9.0.7'},
		]

		with patch.object(service, '_get_connection', return_value=connection):
			result = service.get_static_sessions(targets)

		self.assertTrue(result['success'])
		by_user = {s['username']: s for s in result['sessions']}
		# Every queue is reported so its counters keep being tracked offline.
		self.assertNotIn('no-queue-offline', by_user)
		online = {u for u, s in by_user.items() if s['online']}
		self.assertEqual(online, {'online-by-host', 'online-by-arp', 'static-arp-busy'})
		self.assertEqual(by_user['online-by-host']['service_type'], 'static')
		self.assertEqual((by_user['online-by-host']['upload_bytes'], by_user['online-by-host']['download_bytes']), (1000, 2000))
		self.assertEqual((by_user['unseen']['upload_bytes'], by_user['unseen']['download_bytes']), (300, 400))
		self.assertEqual(by_user['online-by-arp']['mac_address'], 'AA:BB:CC:00:00:09')


class StaticUsageAccountingTests(TestCase):
	def _poll(self, sessions):
		from apps.network.models import Router
		router = Router.objects.first()
		mikrotik = MagicMock()
		mikrotik.get_active_sessions.return_value = {'success': True, 'sessions': []}
		mikrotik.get_static_sessions.return_value = {'success': True, 'sessions': sessions}
		with patch('apps.network.tasks.MikroTikService', return_value=mikrotik), \
			 patch('apps.network.tasks._static_targets_for_router', return_value=[{'username': 'static-u', 'ip': '10.9.0.5'}]):
			from apps.network.tasks import _collect_usage_once
			_collect_usage_once()
		return router

	def _session(self, up, down, online):
		return {
			'service_type': 'static', 'session_id': 'static-static-u', 'username': 'static-u',
			'address': '10.9.0.5', 'mac_address': None, 'uptime': None,
			'upload_bytes': up, 'download_bytes': down, 'online': online,
		}

	def test_going_offline_does_not_recount_lifetime_queue_bytes(self):
		from apps.network.models import ActiveSession, Router
		Router.objects.create(name='r1', ip_address='10.0.0.1', username='u', password='p')
		with patch('apps.billing.signals.sync_plan_to_routers.delay'), \
			 patch('apps.billing.signals.network_automation.activate_customer'):
			plan = BillingPlan.objects.create(
				name='Static 10', service_type='static', download_speed=10,
				upload_speed=5, price='50.00', mikrotik_profile='static-10',
			)
			customer = Customer.objects.create(username='static-u', service_type='static', static_ip_address='10.9.0.5')
			subscription = Subscription.objects.create(customer=customer, plan=plan, expiry_date=timezone.now() + timedelta(days=5))

		self._poll([self._session(1_000_000, 9_000_000, True)])   # first sight: baseline only
		self._poll([self._session(1_000_100, 9_000_200, True)])   # +100/+200
		self.assertTrue(ActiveSession.objects.filter(username='static-u').exists())
		self._poll([self._session(1_000_100, 9_000_200, False)])  # idle, not live
		self.assertFalse(ActiveSession.objects.filter(username='static-u').exists())
		self._poll([self._session(1_000_150, 9_000_250, True)])   # back: +50/+50 only

		usage = UsageRecord.objects.filter(subscription=subscription)
		self.assertEqual(sum(r.upload_bytes for r in usage), 150)
		self.assertEqual(sum(r.download_bytes for r in usage), 250)
		self.assertTrue(ActiveSession.objects.filter(username='static-u').exists())


class HotspotSessionRefreshTests(TestCase):
	def test_rate_pair_parsing(self):
		parse = MikroTikService._parse_rate_pair
		self.assertEqual(parse('5M/10M'), (5_000_000, 10_000_000))
		self.assertEqual(parse('5000000/10000000'), (5_000_000, 10_000_000))
		self.assertEqual(parse('512k/1M 2M/2M'), (512_000, 1_000_000))
		self.assertIsNone(parse(None))
		self.assertIsNone(parse('garbage'))

	def test_only_sessions_with_stale_queue_are_disconnected(self):
		resources = {
			'/ip/hotspot/user/profile': MagicMock(**{'get.return_value': [{'name': 'fast', 'rate-limit': '60M/60M'}]}),
			'/ip/hotspot/user': MagicMock(**{'get.return_value': [
				{'id': '*1', 'name': 'stale', 'profile': 'fast'},
				{'id': '*2', 'name': 'fresh', 'profile': 'fast'},
			]}),
			'/queue/simple': MagicMock(**{'get.return_value': [
				{'name': '<hotspot-stale>', 'max-limit': '10000000/10000000'},
				{'name': '<hotspot-fresh>', 'max-limit': '60000000/60000000'},
			]}),
			'/ip/hotspot/active': MagicMock(**{'get.return_value': [
				{'id': '*a', 'user': 'stale'}, {'id': '*b', 'user': 'fresh'},
			]}),
		}
		api = MagicMock()
		api.get_resource.side_effect = lambda path: resources[path]
		connection = MagicMock()
		connection.get_api.return_value = api
		service = MikroTikService(host='127.0.0.1', username='u', password='p')

		with patch.object(service, '_get_connection', return_value=connection):
			result = service.refresh_hotspot_sessions()

		self.assertEqual(result, {'success': True, 'refreshed': ['stale']})
		resources['/ip/hotspot/active'].remove.assert_called_once_with(id='*a')


class SharedMacUsageTests(TestCase):
	def test_usage_goes_to_customer_with_active_subscription(self):
		with patch('apps.billing.signals.sync_plan_to_routers.delay'), \
			 patch('apps.billing.signals.network_automation.activate_customer'):
			mac = '72:A3:CB:88:E0:03'
			payer = Customer.objects.create(username='payer_E003')
			Customer.objects.create(username='OLDVOUCHER')
			# Legacy rows predate MAC ownership, so set the duplicate without save().
			Customer.objects.update(hotspot_mac_address=mac)
			plan = BillingPlan.objects.create(
				name='Shared MAC plan', service_type='hotspot', download_speed=10,
				upload_speed=5, price='10.00', mikrotik_profile='shared-mac',
			)
			subscription = Subscription.objects.create(
				customer=payer, plan=plan, expiry_date=timezone.now() + timedelta(days=1),
			)

			recorded = update_usage_record(mac, 100, 200, mac, '10.5.50.248')

		self.assertTrue(recorded)
		self.assertEqual(UsageRecord.objects.filter(subscription=subscription).count(), 1)


class UsagePollingOrderTests(TestCase):
	def test_enforcement_runs_right_after_collection(self):
		calls = []
		with patch('redis.from_url', side_effect=RuntimeError('no redis')), \
			 patch('apps.network.tasks._collect_usage_once', side_effect=lambda: calls.append('collect')), \
			 patch('apps.network.tasks.enforce_subscription_data_limits', side_effect=lambda: calls.append('cap')), \
			 patch('apps.network.tasks.enforce_subscription_fup', side_effect=lambda: calls.append('fup')):
			collect_usage_statistics()

		self.assertEqual(calls, ['collect', 'cap', 'fup'])


class DataLimitEnforcementTests(TestCase):
	def setUp(self):
		patcher = patch('apps.billing.signals.sync_plan_to_routers.delay')
		self.addCleanup(patcher.stop)
		patcher.start()
		self.activate_patcher = patch('apps.billing.signals.network_automation.activate_customer')
		self.addCleanup(self.activate_patcher.stop)
		self.activate_patcher.start()
		suspend_patcher = patch(
			'apps.billing.signals.network_automation.suspend_customer',
			return_value={'success': True},
		)
		self.addCleanup(suspend_patcher.stop)
		self.suspend_mock = suspend_patcher.start()

		self.customer = Customer.objects.create(username='data-cap-customer')
		self.plan = BillingPlan.objects.create(
			name='1 GB test',
			service_type='hotspot',
			download_speed=10,
			upload_speed=5,
			price='100.00',
			data_limit_gb=1,
			mikrotik_profile='test-profile',
		)
		self.subscription = Subscription.objects.create(
			customer=self.customer,
			plan=self.plan,
			expiry_date=timezone.now() + timedelta(days=1),
		)

	def add_usage(self, upload_bytes, download_bytes):
		UsageRecord.objects.create(
			customer=self.customer,
			subscription=self.subscription,
			upload_bytes=upload_bytes,
			download_bytes=download_bytes,
			start_time=timezone.now(),
		)

	def test_expires_when_combined_upload_and_download_reach_limit(self):
		self.add_usage(600 * 1024 ** 2, 424 * 1024 ** 2)

		self.assertEqual(enforce_subscription_data_limits(), 1)

		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.status, 'expired')
		self.suspend_mock.assert_called_once_with(self.customer)

	def test_keeps_subscription_active_below_combined_limit(self):
		self.add_usage(600 * 1024 ** 2, 423 * 1024 ** 2)

		self.assertEqual(enforce_subscription_data_limits(), 0)

		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.status, 'active')
		self.suspend_mock.assert_not_called()

	def test_half_gigabyte_data_limit_is_enforced(self):
		self.plan.data_limit_gb = '0.500'
		self.plan.save(update_fields=['data_limit_gb'])
		self.add_usage(256 * 1024 ** 2, 256 * 1024 ** 2)

		self.assertEqual(enforce_subscription_data_limits(), 1)

		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.status, 'expired')


class FupEnforcementTests(TestCase):
	def setUp(self):
		patcher = patch('apps.billing.signals.sync_plan_to_routers.delay')
		self.addCleanup(patcher.stop)
		patcher.start()
		activate_patcher = patch('apps.billing.signals.network_automation.activate_customer')
		self.addCleanup(activate_patcher.stop)
		activate_patcher.start()
		self.apply_fup = patch(
			'apps.network.tasks.network_automation.apply_customer_fup',
			return_value={'success': True},
		)
		self.addCleanup(self.apply_fup.stop)
		self.apply_fup_mock = self.apply_fup.start()
		self.customer = Customer.objects.create(username='fup-customer')
		self.plan = BillingPlan.objects.create(
			name='FUP test',
			service_type='hotspot',
			download_speed=10,
			upload_speed=5,
			price='100.00',
			mikrotik_profile='fup-test',
			fup_limit_gb=1,
			fup_download_speed=3,
			fup_upload_speed=1,
		)
		self.subscription = Subscription.objects.create(
			customer=self.customer,
			plan=self.plan,
			expiry_date=timezone.now() + timedelta(days=1),
		)

	def add_usage(self, upload_bytes, download_bytes):
		UsageRecord.objects.create(
			customer=self.customer,
			subscription=self.subscription,
			upload_bytes=upload_bytes,
			download_bytes=download_bytes,
			start_time=timezone.now(),
		)

	def test_applies_fup_when_combined_usage_reaches_threshold(self):
		self.add_usage(600 * 1024 ** 2, 424 * 1024 ** 2)

		self.assertEqual(enforce_subscription_fup(), 1)

		self.subscription.refresh_from_db()
		self.assertTrue(self.subscription.fup_applied)
		self.apply_fup_mock.assert_called_once_with(self.customer, self.plan)

	def test_does_not_apply_fup_below_threshold(self):
		self.add_usage(600 * 1024 ** 2, 423 * 1024 ** 2)

		self.assertEqual(enforce_subscription_fup(), 0)

		self.subscription.refresh_from_db()
		self.assertFalse(self.subscription.fup_applied)
		self.apply_fup_mock.assert_not_called()

	def test_router_failure_leaves_fup_eligible_for_retry(self):
		self.add_usage(1024 ** 3, 0)
		self.apply_fup_mock.return_value = {'success': False, 'error': 'router unavailable'}

		self.assertEqual(enforce_subscription_fup(), 0)

		self.subscription.refresh_from_db()
		self.assertFalse(self.subscription.fup_applied)
