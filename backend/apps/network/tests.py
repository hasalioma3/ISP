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


class PppoeSecretUpsertTests(TestCase):
	def _service(self, existing):
		secrets = MagicMock(**{'get.return_value': existing})
		api = MagicMock()
		api.get_resource.return_value = secrets
		connection = MagicMock()
		connection.get_api.return_value = api
		service = MikroTikService(host='127.0.0.1', username='u', password='p')
		return service, connection, secrets

	def test_existing_secret_is_overwritten_not_duplicated(self):
		service, connection, secrets = self._service([{'id': '*7', 'name': 'Cyrus', 'password': 'old'}])
		with patch.object(service, '_get_connection', return_value=connection):
			result = service.add_pppoe_secret('Cyrus', 'Cyrus1234', 'Home 5 Mbps')
		self.assertTrue(result['success'])
		secrets.add.assert_not_called()
		secrets.set.assert_called_once_with(
			id='*7', disabled='no', password='Cyrus1234', profile='Home 5 Mbps', service='any',
		)

	def test_missing_secret_is_added(self):
		service, connection, secrets = self._service([{}])  # RouterOS "ghost" empty reply
		with patch.object(service, '_get_connection', return_value=connection):
			result = service.add_pppoe_secret('NewUser', 'pw1234', 'Home 5 Mbps')
		self.assertTrue(result['success'])
		secrets.set.assert_not_called()
		secrets.add.assert_called_once_with(name='NewUser', password='pw1234', profile='Home 5 Mbps', service='any')


class PppoeSecretAdminSyncTests(TestCase):
	def setUp(self):
		from apps.network.models import PPPoESecret, Router
		self.router = Router.objects.create(name='r1', ip_address='10.0.0.1', username='u', password='p')
		self.customer = Customer.objects.create(
			username='cyrus', service_type='pppoe', pppoe_username='Cyrus', pppoe_password='old1234',
		)
		self.secret = PPPoESecret.objects.create(
			customer=self.customer, router=self.router, username='Cyrus', password='old1234', profile='Home 5 Mbps',
		)

	def test_push_renames_existing_secret_and_kicks_session(self):
		from apps.network.services.network_automation import network_automation
		mikrotik = MagicMock()
		mikrotik.update_pppoe_secret.return_value = {'success': True}
		self.secret.username, self.secret.password = 'CyrusK', 'new1234'
		with patch('apps.network.services.network_automation.MikroTikService', return_value=mikrotik):
			result = network_automation.push_pppoe_secret(self.secret, previous_username='Cyrus')
		self.assertTrue(result['success'])
		mikrotik.update_pppoe_secret.assert_called_once_with(
			'Cyrus', name='CyrusK', password='new1234', profile='Home 5 Mbps', disabled='no',
		)
		mikrotik.disconnect_pppoe_session.assert_called_once_with('Cyrus')
		mikrotik.add_pppoe_secret.assert_not_called()

	def test_push_recreates_secret_missing_on_router(self):
		from apps.network.services.network_automation import network_automation
		mikrotik = MagicMock()
		mikrotik.update_pppoe_secret.return_value = {'success': False, 'error': 'Secret not found'}
		mikrotik.add_pppoe_secret.return_value = {'success': True}
		with patch('apps.network.services.network_automation.MikroTikService', return_value=mikrotik):
			result = network_automation.push_pppoe_secret(self.secret)
		self.assertTrue(result['success'])
		mikrotik.add_pppoe_secret.assert_called_once_with('Cyrus', 'old1234', 'Home 5 Mbps')

	def test_admin_edit_updates_customer_and_router(self):
		from django.contrib.admin.sites import AdminSite
		from apps.network.admin import PPPoESecretAdmin
		from apps.network.models import PPPoESecret
		model_admin = PPPoESecretAdmin(PPPoESecret, AdminSite())
		self.secret.password = 'new1234'
		form = MagicMock(changed_data=['password'])
		with patch('apps.network.admin.network_automation.push_pppoe_secret', return_value={'success': True}) as push, \
			 patch.object(model_admin, 'message_user'):
			model_admin.save_model(MagicMock(), self.secret, form, change=True)
		push.assert_called_once()
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.pppoe_password, 'new1234')


