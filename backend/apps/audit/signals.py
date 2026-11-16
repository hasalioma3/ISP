"""
Write an AuditLog row for every model change, sign-in and failed sign-in.

Model changes come from Django's pre_save/post_save/post_delete and
m2m_changed for every model, minus EXCLUDED_MODELS (the log itself and
high-volume telemetry like usage counters, sessions and the notification
log, which would bury real changes and wear the Pi's SD card). Saves that
only touch IGNORED_FIELDS (heartbeats, timestamps, last_login) are skipped
for the same reason.

pre_save reads the row's current values with one query so post_save can
record [old, new] for each changed field. Secret fields are recorded as
changed but never with their value. Nothing here may break the save it's
logging: every hook swallows (and logs) its own errors.

Not covered by Django signals, so not in the log: QuerySet.update() and
bulk_create() -- the app uses those for telemetry counters and voucher
codes, and the request row of the action that ran them still records who
did it.
"""
import logging

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.audit import context
from apps.audit.utils import MASK, is_sensitive, json_value

logger = logging.getLogger('audit')

EXCLUDED_MODELS = {
    'audit.auditlog',
    'admin.logentry',
    'sessions.session',
    'contenttypes.contenttype',
    'auth.permission',
    'token_blacklist.outstandingtoken',
    'token_blacklist.blacklistedtoken',
    'django_celery_beat.periodictasks',
    'django_celery_beat.periodictask',
    'django_celery_beat.crontabschedule',
    'django_celery_beat.intervalschedule',
    'django_celery_beat.solarschedule',
    'django_celery_beat.clockedschedule',
    'django_celery_results.taskresult',
    'django_celery_results.groupresult',
    'django_celery_results.chordcounter',
    'billing.usagerecord',
    'network.activesession',
    'network.staticqueuecounter',
    'notifications.notificationlog',
    'customers.loginactivity',
    'payments.paymentcallback',
}
IGNORED_FIELDS = {
    'last_login', 'updated_at', 'modified_at', 'last_modified',
    'is_online', 'status_checked_at', 'last_seen_at', 'last_error', 'last_health',
    'last_sync', 'last_user_sync', 'last_run_at', 'total_run_count',
}


def _label(sender):
    return sender._meta.label_lower


def _tracked(sender):
    # Historical models (data migrations) live in the '__fake__' module; the
    # audit table may not exist yet while migrations run.
    return sender.__module__ != '__fake__' and _label(sender) not in EXCLUDED_MODELS


def _secret(field):
    return is_sensitive(field.name) or 'encrypted' in type(field).__name__.lower()


def _fields(instance):
    return [f for f in instance._meta.concrete_fields]


def _value(field, instance):
    return json_value(getattr(instance, field.attname, None))


def _repr(instance):
    try:
        return str(instance)[:255]
    except Exception:
        return f'{instance._meta.object_name} #{instance.pk}'


def create_row(**fields):
    """
    Insert one AuditLog row inside its own savepoint: if the insert fails
    (e.g. the table is missing on a half-migrated DB), only the savepoint is
    rolled back and the caller's transaction -- the change being logged --
    carries on untouched. Without it, a caught DB error would still leave
    the surrounding atomic block unusable.
    """
    from django.db import transaction
    from apps.audit.models import AuditLog
    try:
        with transaction.atomic():
            AuditLog.objects.create(**fields)
    except Exception as e:
        if 'audit_log' in str(e):
            # Table not created yet: `migrate` itself saves rows before the
            # audit migration has run. Nothing to record there.
            logger.debug('audit: table missing, %s row skipped', fields.get('action'))
            return
        logger.exception('audit: could not write %s row', fields.get('action'))


def _write(action, instance, changes):
    create_row(action=action, model=instance._meta.label, object_id=str(instance.pk or '')[:64],
               object_repr=_repr(instance), changes=changes, **context.actor_fields())


