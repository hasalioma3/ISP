"""
Tenant lifecycle:

  sign-up -> pending -> provisioning -> trial --(owner activates)--> active
                              |            \\--(trial ends, not activated)--> suspended
                            failed          active --(invoice overdue)--> past_due --(grace over)--> suspended
  suspended --(activate / pay / admin resume)--> trial|active
  anything --(admin)--> cancelled (stopped) -> deleted (data removed)

A suspended instance is stopped, not deleted: its data stays until an
admin deletes it (after PlatformSettings.retention_days).
"""
import logging
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from cloud.core.models import PlatformSettings
from cloud.tenants.models import Tenant, TenantEvent, UsageSnapshot
from cloud.tenants.orchestrator import OrchestratorError, get_orchestrator, write_env

logger = logging.getLogger('cloud.tenants')


class TenantError(Exception):
    pass


def log(tenant, kind, message, actor=None, **data):
    TenantEvent.objects.create(tenant=tenant, kind=kind, message=message,
                               actor=actor if getattr(actor, 'pk', None) else None, data=data)
    logger.info('tenant %s: %s', tenant.slug, message)


def notify_owner(tenant, subject, body):
    """Email the ISP owner(s); failures are logged, never raised."""
    cfg = PlatformSettings.load()
    recipients = sorted({tenant.contact_email, *tenant.owners.values_list('email', flat=True)} - {''})
    try:
        send_mail(f'{cfg.brand_name}: {subject}', body + f'\n\n-- {cfg.brand_name}', None, recipients)
    except Exception as e:
        logger.warning('Could not email %s about %r: %s', tenant.slug, subject, e)


# --- allocation -----------------------------------------------------------

def _allocate_port(cfg):
    used = set(Tenant.objects.exclude(port=None).values_list('port', flat=True))
    for port in range(cfg.port_range_start, cfg.port_range_end + 1):
        if port not in used:
            return port
    raise TenantError('No free ports left in the configured range (Settings -> Platform)')


def _allocate_redis_db():
    from django.conf import settings
    used = set(Tenant.objects.exclude(redis_db=None).values_list('redis_db', flat=True))
    # 0 is reserved for this app's own Celery.
    for n in range(1, settings.SAAS_REDIS_DATABASES):
        if n not in used:
            return n
    raise TenantError('No free Redis databases left (raise SAAS_REDIS_DATABASES and restart saas-redis)')


def prepare_instance(tenant):
    """Fill in everything the instance needs, once (idempotent)."""
    cfg = PlatformSettings.load()
    with transaction.atomic():
        t = Tenant.objects.select_for_update().get(pk=tenant.pk)
        t.port = t.port or _allocate_port(cfg)
        t.redis_db = t.redis_db or _allocate_redis_db()
        t.db_name = t.db_name or f't_{t.slug}'
        t.db_user = t.db_user or f't_{t.slug}'
        t.db_password = t.db_password or secrets.token_urlsafe(24)
        t.secret_key = t.secret_key or secrets.token_urlsafe(48)
        t.encryption_key = t.encryption_key or Fernet.generate_key().decode()
        t.c2b_secret = t.c2b_secret or secrets.token_urlsafe(24)
        t.save()
    return t


# --- sign-up & provisioning ----------------------------------------------

def signup(*, company_name, slug, full_name, email, phone, password, plan=None):
    """Create the owner account + tenant and queue provisioning."""
    from django.contrib.auth import get_user_model
    from cloud.pricing.models import PricingPlan
    cfg = PlatformSettings.load()
    if not cfg.signup_enabled:
        raise TenantError('Sign-ups are closed right now.')
    if Tenant.objects.exclude(status='deleted').count() >= cfg.max_tenants:
        raise TenantError('The platform is full right now. Please contact us.')
    User = get_user_model()
    first, _, last = full_name.strip().partition(' ')
    with transaction.atomic():
        tenant = Tenant.objects.create(
            slug=slug, name=company_name.strip(), contact_name=full_name.strip(), contact_email=email.lower(),
            contact_phone=phone, plan=plan or PricingPlan.default(), status='pending',
            pending_admin_password=password)
        user = User.objects.create_user(username=email.lower(), email=email.lower(), password=password,
                                        first_name=first, last_name=last, phone=phone, role='isp_owner', tenant=tenant)
        log(tenant, 'signup', f'{full_name} signed up {company_name}', actor=user)
    from cloud.tenants.tasks import provision_tenant
    transaction.on_commit(lambda: provision_tenant.delay(tenant.pk))
    return tenant, user