class ManagementVlanPlanTests(TestCase):
	PREFIX = 'ISP Billing - Radio Mgmt'

	def _layout(self, **extra):
		layout = {
			'interfaces': ['ether1', 'ether2', 'ether3', 'ether4', 'ether5', 'hotspot_bridge'],
			'addresses': [
				{'address': '192.168.56.20/24', 'interface': 'ether1', 'dynamic': True},
				{'address': '10.5.50.1/24', 'interface': 'hotspot_bridge', 'dynamic': False},
				{'address': '10.5.70.1/24', 'interface': 'hotspot_bridge', 'dynamic': False},
				{'address': '10.5.60.1/32', 'interface': '<pppoe-cyrus>', 'dynamic': True},
			],
			'pools': [
				{'name': 'hotspot_pool', 'ranges': '10.5.50.2-10.5.50.254'},
				{'name': 'pppoe_pool', 'ranges': '10.5.60.2-10.5.60.254'},
			],
			'vlans': [],
		}
		for key, value in extra.items():
			layout[key] = layout[key] + value
		return layout

	def _plan(self, layout):
		from apps.network.services.network_automation import plan_management_vlan
		return plan_management_vlan(layout, 'ether1', 'hotspot_bridge', self.PREFIX, 90)

	def test_picks_free_subnet_next_to_customer_subnets(self):
		plan = self._plan(self._layout())
		self.assertEqual(plan['vlan_id'], 90)
		self.assertEqual(plan['vlan_name'], 'mgmt-vlan90')
		self.assertEqual(plan['subnet'], '10.5.90.0/24')
		self.assertEqual(plan['gateway'], '10.5.90.1/24')
		self.assertEqual(plan['pool_range'], '10.5.90.100-10.5.90.200')
		self.assertEqual(plan['lan_subnet'], '192.168.56.0/24')
		self.assertEqual(plan['wan_ip'], '192.168.56.20')
		self.assertEqual(plan['blocked'], ['10.5.50.0/24', '10.5.60.0/24', '10.5.70.0/24'])
		self.assertFalse(plan['reused'])

	def test_teleport_subnet_is_allowed_alongside_lan(self):
		from apps.network.services.network_automation import plan_management_vlan
		plan = plan_management_vlan(self._layout(), 'ether1', 'hotspot_bridge', self.PREFIX, 90,
									extra_allowed=['192.168.2.0/24'])
		self.assertEqual(plan['allowed'], ['192.168.56.0/24', '192.168.2.0/24'])
		self.assertEqual(plan['subnet'], '10.5.90.0/24')
		with self.assertRaisesRegex(ValueError, 'MIKROTIK_MGMT_VLAN_ALLOWED_SUBNETS'):
			plan_management_vlan(self._layout(), 'ether1', 'hotspot_bridge', self.PREFIX, 90, extra_allowed=['nonsense'])

	def test_skips_vlan_id_and_subnet_already_in_use(self):
		plan = self._plan(self._layout(
			pools=[{'name': 'guests', 'ranges': '10.5.90.10-10.5.90.50'}],
			vlans=[{'name': 'cctv', 'vlan_id': '90', 'interface': 'ether5', 'comment': ''}],
		))
		self.assertEqual(plan['vlan_id'], 91)
		self.assertEqual(plan['subnet'], '10.5.91.0/24')

	def test_rerun_reuses_existing_management_vlan(self):
		plan = self._plan(self._layout(
			addresses=[{'address': '10.5.95.1/24', 'interface': 'mgmt-vlan93', 'dynamic': False}],
			pools=[{'name': 'isp-mgmt-pool', 'ranges': '10.5.95.100-10.5.95.200'}],
			vlans=[{'name': 'mgmt-vlan93', 'vlan_id': '93', 'interface': 'hotspot_bridge', 'comment': f'{self.PREFIX} (VLAN)'}],
		))
		self.assertTrue(plan['reused'])
		self.assertEqual((plan['vlan_id'], plan['vlan_name'], plan['subnet']), (93, 'mgmt-vlan93', '10.5.95.0/24'))
		self.assertNotIn('10.5.95.0/24', plan['blocked'])

	def test_errors_without_wan_address_or_bridge(self):
		from apps.network.services.network_automation import plan_management_vlan
		layout = self._layout()
		layout['addresses'] = [a for a in layout['addresses'] if a['interface'] != 'ether1']
		with self.assertRaisesRegex(ValueError, 'ether1 has no IP'):
			self._plan(layout)
		with self.assertRaisesRegex(ValueError, "doesn't exist"):
			plan_management_vlan(self._layout(), 'ether1', 'bridge-missing', self.PREFIX)


