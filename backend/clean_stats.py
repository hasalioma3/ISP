import os
import django
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isp_billing.settings')
django.setup()

from apps.network.models import RouterInterfaceStat

print(f"Deleted {RouterInterfaceStat.objects.all().delete()[0]} stats.")
