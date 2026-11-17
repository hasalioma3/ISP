"""
Runs each ISP's instance of the ISP billing app as its own Docker Compose
project (saas-<slug>), from saas/tenant/docker-compose.tenant.yml and an env
file this module writes (SAAS_DATA_DIR/tenants/<slug>.env).

This is the same shape as the repo's provision_company.sh, done from
Python so the master app can do it unattended on sign-up: database + role,
env file, `up -d`, migrate, admin account, company name. The stacks use
pre-built images (saas/build_tenant_images.sh) so a sign-up never waits on
a build, and they contain no bind mounts -- this code runs inside a
container talking to the host's Docker socket, where a relative bind path
would point at the wrong place.

SAAS_ORCHESTRATOR=fake swaps in FakeOrchestrator, which records the calls
and pretends they worked (tests; UI work without Docker).
"""
import logging
import os
import subprocess
import time

from django.conf import settings

logger = logging.getLogger('cloud.tenants')


class OrchestratorError(Exception):
    pass


def tenant_subnet(tenant):
    """10.200.0.0/24, 10.200.1.0/24, ... one /24 per tenant, from its unique Redis index."""
    n = tenant.redis_db or 0
    first, second = settings.SAAS_TENANT_SUBNET_BASE.split('.')[:2]
    return f'{first}.{int(second) + n // 256}.{n % 256}.0/24'


def tenant_env(tenant, cfg):
    """The tenant instance's environment. Everything in here is visible to
    the ISP's own admins (it's their server; their backups include it), so
    it only ever holds the tenant-scoped Daraja app and secrets of its own."""
    url = tenant.url.rstrip('/')
    host = cfg.tenant_host
    callback = cfg.public_url(f'/api/mpesa/stk/{tenant.callback_token}/') if cfg.public_base_url else ''
    backend_alias = f't-{tenant.slug}-backend'
    return {
        'COMPANY_SLUG': tenant.slug,
        'TENANT_SLUG': tenant.slug,
        'TENANT_PORT': str(tenant.port),
        'TENANT_IMAGE_PREFIX': settings.SAAS_IMAGE_PREFIX,
        'TENANT_IMAGE_TAG': tenant.image_tag or settings.SAAS_IMAGE_TAG,
        'SAAS_NETWORK': settings.SAAS_NETWORK,
        'SAAS_CERTS_VOLUME': settings.SAAS_CERTS_VOLUME,
        # Fixed per tenant rather than Docker's pick, which can land on a
        # range something else on the host uses (UISP hard-codes 172.18.251.0/24).
        'TENANT_SUBNET': tenant_subnet(tenant),
        'TENANT_ENV_FILE': str(tenant.env_path),
        'SECRET_KEY': tenant.secret_key,
        'DEBUG': 'False',
        # The alias is how this server forwards M-Pesa callbacks to it.
        'ALLOWED_HOSTS': ','.join(dict.fromkeys([host, 'localhost', '127.0.0.1', backend_alias])),
        'NOTIFICATIONS_ENCRYPTION_KEY': tenant.encryption_key,
        'DATABASE_URL': (f'postgresql://{tenant.db_user}:{tenant.db_password}@{settings.SAAS_TENANT_DB_HOST}:'
                         f'{settings.SAAS_TENANT_DB_PORT}/{tenant.db_name}'),
        'DATABASE': 'postgres',
        'SQL_HOST': settings.SAAS_TENANT_DB_HOST,
        'SQL_PORT': str(settings.SAAS_TENANT_DB_PORT),
        'CELERY_BROKER_URL': f'redis://{settings.SAAS_TENANT_REDIS_HOST}:6379/{tenant.redis_db}',
        'CELERY_RESULT_BACKEND': f'redis://{settings.SAAS_TENANT_REDIS_HOST}:6379/{tenant.redis_db}',
        'MPESA_ENVIRONMENT': cfg.mpesa_environment,
        'MPESA_CONSUMER_KEY': cfg.tenant_consumer_key,
        'MPESA_CONSUMER_SECRET': cfg.tenant_consumer_secret,
        'MPESA_SHORTCODE': cfg.mpesa_shortcode,
        'MPESA_SHORTCODE_TYPE': cfg.mpesa_shortcode_type,
        'MPESA_TILL_NUMBER': cfg.mpesa_till_number,
        'MPESA_PASSKEY': cfg.mpesa_passkey,
        'MPESA_CALLBACK_URL': callback,
        # Only for this server -> instance forwarding of C2B confirmations;
        # Safaricom itself only ever calls the platform's C2B URLs.
        'MPESA_C2B_SECRET': tenant.c2b_secret,
        'CAPTIVE_PORTAL_URL': f'{url}/portal' if url else '',
        'CORS_ALLOWED_ORIGINS': url,
        'CSRF_TRUSTED_ORIGINS': url,
        'MIKROTIK_HOST': '',
    }


