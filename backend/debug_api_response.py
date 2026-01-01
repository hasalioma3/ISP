import os
import django
import sys
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS += ['testserver']

from rest_framework.test import APIClient
from apps.customers.models import Customer
username = '0726686337_0098'
customer = Customer.objects.filter(username=username).first()

if not customer:
    print(f"Customer {username} not found!")
    exit()

print(f"Resetting password for {username}...")
customer.set_password('test1234')
customer.save()

print("Logging in...")
client = APIClient()
res = client.post('/api/customers/login/', {
    'username': username,
    'password': 'test1234'
}, format='json')

if res.status_code != 200:
    print(f"Login Failed: {res.status_code} {res.data}")
    exit()

token = res.data['tokens']['access']
print("Login Success. Token received.")

print("Fetching Usage...")
client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
res_usage = client.get('/api/billing/usage/')

print(f"Status: {res_usage.status_code}")
print(f"Data: {json.dumps(res_usage.data, indent=2, default=str)}")