@receiver(pre_save, dispatch_uid='audit_pre_save')
def remember_old_values(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or not _tracked(sender) or instance.pk is None or instance._state.adding:
        return
    try:
        from django.db import transaction
        names = [f.attname for f in _fields(instance)]
        with transaction.atomic():
            instance._audit_old = sender._base_manager.filter(pk=instance.pk).values(*names).first()
    except Exception:
        logger.exception('audit: could not read old values for %s', _label(sender))
        instance._audit_old = None


@receiver(post_save, dispatch_uid='audit_post_save')
def log_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw or not _tracked(sender):
        return
    try:
        if created:
            changes = {
                f.name: (MASK if _secret(f) else _value(f, instance))
                for f in _fields(instance)
                if getattr(instance, f.attname, None) not in (None, '') and not f.primary_key
            }
            _write('create', instance, changes)
            return
        old = getattr(instance, '_audit_old', None)
        instance._audit_old = None
        if old is None:
            return
        fields = _fields(instance)
        if update_fields:
            fields = [f for f in fields if f.name in update_fields or f.attname in update_fields]
        changes = {}
        for f in fields:
            before, after = json_value(old.get(f.attname)), _value(f, instance)
            if before == after or f.name in IGNORED_FIELDS:
                continue
            changes[f.name] = [MASK, '(changed)'] if _secret(f) else [before, after]
        if changes:
            _write('update', instance, changes)
    except Exception:
        logger.exception('audit: could not log save of %s', _label(sender))


@receiver(post_delete, dispatch_uid='audit_post_delete')
def log_delete(sender, instance, **kwargs):
    if not _tracked(sender):
        return
    try:
        changes = {f.name: (MASK if _secret(f) else _value(f, instance)) for f in _fields(instance)
                   if getattr(instance, f.attname, None) not in (None, '')}
        _write('delete', instance, changes)
    except Exception:
        logger.exception('audit: could not log delete of %s', _label(sender))


@receiver(m2m_changed, dispatch_uid='audit_m2m')
def log_m2m(sender, instance, action, model, pk_set, **kwargs):
    if action not in ('post_add', 'post_remove', 'post_clear') or not _tracked(type(instance)):
        return
    try:
        field = next((f.name for f in instance._meta.many_to_many if f.remote_field.through is sender), sender._meta.model_name)
        verb = {'post_add': 'added', 'post_remove': 'removed', 'post_clear': 'cleared'}[action]
        items = sorted(str(model.objects.filter(pk=pk).first() or pk) for pk in (pk_set or []))[:50]
        _write('update', instance, {field: {verb: items or True}})
    except Exception:
        logger.exception('audit: could not log m2m change on %s', _label(type(instance)))


def log_login(user, request=None, success=True, username=''):
    """Called by the API login view (JWT) and the Django admin signals below."""
    try:
        fields = context.actor_fields()
        if request is not None and not fields.get('ip_address'):
            fields['ip_address'] = context.client_ip(request)
        if success and user is not None:
            fields.update(actor=user, actor_username=user.get_username(),
                          actor_role='superadmin' if user.is_superuser else (getattr(user, 'role', '') if user.is_staff else 'subscriber'))
        else:
            fields.update(actor=None, actor_username=(username or '')[:150], actor_role='')
        create_row(
            action='login' if success else 'login_failed', model=user._meta.label if user is not None else '',
            object_id=str(getattr(user, 'pk', '') or ''), object_repr=(user.get_username() if user else username or '')[:255],
            **fields,
        )
    except Exception:
        logger.exception('audit: could not log sign-in')


@receiver(user_logged_in, dispatch_uid='audit_admin_login')
def admin_logged_in(sender, request, user, **kwargs):
    log_login(user, request)


@receiver(user_login_failed, dispatch_uid='audit_admin_login_failed')
def admin_login_failed(sender, credentials, request=None, **kwargs):
    # The API login view calls authenticate() too; it logs its own failure
    # once (after the voucher-code retry), so skip the signal for it here.
    if request is None or getattr(request, 'path', '').startswith('/api/'):
        return
    log_login(None, request, success=False, username=credentials.get('username', ''))


# Celery: changes made by background tasks are attributed to the task.
try:
    from celery.signals import task_prerun, task_postrun

    _tokens = {}

    @task_prerun.connect(weak=False)
    def _task_start(task_id=None, task=None, **kwargs):
        _tokens[task_id] = context.start(source='task', actor_username=f'task:{task.name.rsplit(".", 1)[-1]}'[:150])

    @task_postrun.connect(weak=False)
    def _task_end(task_id=None, **kwargs):
        token = _tokens.pop(task_id, None)
        if token is not None:
            try:
                context.end(token)
            except ValueError:
                pass  # different context (e.g. eager task inside a request)
except ImportError:  # pragma: no cover
    pass
