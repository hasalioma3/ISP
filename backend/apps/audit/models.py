from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    One row per change in the system: a model row created/updated/deleted
    (with the changed fields' old and new values), a sign-in or failed
    sign-in, or a staff request (POST/PUT/PATCH/DELETE) -- the last covers
    actions that change nothing in the database, like rebooting a router or
    sending messages. Rows written while handling one request share a
    request_id, so "who clicked what, and what did it change" reads as one
    group on the Logs page.

    Append-only: save() refuses to modify an existing row and delete() is
    disabled; only the retention purge (apps.audit.tasks) removes rows,
    via a queryset delete. Superadmins only (see views.py).
    """
    ACTIONS = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('login', 'Signed in'),
        ('login_failed', 'Failed sign-in'),
        ('request', 'Action'),
    ]
    SOURCES = [
        ('web', 'Web / API'),
        ('admin', 'Django admin'),
        ('task', 'Background task'),
        ('system', 'System'),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='+', db_constraint=False)
    # Kept as text so the log still says who it was after the account is gone.
    actor_username = models.CharField(max_length=150, blank=True)
    actor_role = models.CharField(max_length=30, blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default='system')
    action = models.CharField(max_length=15, choices=ACTIONS, db_index=True)
    model = models.CharField(max_length=100, blank=True, db_index=True)  # 'billing.Subscription'
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    # create: {field: value}; update: {field: [old, new]}; delete: last values;
    # request: {'body': {...}} with secrets masked.
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, blank=True)
    path = models.CharField(max_length=255, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    request_id = models.CharField(max_length=32, blank=True, db_index=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['model', 'object_id']),
            models.Index(fields=['actor_username', 'created_at']),
        ]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.actor_username or "system"} {self.action} {self.model} {self.object_repr}'

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError('Audit log entries cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Audit log entries cannot be deleted.')
