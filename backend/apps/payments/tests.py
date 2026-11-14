import base64

from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.payments.models import C2BPayment
from apps.payments.services.payer_name import decode_name_part


class PayerNameTests(TestCase):
    def test_plain_and_base64_names(self):
        self.assertEqual(decode_name_part('JOHN'), 'John')
        # Real production values; 8 mixed-case letters is also valid base64.
        for raw, shown in [('HASSAN', 'Hassan'), ('Shadrack', 'Shadrack'), ('MATHEW', 'Mathew'), ('Samson', 'Samson')]:
            self.assertEqual(decode_name_part(raw), shown)
        self.assertEqual(decode_name_part("MARY-ANN O'NEIL"), "Mary-Ann O'Neil")
        self.assertEqual(decode_name_part(base64.b64encode(b'WANJIRU').decode()), 'Wanjiru')
        self.assertEqual(decode_name_part(base64.b64encode(b'Grace').decode()), 'Grace')

    def test_unknown_formats_are_kept_not_dropped(self):
        self.assertEqual(decode_name_part('J***'), 'J***')
        self.assertEqual(decode_name_part(''), '')

    def test_payments_page_shows_buy_goods_payer_name(self):
        C2BPayment.objects.create(
            transaction_id='SKC77', amount=50, msisdn='a' * 64, raw_data={},
            first_name=base64.b64encode(b'PETER').decode(), last_name='KAMAU',
        )
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        row = client.get('/api/analytics/recent-payments/').data['results'][0]
        self.assertEqual(row['payer_name'], 'Peter Kamau')
        self.assertFalse(row['matched'])


class FalseActivationErrorTests(TestCase):
    """A payment that activated must not show "Activation failed"."""

    def setUp(self):
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from apps.billing.models import BillingPlan, Subscription, Transaction
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        self.customer = Customer.objects.create(username='virginia', service_type='hotspot')
        self.plan = BillingPlan.objects.create(name='Daily 1GB', service_type='hotspot', download_speed=5,
                                               upload_speed=5, price='20.00', mikrotik_profile='d1')
        sub = Subscription.objects.create(customer=self.customer, plan=self.plan, expiry_date=timezone.now() + timedelta(days=1))
        Transaction.objects.create(customer=self.customer, subscription=sub, transaction_id='UKDF72JA5U',
                                   amount=20, payment_method='mpesa', status='completed', mpesa_receipt_number='UKDF72JA5U')
        # Stale row: stamped 'error' and never linked.
        C2BPayment.objects.create(transaction_id='UKDF72JA5U', amount=20, msisdn='h' * 64, raw_data={},
                                  first_name='VIRGINIA', matched_customer=self.customer, status='error')

    def test_payments_page_reads_the_transaction(self):
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        row = client.get('/api/analytics/recent-payments/').data['results'][0]
        self.assertEqual(row['used_for'], 'Daily 1GB')
        self.assertEqual(row['status'], 'utilized')


class FalseActivationErrorCommitTests(TransactionTestCase):
    """Real commits (TransactionTestCase), so post-commit hooks actually run."""

    def setUp(self):
        from unittest.mock import patch
        from apps.billing.models import BillingPlan
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        Customer.objects.create(username='virginia', service_type='pppoe')
        BillingPlan.objects.create(name='Home 20', service_type='pppoe', download_speed=5,
                                   upload_speed=5, price='20.00', mikrotik_profile='d1')

    def test_sms_queue_failure_does_not_mark_activation_failed(self):
        from unittest.mock import patch
        from apps.payments.services.payment_processor import payment_processor
        data = {
            'TransID': 'UKNEW00001', 'TransAmount': '20.00', 'MSISDN': '254700000001', 'BillRefNumber': 'virginia',
            'TransTime': '20261113111600', 'BusinessShortCode': '4993011', 'FirstName': 'VIRGINIA',
        }
        with patch('apps.payments.services.payment_processor.send_payment_confirmation_sms.delay',
                   side_effect=ConnectionError('broker down')):
            payment_processor.process_c2b_confirmation(data)
        payment = C2BPayment.objects.get(transaction_id='UKNEW00001')
        self.assertEqual(payment.status, 'activated')
        self.assertIsNotNone(payment.subscription_id)


