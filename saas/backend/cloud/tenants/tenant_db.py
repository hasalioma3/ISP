"""
Direct access to the tenants' databases on the shared Postgres server:
creating/dropping them, and the few read-only queries the platform needs
(subscriber counts for billing, "does this account exist?" for routing a
paybill payment). Reads use the ISP app's table names (customers,
subscriptions) -- they're that app's schema, read here, never written.

Only billing-relevant counts are read from a tenant's database. Money is
never taken from it: an ISP's admin controls that data, so collections come
only from M-Pesa's own callbacks to this server (cloud.billing).
"""
import logging
from contextlib import contextmanager

import dj_database_url
from django.conf import settings

logger = logging.getLogger('cloud.tenants')

SERVICE_TYPES = ('pppoe', 'hotspot', 'static')


class TenantDBError(Exception):
    pass


def _admin_params():
    url = settings.SAAS_DB_ADMIN_URL
    cfg = dj_database_url.parse(url) if url else settings.DATABASES['default']
    if 'postgresql' not in cfg.get('ENGINE', ''):
        raise TenantDBError('Tenant databases need PostgreSQL (set DATABASE_URL / SAAS_DB_ADMIN_URL)')
    return {'host': cfg.get('HOST') or 'localhost', 'port': cfg.get('PORT') or 5432,
            'user': cfg.get('USER'), 'password': cfg.get('PASSWORD'), 'dbname': cfg.get('NAME')}


@contextmanager
def connect(dbname=None, autocommit=False):
    import psycopg2
    params = _admin_params()
    if dbname:
        params['dbname'] = dbname
    try:
        conn = psycopg2.connect(connect_timeout=8, **params)
    except psycopg2.Error as e:
        raise TenantDBError(f'Could not connect to database {params["dbname"]}: {e}'.strip())
    conn.autocommit = autocommit
    try:
        yield conn
    finally:
        conn.close()


def create_database(name, user, password):
    from psycopg2 import sql
    with connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', [user])
        if cur.fetchone():
            cur.execute(sql.SQL('ALTER ROLE {} WITH LOGIN PASSWORD %s').format(sql.Identifier(user)), [password])
        else:
            cur.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD %s').format(sql.Identifier(user)), [password])
        cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', [name])
        if not cur.fetchone():
            cur.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name), sql.Identifier(user)))
        # Tenants can't reach each other's databases even with a leaked password.
        cur.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))


def drop_database(name, user):
    from psycopg2 import sql
    with connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s', [name])
        cur.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(name)))
        cur.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(user)))


def read_counts(tenant):
    """
    -> {'active': {pppoe: n, hotspot: n, static: n}, 'all': {...}}
    active = subscriber accounts with a subscription live right now;
    all    = every subscriber account (staff excluded).
    """
    out = {'active': dict.fromkeys(SERVICE_TYPES, 0), 'all': dict.fromkeys(SERVICE_TYPES, 0)}
    with connect(tenant.db_name) as conn, conn.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT service_type, COUNT(*) FROM customers WHERE is_staff = false GROUP BY service_type""")
        for stype, n in cur.fetchall():
            if stype in out['all']:
                out['all'][stype] = n
        cur.execute("""
            SELECT c.service_type, COUNT(DISTINCT c.id) FROM customers c
            JOIN subscriptions s ON s.customer_id = c.id
            WHERE c.is_staff = false AND s.status = 'active' AND s.expiry_date > now()
            GROUP BY c.service_type""")
        for stype, n in cur.fetchall():
            if stype in out['active']:
                out['active'][stype] = n
    return out


def account_exists(tenant, account):
    """Does this tenant have a subscriber with this username (case-insensitive)?"""
    with connect(tenant.db_name) as conn, conn.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute('SELECT 1 FROM customers WHERE is_staff = false AND lower(username) = lower(%s) LIMIT 1', [account])
        return cur.fetchone() is not None