def provision(tenant_id):
    """Bring a tenant's instance up from nothing (safe to retry)."""
    from cloud.tenants import tenant_db
    tenant = Tenant.objects.get(pk=tenant_id)
    if tenant.status not in ('pending', 'failed', 'provisioning'):
        return tenant
    cfg = PlatformSettings.load()
    tenant.status, tenant.last_error = 'provisioning', ''
    tenant.save(update_fields=['status', 'last_error'])
    log(tenant, 'provision', 'Setting up the instance')
    orch = get_orchestrator()
    try:
        tenant = prepare_instance(tenant)
        if _real():
            tenant_db.create_database(tenant.db_name, tenant.db_user, tenant.db_password)
        write_env(tenant, cfg)
        orch.up(tenant)
        orch.wait_ready(tenant)
        orch.migrate(tenant)
        password = tenant.pending_admin_password
        if password:
            orch.create_admin(tenant, tenant.admin_username, tenant.contact_email, password, tenant.name)
    except Exception as e:
        logger.exception('Provisioning %s failed', tenant.slug)
        tenant.status, tenant.last_error = 'failed', str(e)[:4000]
        tenant.save(update_fields=['status', 'last_error'])
        log(tenant, 'error', f'Setup failed: {str(e)[:500]}')
        return tenant
    now = timezone.now()
    tenant.pending_admin_password = ''
    tenant.ready_at = now
    tenant.instance_state = 'running'
    tenant.last_health_at = now
    tenant.image_tag = tenant.image_tag or _image_tag()
    if tenant.activated_at:
        tenant.status = 'active'
    else:
        tenant.status = 'trial'
        tenant.trial_ends_at = now + timedelta(days=cfg.trial_days)
    tenant.save()
    log(tenant, 'provision', f'Instance ready at {tenant.url}')
    if tenant.status == 'trial':
        notify_owner(tenant, 'your ISP system is ready', (
            f'Hi {tenant.contact_name or tenant.name},\n\n'
            f'{tenant.name} is ready at {tenant.url}\n'
            f'Sign in with username "{tenant.admin_username}" and the password you chose at sign-up.\n\n'
            f'Your free trial runs until {timezone.localtime(tenant.trial_ends_at):%d %b %Y %H:%M} with every feature '
            f'switched on. Choose a plan any time from your account page to keep it running after that.'))
    return tenant


def _real():
    """True when instances are real Docker stacks with real databases."""
    from django.conf import settings
    return settings.SAAS_ORCHESTRATOR == 'docker'


def _image_tag():
    from django.conf import settings
    return settings.SAAS_IMAGE_TAG


# --- lifecycle actions ------------------------------------------------------

def suspend(tenant, reason, actor=None, notify=True):
    if tenant.status in ('deleted',):
        raise TenantError('This tenant has been deleted')
    try:
        get_orchestrator().stop(tenant)
    except OrchestratorError as e:
        log(tenant, 'error', f'Could not stop the instance: {e}', actor=actor)
        raise TenantError(str(e))
    tenant.status = 'suspended'
    tenant.suspended_at = timezone.now()
    tenant.suspend_reason = reason[:255]
    tenant.instance_state = 'stopped'
    tenant.save(update_fields=['status', 'suspended_at', 'suspend_reason', 'instance_state'])
    log(tenant, 'lifecycle', f'Suspended: {reason}', actor=actor)
    if notify:
        notify_owner(tenant, f'{tenant.name} has been suspended', (
            f'{tenant.name} ({tenant.url}) has been suspended: {reason}.\n\n'
            'Your data is kept. Sign in to your account page to choose a plan or pay an outstanding invoice, '
            'and it comes back straight away.'))
    return tenant


