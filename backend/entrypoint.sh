#!/bin/sh

# Wait for postgres
if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for postgres..."

    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL started"
fi

# Migrations are applied as a single deliberate step by the deploy
# scripts (deploy_fresh.sh / deploy_update.sh) right after `docker compose
# up -d` -- NOT here. This entrypoint runs for backend, celery_worker, and
# celery_beat alike (same image, different command), so auto-migrating
# here meant multiple containers raced to apply the same pending
# migration concurrently on every deploy -- whichever committed first
# left the others hitting "relation/column already exists" against a
# migration history that (from their point of view, mid-race) still
# looked unapplied.

# Collect static files
python manage.py collectstatic --no-input

# Start server
exec "$@"
