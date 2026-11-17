import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from cloud.accounts.models import User
from cloud.billing.ledger import balance
from cloud.billing.models import Collection
from cloud.core.models import PlatformSettings
from cloud.pricing.models import PricingPlan, PricingTier
from cloud.tenants.models import Tenant, UsageSnapshot
from cloud.tenants.orchestrator import FakeOrchestrator

DATA = Path(tempfile.mkdtemp(prefix='saas-test-'))
CERT = None


def make_plan(**kw):
    defaults = dict(name='Standard', code='standard', is_default=True, base_fee=Decimal('500'), included_subscribers=20,
                    service_types='pppoe,static', count_basis='active', count_method='peak', minimum_charge=Decimal('0'))
    defaults.update(kw)
    plan = PricingPlan.objects.create(**defaults)
    for up_to, price in ((100, '30'), (None, '10')):
        PricingTier.objects.create(plan=plan, up_to=up_to, unit_price=Decimal(price))
    return plan


def stk_body(receipt='QK1234ABCD', amount=500, code=0, checkout='ws_CO_1'):
    items = [{'Name': 'Amount', 'Value': amount}, {'Name': 'MpesaReceiptNumber', 'Value': receipt},
             {'Name': 'TransactionDate', 'Value': 20261116101500}, {'Name': 'PhoneNumber', 'Value': 254712345678}]
    cb = {'MerchantRequestID': 'm1', 'CheckoutRequestID': checkout, 'ResultCode': code, 'ResultDesc': 'ok'}
    if code == 0:
        cb['CallbackMetadata'] = {'Item': items}
    return {'Body': {'stkCallback': cb}}


def c2b_body(receipt, account, amount=1000):
    return {'TransactionType': 'Pay Bill', 'TransID': receipt, 'TransTime': '20261116101500', 'TransAmount': str(amount),
            'BusinessShortCode': '600000', 'BillRefNumber': account, 'MSISDN': '2547***678', 'FirstName': 'Jane'}


@override_settings(SAAS_ORCHESTRATOR='fake', SAAS_DATA_DIR=DATA, SAAS_TENANT_ENV_DIR=DATA / 'tenants',
                   CELERY_TASK_ALWAYS_EAGER=True)