def resume(tenant, actor=None, reason='resumed'):
    if tenant.status not in ('suspended', 'cancelled', 'past_due', 'active', 'trial'):
        raise TenantError(f'Cannot resume a tenant that is {tenant.get_status_display().lower()}')
    try:
        write_env(tenant, PlatformSettings.load())
        get_orchestrator().start(tenant)
    except OrchestratorError as e:
        log(tenant, 'error', f'Could not start the instance: {e}', actor=actor)
        raise TenantError(str(e))
    now = timezone.now()
    if tenant.activated_at:
        tenant.status = 'past_due' if _has_overdue(tenant) else 'active'
    else:
        tenant.status = 'trial'
        if not tenant.trial_ends_at or tenant.trial_ends_at < now:
            tenant.trial_ends_at = now + timedelta(days=1)
    tenant.suspended_at = None
    tenant.suspend_reason = ''
    tenant.instance_state = 'running'
    tenant.save(update_fields=['status', 'suspended_at', 'suspend_reason', 'instance_state', 'trial_ends_at'])
    log(tenant, 'lifecycle', f'Instance started ({reason})', actor=actor)
    return tenant


def _has_overdue(tenant):
    return tenant.invoices.filter(status='open', due_at__lt=timezone.now()).exists()


def activate(tenant, plan, actor=None):
    """The ISP becomes a paying customer (from its trial, or after it ended)."""
    was_suspended = tenant.status == 'suspended'
    tenant.plan = plan
    tenant.activated_at = tenant.activated_at or timezone.now()
    tenant.cancel_requested_at = None
    if tenant.status in ('trial', 'suspended', 'cancelled'):
        tenant.status = 'active'
    tenant.save(update_fields=['plan', 'activated_at', 'status', 'cancel_requested_at'])
    log(tenant, 'billing', f'Subscribed to {plan.name}', actor=actor)
    if was_suspended:
        resume(tenant, actor=actor, reason='subscribed')
    return tenant


def extend_trial(tenant, days, actor=None):
    base = max(tenant.trial_ends_at or timezone.now(), timezone.now())
    tenant.trial_ends_at = base + timedelta(days=days)
    tenant.trial_reminder_sent = False
    tenant.save(update_fields=['trial_ends_at', 'trial_reminder_sent'])
    log(tenant, 'lifecycle', f'Trial extended by {days} day(s) to {timezone.localtime(tenant.trial_ends_at):%d %b %H:%M}', actor=actor)
    if tenant.status == 'suspended' and not tenant.activated_at:
        resume(tenant, actor=actor, reason='trial extended')
    return tenant


def cancel(tenant, actor=None):
    if tenant.instance_state == 'running':
        try:
            get_orchestrator().stop(tenant)
        except OrchestratorError as e:
            raise TenantError(str(e))
    tenant.status = 'cancelled'
    tenant.instance_state = 'stopped'
    tenant.save(update_fields=['status', 'instance_state'])
    log(tenant, 'lifecycle', 'Cancelled (instance stopped, data kept)', actor=actor)
    return tenant


def destroy(tenant, actor=None):
    """Delete the instance and its database. The tenant row and its money
    history stay (status 'deleted') -- the ledger must remain auditable."""
    from cloud.tenants import tenant_db
    from cloud.billing.ledger import balance
    if balance(tenant) > 0:
        raise TenantError('This ISP still has money held for it. Pay it out (or adjust the ledger) before deleting.')
    orch = get_orchestrator()
    try:
        orch.destroy(tenant)
        if _real() and tenant.db_name:
            tenant_db.drop_database(tenant.db_name, tenant.db_user)
    except Exception as e:
        raise TenantError(f'Could not delete the instance: {e}')
    tenant.env_path.unlink(missing_ok=True)
    tenant.status = 'deleted'
    tenant.instance_state = ''
    tenant.port = None
    tenant.redis_db = None
    tenant.save(update_fields=['status', 'instance_state', 'port', 'redis_db'])
    log(tenant, 'lifecycle', 'Instance and database deleted', actor=actor)
    return tenant


def resync(tenant, actor=None):
    """Rewrite the env (e.g. after M-Pesa settings changed) and recreate the
    containers that use it."""
    write_env(tenant, PlatformSettings.load())
    if tenant.is_live:
        get_orchestrator().up(tenant)
    log(tenant, 'instance', 'Configuration re-applied', actor=actor)


