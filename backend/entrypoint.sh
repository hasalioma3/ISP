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

# Run migrations
python manage.py makemigrations core
python manage.py makemigrations
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

# Debug: Check if index.html is where we expect it
echo "Checking for index.html..."
ls -l /app/frontend_dist/index.html || echo "index.html NOT FOUND"

# Start server
echo "Starting Gunicorn..."
exec "$@"