class ManagementVlanApplyTests(TestCase):
	def test_drop_rules_end_up_above_lan_accept(self):
		plan = {
			'vlan_id': 90, 'vlan_name': 'mgmt-vlan90', 'bridge': 'hotspot_bridge', 'wan_interface': 'ether1',
			'wan_ip': '192.168.56.20', 'subnet': '10.5.90.0/24', 'gateway': '10.5.90.1/24',
			'pool_range': '10.5.90.100-10.5.90.200', 'lan_subnet': '192.168.56.0/24',
			'allowed': ['192.168.56.0/24', '192.168.2.0/24'], 'blocked': ['10.5.50.0/24'], 'reused': False,
		}
		resources = {}
		filter_rules = []

		def resource(path):
			if path not in resources:
				mock = MagicMock()
				mock.get.return_value = []
				resources[path] = mock
			return resources[path]

		fr = resource('/ip/firewall/filter')
		fr.get.side_effect = lambda **kw: [{'id': r['id'], 'comment': r['comment']} for r in filter_rules]

		def add_rule(**rule):
			rule['id'] = f"*{len(filter_rules)}"
			pos = next((i for i, r in enumerate(filter_rules) if r['id'] == rule.get('place-before')), len(filter_rules))
			filter_rules.insert(pos, rule)
		fr.add.side_effect = add_rule

		api = MagicMock()
		api.get_resource.side_effect = resource
		connection = MagicMock()
		connection.get_api.return_value = api
		service = MikroTikService(host='127.0.0.1', username='u', password='p')
		with patch.object(service, '_get_connection', return_value=connection):
			result = service.apply_management_vlan(plan, 'ISP Billing - Radio Mgmt', dns_servers='8.8.8.8')

		self.assertTrue(result['success'], result)
		order = [r['comment'] for r in filter_rules]
		for allowed in ('192.168.56.0/24', '192.168.2.0/24'):
			self.assertLess(order.index('ISP Billing - Radio Mgmt [10.5.50.0/24] (Block)'),
							order.index(f'ISP Billing - Radio Mgmt [{allowed}] (Access)'))
		teleport = next(r for r in filter_rules if r['comment'] == 'ISP Billing - Radio Mgmt [192.168.2.0/24] (Access)')
		self.assertEqual((teleport['in-interface'], teleport['dst-address']), ('ether1', '10.5.90.0/24'))
		resources['/interface/vlan'].add.assert_called_once_with(
			comment='ISP Billing - Radio Mgmt (VLAN)', name='mgmt-vlan90', **{'vlan-id': '90'},
			interface='hotspot_bridge', disabled='no',
		)


class BackgroundUserSyncTests(TestCase):
	def setUp(self):
		from apps.network.models import Router
		from rest_framework.test import APIClient
		self.router = Router.objects.create(name='r1', ip_address='10.0.0.1', username='u', password='p')
		self.client = APIClient()
		self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))

	def test_task_records_results(self):
		from apps.network.tasks import sync_router_users
		with patch('apps.network.tasks.network_automation.sync_all_users',
				   return_value={'success': ['PPPoE: cyrus'], 'failed': ['koech: no such profile']}):
			sync_router_users(self.router.pk)
		self.router.refresh_from_db()
		state = self.router.last_user_sync
		self.assertEqual(state['status'], 'done')
		self.assertEqual(state['failed'], ['koech: no such profile'])
		self.assertIsNotNone(self.router.last_sync)

	def test_task_records_a_crash_instead_of_losing_it(self):
		from apps.network.tasks import sync_router_users
		with patch('apps.network.tasks.network_automation.sync_all_users', side_effect=ConnectionError('router went away')):
			sync_router_users(self.router.pk)
		self.router.refresh_from_db()
		self.assertEqual(self.router.last_user_sync['status'], 'error')
		self.assertIn('router went away', self.router.last_user_sync['error'])

	def test_view_starts_background_run_and_refuses_a_second(self):
		url = f'/api/network/routers/{self.router.pk}/sync_users/'
		with patch('apps.network.tasks.sync_router_users.delay') as delay:
			first = self.client.post(url)
			second = self.client.post(url)
		self.assertEqual(first.status_code, 202)
		self.assertTrue(second.data['running'])
		delay.assert_called_once_with(self.router.pk)
		status = self.client.get(f'/api/network/routers/{self.router.pk}/sync_users_status/')
		self.assertEqual(status.data['status'], 'running')