def run_lifecycle(now=None):
    """Trial reminders/expiry, overdue invoices -> past_due -> suspended."""
    now = now or timezone.now()
    cfg = PlatformSettings.load()
    done = {'reminded': 0, 'trial_ended': 0, 'past_due': 0, 'suspended': 0}
    for t in Tenant.objects.filter(status='trial', trial_reminder_sent=False, trial_ends_at__lte=now + timedelta(hours=24),
                                   trial_ends_at__gt=now):
        notify_owner(t, 'your free trial ends soon', (
            f'The free trial of {t.name} ends on {timezone.localtime(t.trial_ends_at):%d %b at %H:%M}.\n'
            'Choose a plan from your account page to keep your system running -- nothing else changes, your data '
            'and settings stay as they are.'))
        t.trial_reminder_sent = True
        t.save(update_fields=['trial_reminder_sent'])
        done['reminded'] += 1
    for t in Tenant.objects.filter(status='trial', trial_ends_at__lte=now):
        if t.activated_at:
            t.status = 'active'
            t.save(update_fields=['status'])
            continue
        try:
            suspend(t, 'the free trial ended')
            done['trial_ended'] += 1
        except TenantError:
            pass
    from cloud.billing.models import Invoice
    overdue = Invoice.objects.filter(status='open', due_at__lt=now).select_related('tenant')
    for inv in overdue:
        t = inv.tenant
        if t.status == 'active':
            t.status = 'past_due'
            t.save(update_fields=['status'])
            log(t, 'billing', f'Invoice {inv.number} is overdue')
            notify_owner(t, f'invoice {inv.number} is overdue', (
                f'Invoice {inv.number} for KES {inv.amount:,.0f} was due on {timezone.localtime(inv.due_at):%d %b}. '
                f'Please pay it from your account page within {cfg.grace_days} days to avoid suspension.'))
            done['past_due'] += 1
        if t.status == 'past_due' and inv.due_at < now - timedelta(days=cfg.grace_days):
            try:
                suspend(t, f'invoice {inv.number} is unpaid')
                done['suspended'] += 1
            except TenantError:
                pass
    return done


# --- metrics & health ------------------------------------------------------

def refresh_metrics(tenant):
    """Read subscriber counts and fold them into today's snapshot."""
    from cloud.tenants import tenant_db
    if _real():
        counts = tenant_db.read_counts(tenant)
    else:
        counts = tenant.metrics.get('fake_counts') or {'active': {}, 'all': {}}
    now = timezone.now()
    snap, _ = UsageSnapshot.objects.get_or_create(tenant=tenant, date=timezone.localdate(now))
    peak = snap.peak or {}
    for basis in ('active', 'all'):
        peak.setdefault(basis, {})
        for stype, n in counts.get(basis, {}).items():
            peak[basis][stype] = max(int(peak[basis].get(stype, 0)), int(n))
    snap.peak, snap.latest, snap.samples = peak, counts, snap.samples + 1
    snap.save()
    metrics = dict(tenant.metrics)
    metrics.update({'active': counts.get('active', {}), 'all': counts.get('all', {})})
    tenant.metrics, tenant.metrics_at = metrics, now
    tenant.save(update_fields=['metrics', 'metrics_at'])
    return counts


def check_health(tenant):
    import requests
    if not _real():
        state = get_orchestrator().state(tenant)
    else:
        try:
            from cloud.billing.collections import TENANT_HEADERS
            r = requests.get(f'{tenant.backend_url}/api/settings/site/', timeout=8, headers=TENANT_HEADERS,
                             allow_redirects=False)
            state = 'running' if r.status_code < 300 else 'unhealthy'
        except requests.RequestException:
            state = get_orchestrator().state(tenant)
            if state == 'running':
                state = 'unhealthy'
    changed = state != tenant.instance_state
    tenant.instance_state = state
    if state == 'running':
        tenant.last_health_at = timezone.now()
    tenant.save(update_fields=['instance_state', 'last_health_at'])
    if changed and state in ('unhealthy', 'missing') and tenant.is_live:
        log(tenant, 'error', f'Instance is {tenant.get_instance_state_display().lower()}')
    return state
