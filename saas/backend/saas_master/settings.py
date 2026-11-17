"""
Settings for the ISP Cloud master application: the control plane that signs
ISPs up, runs one instance of the ISP billing app per ISP, bills them per
subscriber, collects their customers' M-Pesa payments on the platform's
shortcode and settles the money back to them.

It is a separate Django project from the ISP billing app (../../backend) and
has its own database. It imports a few pieces of that app instead of copying
them (see ISP_BACKEND_DIR below) and never modifies it.
"""
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# The ISP billing app's backend, put on the path so its reusable pieces
# (e.g. apps.notifications.fields.EncryptedCharField) are imported, not
# duplicated. In Docker it's copied to /isp_backend by the Dockerfile.
ISP_BACKEND_DIR = Path(config('ISP_BACKEND_DIR', default=str(BASE_DIR.parent.parent / 'backend')))
if str(ISP_BACKEND_DIR) not in sys.path:
    sys.path.append(str(ISP_BACKEND_DIR))

SECRET_KEY = config('SECRET_KEY', default='dev-only-insecure-key-change-me')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'cloud.accounts',
    'cloud.core',
    'cloud.pricing',
    'cloud.tenants',
    'cloud.billing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'saas_master.urls'
WSGI_APPLICATION = 'saas_master.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

DATABASES = {
    'default': dj_database_url.config(default=f'sqlite:///{BASE_DIR / "db.sqlite3"}', conn_max_age=60),
}

AUTH_USER_MODEL = 'accounts.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/django-static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_RATES': {'signup': config('SIGNUP_THROTTLE', default='10/hour'), 'login': '30/minute'},
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=12),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Encrypts secrets stored in this database (Daraja keys, initiator password,
# each tenant's DB password and keys). Named like the ISP app's setting
# because its EncryptedCharField, which we reuse, reads this name.
NOTIFICATIONS_ENCRYPTION_KEY = config('SAAS_ENCRYPTION_KEY', default='')
if not NOTIFICATIONS_ENCRYPTION_KEY and (DEBUG or 'test' in sys.argv):
    # Throwaway key for tests/local runs only -- anything encrypted with it
    # is unreadable after a restart. Production must set SAAS_ENCRYPTION_KEY.
    from cryptography.fernet import Fernet
    NOTIFICATIONS_ENCRYPTION_KEY = Fernet.generate_key().decode()

# --- Celery ---------------------------------------------------------------
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    # Trials ending soon / ended, overdue invoices -> suspension.
    'lifecycle': {'task': 'cloud.tenants.tasks.run_lifecycle', 'schedule': crontab(minute='*/10')},
    # Subscriber counts per tenant (what billing is based on).
    'metrics': {'task': 'cloud.tenants.tasks.refresh_all_metrics', 'schedule': crontab(minute=15)},
    'health': {'task': 'cloud.tenants.tasks.check_all_health', 'schedule': crontab(minute='*/5')},
    # Monthly invoices, run daily: only the configured invoice day does anything.
    'invoices': {'task': 'cloud.billing.tasks.run_invoicing', 'schedule': crontab(minute=30, hour=1)},
    # Settlements: hourly, gated on the configured schedule.
    'settlements': {'task': 'cloud.billing.tasks.run_scheduled_settlements', 'schedule': crontab(minute=45)},
    # STK callbacks whose verification failed transiently.
    'verify-collections': {'task': 'cloud.billing.tasks.verify_pending_collections', 'schedule': crontab(minute='*/15')},
}

# --- Tenant orchestration -------------------------------------------------
# 'docker' runs real stacks through the Docker socket; 'fake' only records
# what it would do (tests, or developing the UI without Docker).
SAAS_ORCHESTRATOR = config('SAAS_ORCHESTRATOR', default='fake')
SAAS_TENANT_COMPOSE_FILE = config('SAAS_TENANT_COMPOSE_FILE', default=str(BASE_DIR.parent / 'tenant' / 'docker-compose.tenant.yml'))
SAAS_DATA_DIR = Path(config('SAAS_DATA_DIR', default=str(BASE_DIR / 'data')))
SAAS_TENANT_ENV_DIR = SAAS_DATA_DIR / 'tenants'
SAAS_IMAGE_PREFIX = config('SAAS_IMAGE_PREFIX', default='isp-saas/tenant-')
SAAS_IMAGE_TAG = config('SAAS_IMAGE_TAG', default='latest')
SAAS_NETWORK = config('SAAS_NETWORK', default='saas_network')
SAAS_TENANT_SUBNET_BASE = config('SAAS_TENANT_SUBNET_BASE', default='10.200')
SAAS_CERTS_VOLUME = config('SAAS_CERTS_VOLUME', default='saas_tenant_certs')
# How tenant containers reach the shared Postgres/Redis (hostnames on SAAS_NETWORK).
SAAS_TENANT_DB_HOST = config('SAAS_TENANT_DB_HOST', default='saas-db')
SAAS_TENANT_DB_PORT = config('SAAS_TENANT_DB_PORT', default=5432, cast=int)
SAAS_TENANT_REDIS_HOST = config('SAAS_TENANT_REDIS_HOST', default='saas-redis')
SAAS_REDIS_DATABASES = config('SAAS_REDIS_DATABASES', default=1024, cast=int)
# Superuser connection used to create/drop tenant databases and read their
# subscriber counts. Defaults to this app's own database server.
SAAS_DB_ADMIN_URL = config('SAAS_DB_ADMIN_URL', default='')
# How this server reaches a tenant's backend directly (forwarding M-Pesa
# callbacks, health checks). {slug} is filled in.
SAAS_TENANT_BACKEND_URL = config('SAAS_TENANT_BACKEND_URL', default='http://t-{slug}-backend:8000')

# --- Email ----------------------------------------------------------------
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='ISP Cloud <no-reply@localhost>')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'plain': {'format': '%(levelname)s %(asctime)s %(name)s %(message)s'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'plain'}},
    'loggers': {'cloud': {'handlers': ['console'], 'level': config('LOG_LEVEL', default='INFO')}},
}