class RouterReachabilityTests(TestCase):
	"""An offline router must not stall page requests (it used to freeze the portal)."""

	def setUp(self):
		from apps.network.models import Router
		from rest_framework.test import APIClient
		self.router = Router.objects.create(name='r1', ip_address='10.0.0.1', username='u', password='p')
		self.client = APIClient()
		self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))

	def health(self):
		return self.client.get('/api/network/routers/health/').data[self.router.pk]

	def test_known_offline_router_is_answered_from_db_without_contacting_it(self):
		from apps.network.models import Router
		seen = timezone.now() - timedelta(hours=2)
		Router.objects.filter(pk=self.router.pk).update(
			is_online=False, status_checked_at=timezone.now(), last_seen_at=seen,
			last_error='timed out', last_health={'cpu_load': 7},
		)
		with patch.object(MikroTikService, 'get_system_health') as live:
			data = self.health()
		live.assert_not_called()
		self.assertFalse(data['online'])
		self.assertEqual(data['last_health'], {'cpu_load': 7})
		self.assertEqual(data['last_seen_at'], seen.isoformat())

	def test_offline_router_is_retried_live_after_the_recheck_window(self):
		from apps.network.models import Router
		Router.objects.filter(pk=self.router.pk).update(
			is_online=False, status_checked_at=timezone.now() - timedelta(minutes=5),
		)
		with patch.object(MikroTikService, 'get_system_health', return_value={'success': True, 'cpu_load': 3}) as live:
			data = self.health()
		live.assert_called_once()
		self.assertTrue(data['online'])
		self.router.refresh_from_db()
		self.assertTrue(self.router.is_online)
		self.assertEqual(self.router.last_health['cpu_load'], 3)

	def test_failed_live_read_marks_router_offline_and_keeps_last_health(self):
		from apps.network.models import Router
		Router.objects.filter(pk=self.router.pk).update(is_online=True, last_health={'cpu_load': 9})
		with patch.object(MikroTikService, 'get_system_health', return_value={'success': False, 'error': 'timed out'}):
			data = self.health()
		self.assertFalse(data['success'])
		self.router.refresh_from_db()
		self.assertFalse(self.router.is_online)
		self.assertEqual(self.router.last_error, 'timed out')
		self.assertEqual(self.router.last_health, {'cpu_load': 9})

	def test_usage_poll_is_the_heartbeat(self):
		with patch.object(MikroTikService, 'get_active_sessions', return_value={'success': False, 'error': 'no route'}):
			collect_usage_statistics()
		self.router.refresh_from_db()
		self.assertFalse(self.router.is_online)
		with patch.object(MikroTikService, 'get_active_sessions', return_value={'success': True, 'sessions': []}):
			collect_usage_statistics()
		self.router.refresh_from_db()
		self.assertTrue(self.router.is_online)
		self.assertIsNotNone(self.router.last_seen_at)

	def test_connect_uses_short_timeout_then_read_timeout(self):
		from django.test import override_settings
		from apps.network.services.mikrotik_service import _TimedApiPool
		pool = _TimedApiPool('10.0.0.1', username='u', password='p', plaintext_login=True)
		sock = MagicMock()
		used = {}

		def fake_get_socket(host, port, timeout, **kw):
			used['timeout'] = timeout
			return sock

		with override_settings(MIKROTIK_CONNECT_TIMEOUT=2.0, MIKROTIK_READ_TIMEOUT=15.0), \
			 patch('routeros_api.api.api_socket.get_socket', side_effect=fake_get_socket), \
			 patch('routeros_api.api.RouterOsApi.login'):
			pool.get_api()
		self.assertEqual(used['timeout'], 2.0)
		sock.settimeout.assert_called_with(15.0)


class OnlineUsersUsageTests(TestCase):
	def test_rows_include_plan_period_and_all_time_usage(self):
		from apps.billing.models import UsageRecord
		from apps.network.models import Router, ActiveSession
		from rest_framework.test import APIClient
		with patch('apps.billing.signals.sync_plan_to_routers.delay'), \
			 patch('apps.billing.signals.network_automation.activate_customer'), \
			 patch('apps.billing.signals.network_automation.suspend_customer', return_value={'success': True}):
			plan = BillingPlan.objects.create(name='P', service_type='pppoe', download_speed=5, upload_speed=5,
											  price='10.00', mikrotik_profile='p')
			customer = Customer.objects.create(username='kim', service_type='pppoe')
			old = Subscription.objects.create(customer=customer, plan=plan, expiry_date=timezone.now() - timedelta(days=1), status='expired')
			current = Subscription.objects.create(customer=customer, plan=plan, expiry_date=timezone.now() + timedelta(days=3))
		GB = 1024 ** 3
		UsageRecord.objects.create(customer=customer, subscription=old, download_bytes=4 * GB, start_time=timezone.now())
		UsageRecord.objects.create(customer=customer, subscription=current, download_bytes=GB, start_time=timezone.now())
		router = Router.objects.create(name='r', ip_address='10.0.0.9', username='u', password='p')
		ActiveSession.objects.create(router=router, customer=customer, session_id='s1', session_type='pppoe',
									 username='kim', ip_address='10.5.60.2', start_time=timezone.now())
		client = APIClient()
		client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
		row = client.get('/api/network/online-users/').data[0]
		self.assertEqual(row['period_usage_gb'], 1.0)
		self.assertEqual(row['total_usage_gb'], 5.0)