class StkAndTillDoubleCallbackTests(TestCase):
    """A portal STK payment to a Buy Goods till sends an STK callback AND a C2B confirmation."""

    def setUp(self):
        from unittest.mock import patch
        from apps.billing.models import BillingPlan
        from apps.payments.models import PaymentRequest
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer',
                       'apps.payments.services.payment_processor.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        # Two hotspot device accounts on one phone -- the C2B side can't tell them apart.
        self.phone = '0720001333'
        Customer.objects.create(username='0720001333_AAAA', phone_number=self.phone, service_type='hotspot')
        self.buyer = Customer.objects.create(username='0720001333_ED57', phone_number=self.phone, service_type='hotspot')
        self.plan = BillingPlan.objects.create(name='Unlimited 1 hour', service_type='hotspot', download_speed=5,
                                               upload_speed=5, price='20.00', mikrotik_profile='h1')
        self.request = PaymentRequest.objects.create(
            customer=self.buyer, plan=self.plan, phone_number='254720001333', amount=20,
            account_reference=self.buyer.username, transaction_desc='x', status='pending',
        )
        self.request = PaymentRequest.objects.select_related('plan', 'customer').get(pk=self.request.pk)

    def stk_callback(self, code):
        from apps.payments.models import PaymentCallback
        from apps.payments.services.payment_processor import payment_processor
        callback = PaymentCallback.objects.create(
            payment_request=self.request, merchant_request_id='m', checkout_request_id='c', result_code='0',
            result_desc='ok', mpesa_receipt_number=code, phone_number='254720001333', amount=20, raw_data={},
        )
        payment_processor._process_successful_payment(self.request, callback)

    def c2b(self, code):
        from apps.payments.services.payment_processor import payment_processor
        from apps.payments.services.phone_hash import hash_phone
        payment_processor.process_c2b_confirmation({
            'TransID': code, 'TransAmount': '20.00', 'MSISDN': hash_phone(self.phone),
            'TransTime': '20261113111600', 'BusinessShortCode': '4993011', 'FirstName': 'ALEX',
        })
        return C2BPayment.objects.get(transaction_id=code)

    def test_stk_first_then_till_confirmation_links_without_duplicate(self):
        from apps.billing.models import Subscription, Transaction
        self.stk_callback('UKDQP1VZDA')
        payment = self.c2b('UKDQP1VZDA')
        self.assertEqual(payment.status, 'activated')
        self.assertEqual(payment.matched_customer, self.buyer)
        self.assertEqual(Transaction.objects.filter(transaction_id='UKDQP1VZDA').count(), 1)
        self.assertEqual(Subscription.objects.filter(customer__phone_number=self.phone).count(), 1)

    def test_till_first_waits_for_stk_which_activates_the_right_device(self):
        from apps.billing.models import Subscription
        payment = self.c2b('UKDQP1VZDB')
        self.assertEqual(payment.status, 'awaiting_stk')
        self.assertFalse(Subscription.objects.exists())  # nothing activated by guesswork
        self.stk_callback('UKDQP1VZDB')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'activated')
        self.assertEqual(Subscription.objects.get().customer, self.buyer)

    def test_awaiting_payment_left_for_admin_when_stk_times_out(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.payments.models import PaymentRequest
        from apps.payments.tasks import cleanup_pending_payments
        payment = self.c2b('UKDQP1VZDC')
        PaymentRequest.objects.filter(pk=self.request.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        cleanup_pending_payments()
        payment.refresh_from_db()
        # Hotspot buyer: held for an admin, with the exact device account as the hint.
        self.assertEqual(payment.status, 'review')
        self.assertEqual(payment.matched_customer, self.buyer)
        self.assertIsNone(payment.subscription)


class AssignOpenPaymentTests(TestCase):
    def setUp(self):
        from unittest.mock import patch
        from apps.billing.models import BillingPlan
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        self.client = APIClient()
        self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        self.alice = Customer.objects.create(username='alice', service_type='hotspot')
        self.bob = Customer.objects.create(username='bob', service_type='hotspot')
        self.plan = BillingPlan.objects.create(name='Unlimited 1 hour', service_type='hotspot', download_speed=5,
                                               upload_speed=5, price='20.00', mikrotik_profile='h1')
        self.big = BillingPlan.objects.create(name='Weekly', service_type='hotspot', download_speed=5,
                                              upload_speed=5, price='300.00', mikrotik_profile='w1')

    def payment(self, code='TILL1', **kw):
        return C2BPayment.objects.create(transaction_id=code, amount=20, msisdn='h' * 64, raw_data={}, **kw)

    def assign(self, payment, customer, plan=None):
        return self.client.post(f'/api/payments/c2b/{payment.id}/assign/',
                                {'customer_id': customer.id, 'plan_id': plan.id if plan else None}, format='json')

    def test_unmatched_payment_activates_chosen_plan(self):
        from apps.billing.models import Subscription
        p = self.payment()
        res = self.assign(p, self.alice, self.plan)
        self.assertEqual(res.status_code, 200, res.data)
        p.refresh_from_db()
        self.assertEqual(p.status, 'activated')
        self.assertEqual(Subscription.objects.get().customer, self.alice)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.account_balance, 0)

    def test_keep_as_balance(self):
        p = self.payment()
        self.assertEqual(self.assign(p, self.alice).status_code, 200)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.account_balance, 20)
        row = self.client.get('/api/analytics/recent-payments/').data['results'][0]
        self.assertEqual(row['status'], 'assigned')

    def test_status_after_assigning_with_plan_is_used(self):
        p = self.payment()
        self.assign(p, self.alice, self.plan)
        row = self.client.get('/api/analytics/recent-payments/').data['results'][0]
        self.assertEqual(row['status'], 'utilized')

    def test_move_from_wrong_subscriber_balance(self):
        p = self.payment()
        self.assign(p, self.alice)
        res = self.assign(p, self.bob, self.plan)
        self.assertEqual(res.status_code, 200, res.data)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.account_balance, 0)
        p.refresh_from_db()
        self.assertEqual((p.matched_customer, p.status), (self.bob, 'activated'))

    def test_refuses_to_move_money_already_spent(self):
        p = self.payment()
        self.assign(p, self.alice)
        Customer.objects.filter(pk=self.alice.pk).update(account_balance=5)
        res = self.assign(p, self.bob)
        self.assertEqual(res.status_code, 400)
        self.assertIn('already spent', res.data['error'])

    def test_plan_too_expensive_changes_nothing(self):
        from apps.billing.models import Transaction
        p = self.payment()
        res = self.assign(p, self.alice, self.big)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Transaction.objects.exists())
        p.refresh_from_db()
        self.assertEqual(p.status, 'unmatched')

    def test_activated_payment_cannot_be_reassigned(self):
        p = self.payment()
        self.assign(p, self.alice, self.plan)
        self.assertEqual(self.assign(p, self.bob).status_code, 400)



