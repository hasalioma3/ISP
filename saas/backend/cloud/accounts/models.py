from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class User(AbstractUser):
    """
    Everyone who signs in to the master app: the platform's own team and the
    ISP owners. An ISP owner sees only their own tenant (the "account"
    portal); platform staff see everything. An ISP's own staff and
    subscribers never live here -- they're in that ISP's instance.
    """
    ROLES = [
        ('platform_admin', 'Platform admin'),   # everything, incl. settings, money and team
        ('platform_staff', 'Platform support'),  # tenants and support; no settings or payouts
        ('isp_owner', 'ISP owner'),
    ]
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLES, default='isp_owner')
    phone = models.CharField(max_length=20, blank=True)
    tenant = models.ForeignKey('tenants.Tenant', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='owners')

    objects = UserManager()

    @property
    def is_platform(self):
        return self.is_superuser or self.role in ('platform_admin', 'platform_staff')

    @property
    def is_platform_admin(self):
        return self.is_superuser or self.role == 'platform_admin'

    def __str__(self):
        return self.email or self.username
