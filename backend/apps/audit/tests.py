from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.customers.models import Customer


class AuditLogTests(TestCase):
    def setUp(self):
        for target in ('apps.billing.signals.sync_plan_to_routers.delay',):
            p = patch(target)
            self.addCleanup(p.stop)
            p.start()
        self.root = Customer.objects.create(username='root', is_staff=True, is_superuser=True)
        self.root.set_password('pw-root-123')
        self.root.save()
        self.admin = Customer.objects.create(username='ops', is_staff=True, role='admin')

    def test_model_changes_record_old_and_new_and_mask_secrets(self):
        from apps.billing.models import BillingPlan
        plan = BillingPlan.objects.create(name='Home', service_type='pppoe', download_speed=5, upload_speed=5,
                                          price='1000.00', mikrotik_profile='h')
        created = AuditLog.objects.get(action='create', model='billing.BillingPlan')
        self.assertEqual(created.changes['name'], 'Home')
        plan.price = '1500.00'
        plan.save()
        upd = AuditLog.objects.filter(action='update', model='billing.BillingPlan').latest('id')
        self.assertEqual(upd.changes['price'], ['1000.00', '1500.00'])
        self.admin.set_password('new-secret')
        self.admin.save()
        pw = AuditLog.objects.filter(action='update', model='customers.Customer', object_id=str(self.admin.pk)).latest('id')
        self.assertNotIn('new-secret', str(pw.changes))
        self.assertIn('password', pw.changes)
        plan_id = plan.pk
        plan.delete()
        self.assertTrue(AuditLog.objects.filter(action='delete', object_id=str(plan_id)).exists())

    def test_noop_save_is_not_logged_and_rows_are_immutable(self):
        before = AuditLog.objects.count()
        self.admin.save()
        self.assertEqual(AuditLog.objects.count(), before)
        row = AuditLog.objects.first()
        with self.assertRaises(ValueError):
            row.save()
        with self.assertRaises(ValueError):
            row.delete()

    def test_api_changes_are_attributed_and_grouped(self):
        client = APIClient()
        client.force_authenticate(self.root)
        res = client.patch('/api/notifications/settings/', {'reminder_days_before': 5, 'at_api_key': ''}, format='json')
        self.assertEqual(res.status_code, 200)
        req = AuditLog.objects.filter(action='request').latest('id')
        self.assertEqual(req.actor_username, 'root')
        self.assertEqual(req.status_code, 200)
        change = AuditLog.objects.filter(action='update', model='notifications.NotificationSettings').latest('id')
        self.assertEqual(change.actor_username, 'root')
        self.assertEqual(change.request_id, req.request_id)
        self.assertEqual(change.changes['reminder_days_before'], [3, 5])

    def test_login_success_and_failure(self):
        client = APIClient()
        client.post('/api/customers/login/', {'username': 'root', 'password': 'pw-root-123'}, format='json')
        client.post('/api/customers/login/', {'username': 'root', 'password': 'wrong'}, format='json')
        self.assertEqual(AuditLog.objects.filter(action='login', actor_username='root').count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='login_failed', actor_username='root').count(), 1)
        # Passwords never reach the log.
        self.assertFalse(AuditLog.objects.filter(changes__icontains='pw-root-123').exists())

    def test_only_superadmin_can_read(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        self.assertEqual(client.get('/api/audit/logs/').status_code, 403)
        client.force_authenticate(self.root)
        res = client.get('/api/audit/logs/', {'model': 'customers.Customer'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['count'] >= 1)
        self.assertEqual(client.get('/api/audit/logs/facets/').status_code, 200)
        self.assertEqual(client.get('/api/audit/logs/', {'export': 'csv'}).status_code, 200)

    def test_purge_respects_retention(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.audit.tasks import purge_old_audit_logs
        old = AuditLog.objects.create(action='request', object_repr='old')
        AuditLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=400))
        self.assertEqual(purge_old_audit_logs(), 1)
        self.assertTrue(AuditLog.objects.exists())