class Base(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # sign-up throttle counts
        FakeOrchestrator.calls = []
        self.plan = make_plan()
        cfg = PlatformSettings.load()
        cfg.public_base_url = 'https://cloud.example.com'
        cfg.mpesa_shortcode, cfg.mpesa_passkey = '600000', 'pk'
        cfg.mpesa_consumer_key, cfg.mpesa_consumer_secret = 'platform-key', 'platform-secret'
        cfg.tenant_consumer_key, cfg.tenant_consumer_secret = 'tenant-key', 'tenant-secret'
        cfg.settlement_requires_approval = False
        cfg.save()
        self.admin = User.objects.create_user(username='a@p.com', email='a@p.com', password='x', role='platform_admin')
        self.client = APIClient()
        self.forwarded = []
        p = patch('cloud.billing.collections.requests.post', side_effect=self._forward)
        p.start()
        self.addCleanup(p.stop)

    def _forward(self, url, json=None, **kw):
        self.forwarded.append((url, json))
        return MagicMock(status_code=200, text='')

    def signup(self, name='Acme Wireless', email='owner@acme.co.ke', **extra):
        client = APIClient()
        with self.captureOnCommitCallbacks(execute=True):
            res = client.post('/api/public/signup/', {
                'company_name': name, 'full_name': 'Jane Owner', 'email': email, 'phone': '0712345678',
                'password': 'Str0ng-pass-123', 'accept_terms': True, **extra}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return Tenant.objects.get(slug=res.data['tenant']['slug']), res

    def live_tenant(self, **kw):
        t, _ = self.signup(**kw)
        t.refresh_from_db()
        return t


class PricingTests(TestCase):
    def test_graduated_with_included_and_minimum(self):
        plan = make_plan(minimum_charge=Decimal('1000'))
        q = plan.quote(150)  # 130 billable: 100 @30 + 30 @10
        self.assertEqual(q['billable'], 130)
        self.assertEqual(Decimal(q['amount']), Decimal('500') + 3000 + 300)
        self.assertEqual(Decimal(plan.quote(10)['amount']), Decimal('1000'))  # base 500 -> minimum 1000

    def test_volume_and_cap(self):
        plan = make_plan(code='vol', is_default=False, tier_mode='volume', base_fee=0, included_subscribers=0,
                         maximum_charge=Decimal('2500'))
        self.assertEqual(Decimal(plan.quote(50)['amount']), Decimal('1500'))   # all 50 @30
        self.assertEqual(Decimal(plan.quote(150)['amount']), Decimal('1500'))  # all 150 @10
        self.assertEqual(Decimal(plan.quote(400)['amount']), Decimal('2500'))  # capped

    def test_quote_api_previews_unsaved_plan(self):
        res = APIClient().post('/api/public/quote/', {'count': 120, 'plan': {
            'tier_mode': 'graduated', 'base_fee': '0', 'included_subscribers': 0, 'service_types': 'pppoe',
            'tiers': [{'up_to': 100, 'unit_price': '20'}, {'up_to': None, 'unit_price': '5'}]}}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data['amount']), Decimal('2100'))


class SignupAndLifecycleTests(Base):
    def test_signup_provisions_a_trial_instance(self):
        t, res = self.signup()
        t.refresh_from_db()
        self.assertEqual(t.slug, 'acmewireless')
        self.assertEqual(t.status, 'trial')
        self.assertTrue(res.data['access'])
        self.assertAlmostEqual((t.trial_ends_at - timezone.now()).total_seconds(), 2 * 86400, delta=60)
        self.assertEqual(t.pending_admin_password, '')  # wiped once the instance admin exists
        self.assertEqual([c[0] for c in FakeOrchestrator.calls], ['up', 'wait_ready', 'migrate', 'create_admin'])
        env = t.env_path.read_text()
        self.assertIn('MPESA_CONSUMER_KEY=tenant-key', env)
        self.assertNotIn('platform-secret', env)  # the platform's Daraja app never goes to an instance
        self.assertIn(f'MPESA_CALLBACK_URL=https://cloud.example.com/api/mpesa/stk/{t.callback_token}/', env)
        self.assertIn(f'redis://saas-redis:6379/{t.redis_db}', env)
        self.assertTrue(any('ready' in m.subject for m in mail.outbox))

    def test_signup_validation(self):
        self.signup()
        res = APIClient().post('/api/public/signup/', {
            'company_name': 'Acme Wireless', 'full_name': 'X', 'email': 'OWNER@acme.co.ke', 'phone': '0712',
            'password': 'short', 'accept_terms': False, 'slug': 'admin'}, format='json')
        self.assertEqual(res.status_code, 400)
        for field in ('email', 'phone', 'accept_terms', 'slug'):
            self.assertIn(field, res.data)
        self.assertEqual(APIClient().get('/api/public/slug/', {'name': 'Acme Wireless'}).data['slug'], 'acmewireless2')

    def test_trial_end_suspends_unless_activated(self):
        a = self.live_tenant()
        b = self.live_tenant(name='Beta Net', email='b@beta.co.ke')
        owner = User.objects.get(email='b@beta.co.ke')
        c = APIClient()
        c.force_authenticate(owner)
        res = c.post('/api/portal/activate/', {'plan': 'standard', 'accept_terms': True,
                                               'settlement_method': 'paybill', 'settlement_account': '400200',
                                               'settlement_account_ref': 'BETA'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        from cloud.tenants.services import run_lifecycle
        later = timezone.now() + timedelta(days=3)
        with patch('cloud.tenants.services.timezone.now', return_value=later):
            run_lifecycle(now=later)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.status, 'suspended')
        self.assertIn('stop', [c[0] for c in FakeOrchestrator.calls])
        self.assertEqual(b.status, 'active')
        # Subscribing after the trial ended brings the instance back.
        owner_a = User.objects.get(email='owner@acme.co.ke')
        c.force_authenticate(owner_a)
        with self.captureOnCommitCallbacks(execute=True):
            res = c.post('/api/portal/activate/', {'accept_terms': True}, format='json')
        a.refresh_from_db()
        self.assertEqual(a.status, 'active')
        self.assertEqual(FakeOrchestrator.calls[-1][0], 'start')

    def test_owner_cannot_reach_admin_and_staff_cannot_change_settings(self):
        t = self.live_tenant()
        c = APIClient()
        c.force_authenticate(User.objects.get(email='owner@acme.co.ke'))
        self.assertEqual(c.get('/api/admin/tenants/').status_code, 403)
        self.assertEqual(c.get('/api/portal/tenant/').data['slug'], t.slug)
        self.assertNotIn('notes', c.get('/api/portal/tenant/').data)
        support = User.objects.create_user(username='s@p.com', email='s@p.com', password='x', role='platform_staff')
        c.force_authenticate(support)
        self.assertEqual(c.get('/api/admin/settings/').status_code, 200)
        self.assertEqual(c.patch('/api/admin/settings/', {'trial_days': 9}, format='json').status_code, 403)
        self.assertEqual(c.post(f'/api/admin/tenants/{t.pk}/action/', {'action': 'suspend'}, format='json').status_code, 403)

    def test_settings_secrets_are_write_only(self):
        c = APIClient()
        c.force_authenticate(self.admin)
        res = c.patch('/api/admin/settings/', {'initiator_password': 'secret!', 'mpesa_passkey': ''}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertNotIn('initiator_password', res.data)
        self.assertTrue(res.data['initiator_password_set'])
        self.assertEqual(PlatformSettings.load().mpesa_passkey, 'pk')  # blank kept it

    def test_admin_destroy_requires_confirmation_and_zero_balance(self):
        t = self.live_tenant()
        c = APIClient()
        c.force_authenticate(self.admin)
        self.assertEqual(c.post(f'/api/admin/tenants/{t.pk}/action/', {'action': 'destroy'}, format='json').status_code, 400)
        from cloud.billing.ledger import post
        post(t, 'adjustment', 100, 'adj-1', 'test')
        with self.captureOnCommitCallbacks(execute=True):
            c.post(f'/api/admin/tenants/{t.pk}/action/', {'action': 'destroy', 'confirm': t.slug}, format='json')
        t.refresh_from_db()
        self.assertNotEqual(t.status, 'deleted')  # money still held
        self.assertIn('money held', t.events.first().message)


class CollectionTests(Base):
    def test_stk_callback_verified_credited_and_forwarded(self):
        t = self.live_tenant()
        with patch('cloud.billing.daraja.Daraja.stk_query', return_value=('paid', 'ok')), \
             self.captureOnCommitCallbacks(execute=True):
            res = APIClient().post(f'/api/mpesa/stk/{t.callback_token}/', stk_body(), format='json')
        self.assertEqual(res.data['ResultCode'], 0)
        c = Collection.objects.get(receipt='QK1234ABCD')
        self.assertTrue(c.verified and c.forwarded)
        self.assertEqual(balance(t), Decimal('500'))
        self.assertEqual(self.forwarded[0][0], f'http://t-{t.slug}-backend:8000/api/payments/callback/')
        self.assertEqual(self.forwarded[0][1], stk_body())  # untouched
        # Safaricom retrying the same callback changes nothing.
        with self.captureOnCommitCallbacks(execute=True):
            APIClient().post(f'/api/mpesa/stk/{t.callback_token}/', stk_body(), format='json')
        self.assertEqual(balance(t), Decimal('500'))

    def test_forged_stk_callback_is_not_credited(self):
        t = self.live_tenant()
        with patch('cloud.billing.daraja.Daraja.stk_query', return_value=('failed', 'No such transaction')), \
             self.captureOnCommitCallbacks(execute=True):
            APIClient().post(f'/api/mpesa/stk/{t.callback_token}/', stk_body(receipt='FAKE00001'), format='json')
        self.assertFalse(Collection.objects.get(receipt='FAKE00001').verified)
        self.assertEqual(balance(t), 0)
        self.assertEqual(self.forwarded, [])  # never reaches the instance: no free service
        self.assertEqual(APIClient().post('/api/mpesa/stk/wrong-token/', stk_body(), format='json').status_code, 404)

    def test_failed_stk_is_forwarded_but_not_recorded(self):
        t = self.live_tenant()
        with self.captureOnCommitCallbacks(execute=True):
            APIClient().post(f'/api/mpesa/stk/{t.callback_token}/', stk_body(code=1032), format='json')
        self.assertFalse(Collection.objects.exists())
        self.assertEqual(len(self.forwarded), 1)

    def test_c2b_routing_prefix_username_and_unallocated(self):
        a = self.live_tenant()
        b = self.live_tenant(name='Beta Net', email='b@beta.co.ke')
        a.metrics = {'fake_accounts': ['john', 'shared']}
        a.save()
        b.metrics = {'fake_accounts': ['mary', 'shared']}
        b.save()
        cfg = PlatformSettings.load()
        url = f'/api/mpesa/c2b/{cfg.c2b_secret}/confirmation/'
        with self.captureOnCommitCallbacks(execute=True):
            APIClient().post(url, c2b_body('R1', 'mary'), format='json')
            APIClient().post(url, c2b_body('R2', f'{a.account_prefix} shared'), format='json')
            APIClient().post(url, c2b_body('R3', 'shared'), format='json')
            APIClient().post(url, c2b_body('R4', 'nobody'), format='json')
        got = {c.receipt: (c.tenant_id, c.routed_by) for c in Collection.objects.all()}
        self.assertEqual(got['R1'], (b.pk, 'username'))
        self.assertEqual(got['R2'], (a.pk, 'prefix'))
        self.assertEqual(got['R3'], (None, ''))  # two ISPs have "shared"
        self.assertEqual(got['R4'], (None, ''))
        fwd = {u: body['BillRefNumber'] for u, body in self.forwarded}
        self.assertEqual(fwd[f'http://t-{a.slug}-backend:8000/api/payments/c2b/{a.c2b_secret}/confirmation/'], 'shared')
        self.assertEqual(APIClient().post('/api/mpesa/c2b/nope/confirmation/', c2b_body('R5', 'x'), format='json').status_code, 404)
        # An admin allocates the ambiguous one.
        c = APIClient()
        c.force_authenticate(self.admin)
        r3 = Collection.objects.get(receipt='R3')
        with self.captureOnCommitCallbacks(execute=True):
            res = c.post(f'/api/admin/collections/{r3.pk}/action/', {'action': 'allocate', 'tenant': b.pk}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(balance(b), Decimal('2000'))

    def test_collection_fee(self):
        cfg = PlatformSettings.load()
        cfg.collection_fee_percent = Decimal('2.5')
        cfg.save()
        t = self.live_tenant()
        t.metrics = {'fake_accounts': ['john']}
        t.save()
        with self.captureOnCommitCallbacks(execute=True):
            APIClient().post(f'/api/mpesa/c2b/{cfg.c2b_secret}/confirmation/', c2b_body('R9', 'john', 1000), format='json')
        self.assertEqual(balance(t), Decimal('975.00'))


class InvoiceAndSettlementTests(Base):
    def active_tenant(self):
        t = self.live_tenant()
        t.status, t.activated_at = 'active', timezone.now() - timedelta(days=90)
        t.settlement_method, t.settlement_account, t.settlement_account_ref = 'paybill', '400200', 'ACME'
        t.save()
        return t

    def snapshot(self, t, day, pppoe, hotspot=0):
        UsageSnapshot.objects.create(tenant=t, date=day, peak={'active': {'pppoe': pppoe, 'hotspot': hotspot}},
                                     latest={'active': {'pppoe': pppoe, 'hotspot': hotspot}})

    def test_invoice_uses_peak_counted_types_and_auto_deducts(self):
        from cloud.billing.invoicing import issue
        from cloud.billing.ledger import post
        t = self.active_tenant()
        start, end = date(2026, 10, 1), date(2026, 10, 31)
        self.snapshot(t, date(2026, 10, 5), 100, hotspot=900)  # hotspot not counted by this plan
        self.snapshot(t, date(2026, 10, 20), 140)
        post(t, 'collection', 10000, 'X1', 'payments')
        inv, created = issue(t, start, end)
        self.assertTrue(created)
        self.assertEqual(inv.subscriber_count, 140)
        self.assertEqual(inv.amount, Decimal('500') + 100 * 30 + 20 * 10)  # 120 billable
        self.assertEqual(inv.status, 'paid')
        self.assertEqual(balance(t), Decimal('10000') - inv.amount)
        self.assertFalse(issue(t, start, end)[1])  # once per period

    def test_first_period_prorated(self):
        from cloud.billing.invoicing import build
        t = self.active_tenant()
        t.activated_at = timezone.make_aware(timezone.datetime(2026, 10, 17, 12))
        t.save()
        self.snapshot(t, date(2026, 10, 20), 20)  # all included -> base fee only
        d = build(t, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(d['period_start'], date(2026, 10, 17))
        self.assertEqual(d['amount'], (Decimal('500') * 15 / 31).quantize(Decimal('0.01')))

    def test_unpaid_invoice_overdue_then_suspended_then_resumed_on_payment(self):
        from cloud.billing.invoicing import issue, mark_paid
        from cloud.tenants.services import run_lifecycle
        t = self.active_tenant()
        self.snapshot(t, date(2026, 10, 3), 50)
        inv, _ = issue(t, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(inv.status, 'open')
        run_lifecycle(now=inv.due_at + timedelta(hours=1))
        t.refresh_from_db()
        self.assertEqual(t.status, 'past_due')
        run_lifecycle(now=inv.due_at + timedelta(days=8))
        t.refresh_from_db()
        self.assertEqual(t.status, 'suspended')
        with self.captureOnCommitCallbacks(execute=True):
            mark_paid(inv, 'manual')
        t.refresh_from_db()
        self.assertEqual(t.status, 'active')

    def test_payout_success_and_failure_reversal(self):
        from cloud.billing import settlement
        from cloud.billing.ledger import post
        cfg = PlatformSettings.load()
        cfg.settlement_fee_flat = Decimal('30')
        cfg.save()
        t = self.active_tenant()
        post(t, 'collection', 5000, 'X2', 'payments')
        with patch('cloud.billing.daraja.Daraja.payout', return_value={'ConversationID': 'AG_1', 'ResponseDescription': 'ok'}) as pay, \
             self.captureOnCommitCallbacks(execute=True):
            s = settlement.create(t)
        s.refresh_from_db()
        self.assertEqual((s.status, s.amount, s.fee), ('processing', Decimal('4970'), Decimal('30')))
        self.assertEqual(pay.call_args.kwargs['method'], 'paybill')
        self.assertEqual(balance(t), 0)
        APIClient().post('/api/mpesa/payout/result/', {'Result': {
            'ResultType': 0, 'ResultCode': 0, 'ResultDesc': 'done', 'OriginatorConversationID': s.originator_id,
            'ConversationID': 'AG_1', 'TransactionID': 'RKT1'}}, format='json')
        s.refresh_from_db()
        self.assertEqual((s.status, s.mpesa_receipt), ('succeeded', 'RKT1'))
        # A failed payout gives the money back.
        post(t, 'collection', 1000, 'X3', 'payments')
        with patch('cloud.billing.daraja.Daraja.payout', return_value={'ConversationID': 'AG_2'}), \
             self.captureOnCommitCallbacks(execute=True):
            s2 = settlement.create(t)
        APIClient().post('/api/mpesa/payout/result/', {'Result': {
            'ResultCode': 2001, 'ResultDesc': 'The initiator information is invalid.',
            'OriginatorConversationID': s2.originator_id}}, format='json')
        s2.refresh_from_db()
        self.assertEqual(s2.status, 'failed')
        self.assertEqual(balance(t), Decimal('1000'))

    def test_payout_needs_details_approval_by_someone_else(self):
        from cloud.billing import settlement
        from cloud.billing.ledger import post
        cfg = PlatformSettings.load()
        cfg.settlement_requires_approval = True
        cfg.save()
        t = self.active_tenant()
        post(t, 'collection', 2000, 'X4', 'payments')
        s = settlement.create(t, actor=self.admin)
        self.assertEqual(s.status, 'pending_approval')
        with self.assertRaises(settlement.SettlementError):
            settlement.approve(s, self.admin)  # same person
        other = User.objects.create_user(username='o@p.com', email='o@p.com', password='x', role='platform_admin')
        with patch('cloud.billing.daraja.Daraja.payout', return_value={'ConversationID': 'AG_3'}), \
             self.captureOnCommitCallbacks(execute=True):
            settlement.approve(s, other)
        s.refresh_from_db()
        self.assertEqual(s.status, 'processing')
        t.settlement_method = ''
        t.save()
        with self.assertRaises(settlement.SettlementError):
            settlement.create(t)

    def test_open_invoice_reserved_before_payout(self):
        from cloud.billing.invoicing import issue
        from cloud.billing.ledger import post
        from cloud.billing.settlement import available
        cfg = PlatformSettings.load()
        cfg.auto_deduct_invoices = False
        cfg.save()
        t = self.active_tenant()
        self.snapshot(t, date(2026, 10, 3), 50)
        inv, _ = issue(t, date(2026, 10, 1), date(2026, 10, 31))
        post(t, 'collection', 3000, 'X5', 'payments')
        self.assertEqual(available(t), Decimal('3000') - inv.amount)


class SecurityCredentialTests(TestCase):
    def test_encrypts_with_certificate(self):
        import base64
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        from cryptography.x509.oid import NameOID
        from cloud.billing.daraja import security_credential
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'test')])
        now = timezone.now()
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                .sign(key, hashes.SHA256()))
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        token = security_credential(pem, 'Safaricom999!*!')
        self.assertEqual(key.decrypt(base64.b64decode(token), padding.PKCS1v15()), b'Safaricom999!*!')
