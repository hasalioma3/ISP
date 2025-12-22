"""
Test script for M-Pesa STK Push integration
Run this to test M-Pesa payment flow without using the frontend
"""
import os
import sys
import django

# Setup Django environment
sys.path.append('/Users/hassan/Desktop/ISP/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from apps.payments.services.mpesa_service import mpesa_service
from apps.billing.models import BillingPlan
from apps.customers.models import Customer


def test_mpesa_integration():
    """
    Test M-Pesa STK Push integration
    """
    print("=" * 60)
    print("M-PESA STK PUSH TEST")
    print("=" * 60)
    
    # Check M-Pesa configuration
    print("\n1. Checking M-Pesa Configuration...")
    from django.conf import settings
    
    config_items = {
        'Environment': settings.MPESA_ENVIRONMENT,
        'Consumer Key': settings.MPESA_CONSUMER_KEY[:10] + '...' if settings.MPESA_CONSUMER_KEY else 'NOT SET',
        'Consumer Secret': settings.MPESA_CONSUMER_SECRET[:10] + '...' if settings.MPESA_CONSUMER_SECRET else 'NOT SET',
        'Shortcode': settings.MPESA_SHORTCODE,
        'Passkey': settings.MPESA_PASSKEY[:10] + '...' if settings.MPESA_PASSKEY else 'NOT SET',
        'Callback URL': settings.MPESA_CALLBACK_URL,
    }
    
    for key, value in config_items.items():
        print(f"   {key}: {value}")
    
    # Check if credentials are set
    if not settings.MPESA_CONSUMER_KEY or not settings.MPESA_CONSUMER_SECRET:
        print("\n❌ ERROR: M-Pesa credentials not configured!")
        print("   Please update backend/.env with your M-Pesa credentials")
        return
    
    # Test OAuth token
    print("\n2. Testing OAuth Token Generation...")
    token = mpesa_service.get_access_token()
    
    if token:
        print(f"   ✅ Access token obtained: {token[:20]}...")
    else:
        print("   ❌ Failed to get access token")
        print("   Check your M-Pesa credentials")
        return
    
    # Get test data
    print("\n3. Getting Test Data...")
    
    # Get first billing plan
    plan = BillingPlan.objects.filter(is_active=True).first()
    if not plan:
        print("   ❌ No billing plans found!")
        print("   Run: python manage.py create_sample_plans")
        return
    
    print(f"   Plan: {plan.name} - KES {plan.price}")
    
    # Get or create test customer
    customer, created = Customer.objects.get_or_create(
        username='testuser',
        defaults={
            'email': 'test@example.com',
            'phone_number': '0712345678',
            'first_name': 'Test',
            'last_name': 'User',
            'service_type': 'pppoe',
        }
    )
    
    if created:
        customer.set_password('testpass123')
        customer.save()
        print(f"   ✅ Created test customer: {customer.username}")
    else:
        print(f"   ℹ️  Using existing customer: {customer.username}")
    
    # Get phone number for STK Push
    print("\n4. STK Push Test")
    print("   " + "-" * 50)
    phone = input("   Enter M-Pesa phone number (e.g., 0712345678): ").strip()
    
    if not phone:
        print("   ❌ Phone number required!")
        return
    
    # Initiate STK Push
    print(f"\n   Initiating STK Push to {phone}...")
    print(f"   Amount: KES {plan.price}")
    
    result = mpesa_service.initiate_stk_push(
        phone_number=phone,
        amount=plan.price,
        account_reference=customer.username,
        transaction_desc=f"{plan.name} subscription"
    )
    
    print("\n5. STK Push Result:")
    print("   " + "-" * 50)
    
    if result['success']:
        data = result['data']
        print("   ✅ STK Push sent successfully!")
        print(f"\n   Response Details:")
        print(f"   - Merchant Request ID: {data.get('MerchantRequestID')}")
        print(f"   - Checkout Request ID: {data.get('CheckoutRequestID')}")
        print(f"   - Response Code: {data.get('ResponseCode')}")
        print(f"   - Customer Message: {data.get('CustomerMessage')}")
        
        print(f"\n   📱 Check your phone ({phone}) for the STK Push prompt!")
        print("   💡 Enter your M-Pesa PIN to complete the payment")
        print("\n   ℹ️  The callback will be sent to:")
        print(f"   {settings.MPESA_CALLBACK_URL}")
        
        if settings.MPESA_ENVIRONMENT == 'sandbox':
            print("\n   ⚠️  SANDBOX MODE - Use test credentials")
        
    else:
        print("   ❌ STK Push failed!")
        print(f"   Error: {result.get('error')}")
        print("\n   Troubleshooting:")
        print("   1. Check your M-Pesa credentials in .env")
        print("   2. Verify your shortcode and passkey")
        print("   3. Ensure phone number is in correct format")
        print("   4. Check if you have sufficient test credits (sandbox)")
    
    print("\n" + "=" * 60)


if __name__ == '__main__':
    try:
        test_mpesa_integration()
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
