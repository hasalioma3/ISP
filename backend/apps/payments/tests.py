import base64

from django.test import TestCase
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
