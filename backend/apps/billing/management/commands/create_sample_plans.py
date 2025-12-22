"""
Django management command to create sample billing plans
"""
from django.core.management.base import BaseCommand
from apps.billing.models import BillingPlan
from apps.network.models import Router


class Command(BaseCommand):
    help = 'Create sample billing plans for testing'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Creating sample billing plans...'))
        
        # Create sample PPPoE plans
        pppoe_plans = [
            {
                'name': 'Bronze 5Mbps',
                'description': 'Perfect for browsing and social media',
                'service_type': 'pppoe',
                'download_speed': 5,
                'upload_speed': 5,
                'price': 1500,
                'duration_days': 30,
                'data_limit_gb': None,  # Unlimited
                'mikrotik_profile': 'bronze-5mbps',
            },
            {
                'name': 'Silver 10Mbps',
                'description': 'Great for streaming and video calls',
                'service_type': 'pppoe',
                'download_speed': 10,
                'upload_speed': 10,
                'price': 2500,
                'duration_days': 30,
                'data_limit_gb': None,
                'mikrotik_profile': 'silver-10mbps',
            },
            {
                'name': 'Gold 20Mbps',
                'description': 'Premium speed for heavy users',
                'service_type': 'pppoe',
                'download_speed': 20,
                'upload_speed': 20,
                'price': 4000,
                'duration_days': 30,
                'data_limit_gb': None,
                'mikrotik_profile': 'gold-20mbps',
            },
            {
                'name': 'Platinum 50Mbps',
                'description': 'Ultimate speed for businesses',
                'service_type': 'pppoe',
                'download_speed': 50,
                'upload_speed': 50,
                'price': 8000,
                'duration_days': 30,
                'data_limit_gb': None,
                'mikrotik_profile': 'platinum-50mbps',
            },
        ]
        
        # Create sample Hotspot plans
        hotspot_plans = [
            {
                'name': 'Hotspot Daily',
                'description': '24-hour unlimited access',
                'service_type': 'hotspot',
                'download_speed': 5,
                'upload_speed': 5,
                'price': 100,
                'duration_days': 1,
                'data_limit_gb': None,
                'mikrotik_profile': 'hotspot-daily',
            },
            {
                'name': 'Hotspot Weekly',
                'description': '7-day unlimited access',
                'service_type': 'hotspot',
                'download_speed': 10,
                'upload_speed': 10,
                'price': 500,
                'duration_days': 7,
                'data_limit_gb': None,
                'mikrotik_profile': 'hotspot-weekly',
            },
            {
                'name': 'Hotspot Monthly',
                'description': '30-day unlimited access',
                'service_type': 'hotspot',
                'download_speed': 10,
                'upload_speed': 10,
                'price': 1500,
                'duration_days': 30,
                'data_limit_gb': None,
                'mikrotik_profile': 'hotspot-monthly',
            },
        ]
        
        all_plans = pppoe_plans + hotspot_plans
        created_count = 0
        
        for plan_data in all_plans:
            plan, created = BillingPlan.objects.get_or_create(
                name=plan_data['name'],
                defaults=plan_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created: {plan.name} - KES {plan.price}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'- Already exists: {plan.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Created {created_count} new billing plans')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Total plans in database: {BillingPlan.objects.count()}')
        )
        
        # Create sample router if none exists
        if not Router.objects.exists():
            self.stdout.write(self.style.WARNING('\n⚠️  No routers found. Creating sample router...'))
            router = Router.objects.create(
                name='Main Router',
                ip_address='192.168.88.1',
                username='admin',
                password='',  # Set this in Django admin
                port=8728,
                use_ssl=False,
                is_active=True,
                location='Main Office'
            )
            self.stdout.write(
                self.style.SUCCESS(f'✓ Created router: {router.name}')
            )
            self.stdout.write(
                self.style.WARNING('⚠️  Please update router password in Django admin!')
            )
