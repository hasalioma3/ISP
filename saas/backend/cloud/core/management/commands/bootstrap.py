"""
First-run setup: a platform admin (from SAAS_ADMIN_EMAIL/SAAS_ADMIN_PASSWORD
or --email/--password) and a starter pricing plan if there are none.
Safe to run on every deploy.
"""
import os
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from cloud.core.models import PlatformSettings
from cloud.pricing.models import PricingPlan, PricingTier


class Command(BaseCommand):
    help = 'Create the first platform admin and a starter pricing plan (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--email', default=os.environ.get('SAAS_ADMIN_EMAIL', ''))
        parser.add_argument('--password', default=os.environ.get('SAAS_ADMIN_PASSWORD', ''))

    def handle(self, *args, email, password, **opts):
        PlatformSettings.load()
        User = get_user_model()
        if email and password and not User.objects.filter(email__iexact=email).exists():
            User.objects.create_superuser(username=email.lower(), email=email.lower(), password=password,
                                          role='platform_admin')
            self.stdout.write(self.style.SUCCESS(f'Created platform admin {email}'))
        if not PricingPlan.objects.exists():
            plan = PricingPlan.objects.create(
                name='Standard', code='standard', is_default=True, description='Pay for the subscribers you serve.',
                count_basis='active', service_types='pppoe,static', count_method='peak', tier_mode='graduated',
                base_fee=Decimal('500'), included_subscribers=20, minimum_charge=Decimal('500'))
            for up_to, price in ((200, '30'), (1000, '20'), (None, '12')):
                PricingTier.objects.create(plan=plan, up_to=up_to, unit_price=Decimal(price))
            self.stdout.write(self.style.SUCCESS('Created the "Standard" pricing plan (edit it under Pricing)'))