class TillAutoMatchRulesTests(TestCase):
    """Till payments only auto-activate PPPoE plans; hotspot payers wait for an admin."""

    def setUp(self):
        from unittest.mock import patch
        from apps.billing.models import BillingPlan
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        BillingPlan.objects.create(name='Hotspot 5', service_type='hotspot', download_speed=2, upload_speed=2,
                                   price='5.00', mikrotik_profile='h5')
        BillingPlan.objects.create(name='Home 10', service_type='pppoe', download_speed=10, upload_speed=10,
                                   price='1500.00', mikrotik_profile='p10')

    def pay(self, customer, amount, code):
        from apps.payments.services.payment_processor import payment_processor
        from apps.payments.services.phone_hash import hash_phone
        payment_processor.process_c2b_confirmation({
            'TransID': code, 'TransAmount': amount, 'MSISDN': hash_phone(customer.phone_number),
            'TransTime': '20261113111600', 'BusinessShortCode': '4993011',
        })
        customer.refresh_from_db()
        return C2BPayment.objects.get(transaction_id=code)

    def test_hotspot_payer_is_left_for_admin(self):
        from apps.billing.models import Subscription, Transaction
        guest = Customer.objects.create(username='0711000000_AAAA', phone_number='0711000000', service_type='hotspot')
        payment = self.pay(guest, '5.00', 'TILLH1')
        self.assertEqual(payment.status, 'review')
        self.assertEqual(payment.matched_customer, guest)  # a hint for the admin
        self.assertFalse(Subscription.objects.exists())
        self.assertFalse(Transaction.objects.exists())
        self.assertEqual(guest.account_balance, 0)

    def test_pppoe_payer_never_lands_on_a_hotspot_plan(self):
        from apps.billing.models import Subscription
        home = Customer.objects.create(username='grace', phone_number='0722000001', service_type='pppoe')
        payment = self.pay(home, '5.00', 'TILLP1')
        self.assertEqual(payment.status, 'matched_no_plan')
        self.assertFalse(Subscription.objects.exists())
        self.assertEqual(home.account_balance, 5)

    def test_pppoe_exact_price_still_activates(self):
        home = Customer.objects.create(username='peter', phone_number='0722000002', service_type='pppoe')
        payment = self.pay(home, '1500.00', 'TILLP2')
        self.assertEqual(payment.status, 'activated')
        self.assertEqual(payment.subscription.plan.name, 'Home 10')

    def test_needs_assignment_shows_on_payments_page(self):
        guest = Customer.objects.create(username='0711000009_BBBB', phone_number='0711000009', service_type='hotspot')
        self.pay(guest, '5.00', 'TILLH2')
        client = APIClient()
        client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        data = client.get('/api/analytics/recent-payments/').data
        row = data['results'][0]
        self.assertTrue(row['needs_assignment'])
        self.assertIsNone(row['used_for'])
        self.assertEqual(data['unassigned'], 1)