def write_env(tenant, cfg):
    env = tenant_env(tenant, cfg)
    path = tenant.env_path
    path.parent.mkdir(parents=True, exist_ok=True)
    body = '# Written by the ISP Cloud master app -- edits are overwritten.\n'
    body += ''.join(f'{k}={str(v).replace(chr(10), "")}\n' for k, v in env.items())
    tmp = path.with_suffix('.tmp')
    tmp.write_text(body)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


class DockerOrchestrator:
    def _compose(self, tenant, *args, check=True, timeout=900, input_text=None, extra_env=None):
        cmd = ['docker', 'compose', '-p', tenant.project, '-f', settings.SAAS_TENANT_COMPOSE_FILE,
               '--env-file', str(tenant.env_path), *args]
        env = {**os.environ, **(extra_env or {})}
        logger.info('tenant %s: %s', tenant.slug, ' '.join(args[:4]))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text, env=env)
        except FileNotFoundError:
            raise OrchestratorError('The docker CLI is not available to this worker')
        except subprocess.TimeoutExpired:
            raise OrchestratorError(f'docker compose {args[0]} timed out')
        if check and proc.returncode != 0:
            raise OrchestratorError((proc.stderr or proc.stdout).strip()[-1500:] or f'docker compose {args[0]} failed')
        return proc

    def _manage(self, tenant, *args, env=None, input_text=None, timeout=600):
        extra = []
        for k, v in (env or {}).items():
            extra += ['-e', k]  # value passed through the environment, never on the command line
        return self._compose(tenant, 'exec', '-T', *extra, 'backend', 'python', 'manage.py', *args,
                             input_text=input_text, extra_env=env, timeout=timeout)

    def up(self, tenant):
        self._compose(tenant, 'up', '-d', '--remove-orphans')

    def wait_ready(self, tenant, attempts=60):
        for _ in range(attempts):
            proc = self._compose(tenant, 'exec', '-T', 'backend', 'python', 'manage.py', 'check', check=False, timeout=120)
            if proc.returncode == 0:
                return
            time.sleep(3)
        raise OrchestratorError('The instance backend did not become ready')

    def migrate(self, tenant):
        self._manage(tenant, 'migrate', '--noinput', timeout=1800)

    def create_admin(self, tenant, username, email, password, company_name):
        self._manage(tenant, 'createsuperuser', '--noinput', env={
            'DJANGO_SUPERUSER_USERNAME': username, 'DJANGO_SUPERUSER_EMAIL': email,
            'DJANGO_SUPERUSER_PASSWORD': password}, timeout=300)
        script = ("import os\nfrom apps.sitesettings.models import SiteSettings\n"
                  "s = SiteSettings.load()\ns.company_name = os.environ['SEED_COMPANY_NAME'][:100]\ns.save()\n")
        self._manage(tenant, 'shell', env={'SEED_COMPANY_NAME': company_name}, input_text=script)

    def start(self, tenant):
        self.up(tenant)

    def stop(self, tenant):
        self._compose(tenant, 'stop', timeout=300)

    def destroy(self, tenant):
        self._compose(tenant, 'down', '-v', '--remove-orphans', check=False, timeout=600)

    def state(self, tenant):
        """-> 'running' | 'stopped' | 'missing' (from the containers, not the app)."""
        proc = self._compose(tenant, 'ps', '-a', '--format', '{{.Service}} {{.State}}', check=False, timeout=60)
        rows = [line.split() for line in proc.stdout.splitlines() if line.strip()]
        if not rows:
            return 'missing'
        states = {svc: st for svc, st, *_ in rows}
        return 'running' if states.get('backend') == 'running' and states.get('frontend') == 'running' else 'stopped'

    def logs(self, tenant, service='backend', lines=200):
        proc = self._compose(tenant, 'logs', '--no-color', '--tail', str(lines), service, check=False, timeout=60)
        return proc.stdout[-20000:]


class FakeOrchestrator:
    """Records calls; every instance 'works'. Subscriber counts come from
    tenant.metrics['fake_counts'] when a test sets them."""
    calls = []

    def _rec(self, name, tenant, **kw):
        FakeOrchestrator.calls.append((name, tenant.slug, kw))

    def up(self, tenant):
        self._rec('up', tenant)

    def wait_ready(self, tenant):
        self._rec('wait_ready', tenant)

    def migrate(self, tenant):
        self._rec('migrate', tenant)

    def create_admin(self, tenant, username, email, password, company_name):
        self._rec('create_admin', tenant, username=username, email=email, company_name=company_name)

    def start(self, tenant):
        self._rec('start', tenant)

    def stop(self, tenant):
        self._rec('stop', tenant)

    def destroy(self, tenant):
        self._rec('destroy', tenant)

    def state(self, tenant):
        return 'stopped' if tenant.status == 'suspended' else 'running'

    def logs(self, tenant, service='backend', lines=200):
        return f'(fake orchestrator: no logs for {tenant.slug}/{service})'


def get_orchestrator():
    return DockerOrchestrator() if settings.SAAS_ORCHESTRATOR == 'docker' else FakeOrchestrator()
