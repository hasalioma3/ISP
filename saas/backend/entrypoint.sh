#!/bin/sh
set -e
# Wait for Postgres.
if [ -n "$DB_HOST" ]; then
    until nc -z "$DB_HOST" "${DB_PORT:-5432}"; do echo "waiting for $DB_HOST..."; sleep 1; done
fi
# Unlike the ISP app, this stack has one API container, and migrations are
# cheap: the API container applies them (RUN_MIGRATIONS=1 is set only there,
# so worker/beat never race it).
if [ "$RUN_MIGRATIONS" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py bootstrap
    python manage.py ensure_certs --dir /data/certs --host "${TENANT_CERT_HOST:-localhost}"
    python manage.py collectstatic --noinput >/dev/null
fi
exec "$@"