class AssignOfferMatchesEndpointTests(TestCase):
    """The Payments list must only offer Assign where the assign endpoint accepts it."""

    def setUp(self):
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from apps.billing.models import BillingPlan, Subscription, Transaction
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',
                       'apps.billing.signals.network_automation.activate_customer'):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        self.client = APIClient()
        self.client.force_authenticate(Customer.objects.create(username='boss', is_staff=True, is_superuser=True))
        self.alice = Customer.objects.create(username='alice', service_type='pppoe')
        self.bob = Customer.objects.create(username='bob', service_type='pppoe')
        plan = BillingPlan.objects.create(name='Home 20', service_type='pppoe', download_speed=5, upload_speed=5,
                                          price='20.00', mikrotik_profile='h20')
        sub = Subscription.objects.create(customer=self.alice, plan=plan, expiry_date=timezone.now() + timedelta(days=5))

        def pay(code, **kw):
            return C2BPayment.objects.create(transaction_id=code, amount=20, msisdn='h' * 64, raw_data={}, **kw)

        # Plan recorded on the payment only (status never updated).
        pay('SUBONLY', matched_customer=self.alice, subscription=sub, status='matched_no_plan')
        # Twin transaction with a plan but not marked 'completed'.
        Transaction.objects.create(customer=self.alice, subscription=sub, transaction_id='TWINPEND', amount=20,
                                   payment_method='mpesa', status='pending')
        pay('TWINPEND', status='error')
        # Linked transaction with a plan, stale status.
        linked = Transaction.objects.create(customer=self.alice, subscription=sub, transaction_id='LINKED', amount=20,
                                            payment_method='mpesa', status='completed')
        pay('LINKED', linked_transaction=linked, status='error')
        # Genuinely assignable ones.
        pay('UNMATCHED')
        balance = Transaction.objects.create(customer=self.alice, transaction_id='INBAL', amount=20,
                                             payment_method='mpesa', status='completed')
        Customer.objects.filter(pk=self.alice.pk).update(account_balance=20)
        pay('INBAL', matched_customer=self.alice, linked_transaction=balance, status='matched_no_plan')

    def test_offer_and_endpoint_agree(self):
        rows = self.client.get('/api/analytics/recent-payments/').data['results']
        by_code = {r['transaction_id']: r for r in rows}
        for code in ('SUBONLY', 'TWINPEND', 'LINKED'):
            self.assertEqual(by_code[code]['status'], 'utilized', code)
            self.assertEqual(by_code[code]['used_for'], 'Home 20', code)
        for code in ('UNMATCHED', 'INBAL'):
            self.assertNotEqual(by_code[code]['status'], 'utilized', code)
        for row in rows:
            offered = row['status'] != 'utilized'  # the page's Assign/Reassign condition
            res = self.client.post(f"/api/payments/c2b/{row['c2b_payment_id']}/assign/",
                                   {'customer_id': self.bob.id}, format='json')
            self.assertEqual(res.status_code == 200, offered, f"{row['transaction_id']}: {res.data}")
