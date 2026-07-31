#!/bin/bash
# Provisions a brand-new company/tenant on this same host: its own Postgres
# database + role on the shared Postgres server, its own Redis DB index,
# its own backend/frontend/celery containers on a dedicated port, and a
# default admin account -- all isolated from every other company.
#
# Usage:
#   ./provision_company.sh <slug> "<Display Name>" <port>
#
# Example:
#   ./provision_company.sh acme "Acme Wireless" 8081
set -e

HOST_IP="192.168.88.252"

SLUG="$1"
DISPLAY_NAME="$2"
PORT="$3"

if [ -z "$SLUG" ] || [ -z "$DISPLAY_NAME" ] || [ -z "$PORT" ]; then
    echo "Usage: $0 <slug> \"<Display Name>\" <port>"
    echo "Example: $0 acme \"Acme Wireless\" 8081"
    exit 1
fi

if ! [[ "$SLUG" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "❌ <slug> must be lowercase letters/digits/underscores, starting with a letter (e.g. 'acme', not 'Acme' or 'acme-wireless')."
    exit 1
fi

ENV_FILE="companies/${SLUG}.env"

if [ -f "$ENV_FILE" ]; then
    echo "❌ ${ENV_FILE} already exists -- '${SLUG}' looks like it's already provisioned."
    echo "   (To reprovision from scratch: ./deprovision_company.sh ${SLUG}, then re-run this script.)"
    exit 1
fi

if grep -h "^COMPANY_PORT=${PORT}$" companies/*.env 2>/dev/null | grep -q .; then
    echo "❌ Port ${PORT} is already used by another company. Pick a different one."
    exit 1
fi

# --- Pick the next free Redis DB index (0 is the main isp-billing project; 1-15 available) ---
REDIS_INDEX=1
while grep -h "^CELERY_BROKER_URL=redis://redis:6379/${REDIS_INDEX}$" companies/*.env 2>/dev/null | grep -q .; do
    REDIS_INDEX=$((REDIS_INDEX + 1))
done
if [ "$REDIS_INDEX" -gt 15 ]; then
    echo "❌ All 15 available Redis DB indexes are in use. Can't provision another company without a second Redis instance."
    exit 1
fi

# --- Generate secrets ---
SECRET_KEY=$(openssl rand -hex 32)
DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | head -c 14)
DB_NAME="isp_${SLUG}"
DB_USER="isp_${SLUG}_user"

echo "🏗️  Provisioning '${DISPLAY_NAME}' (${SLUG}) on port ${PORT}, Redis DB ${REDIS_INDEX}..."

# --- Create the database + role on the shared Postgres server ---
echo "🗄️  Creating database ${DB_NAME}..."
docker compose exec -T db psql -U isp_user -d isp_billing_prod -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
SQL

# --- Write the company's env file from the template ---
echo "📝 Writing ${ENV_FILE}..."
sed \
    -e "s|__SLUG__|${SLUG}|g" \
    -e "s|__PORT__|${PORT}|g" \
    -e "s|__SECRET_KEY__|${SECRET_KEY}|g" \
    -e "s|__HOST_IP__|${HOST_IP}|g" \
    -e "s|__DB_NAME__|${DB_NAME}|g" \
    -e "s|__DB_USER__|${DB_USER}|g" \
    -e "s|__DB_PASSWORD__|${DB_PASSWORD}|g" \
    -e "s|__REDIS_INDEX__|${REDIS_INDEX}|g" \
    companies/.env.template > "$ENV_FILE"

# --- Bring the stack up ---
echo "🚀 Building and starting containers..."
COMPOSE="docker compose -f docker-compose.company.yml --env-file ${ENV_FILE} -p isp-${SLUG}"
$COMPOSE up -d --build

echo "⏳ Waiting for the backend to be ready..."
for i in $(seq 1 30); do
    if $COMPOSE exec -T backend python manage.py check >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo "✨ Running migrations..."
$COMPOSE exec -T backend python manage.py migrate

echo "👤 Creating default admin..."
$COMPOSE exec -T \
    -e DJANGO_SUPERUSER_USERNAME=admin \
    -e DJANGO_SUPERUSER_EMAIL="admin@${SLUG}.local" \
    -e DJANGO_SUPERUSER_PASSWORD="${ADMIN_PASSWORD}" \
    backend python manage.py createsuperuser --noinput

echo "🏷️  Setting company branding name..."
$COMPOSE exec -T -e SEED_COMPANY_NAME="${DISPLAY_NAME}" backend python manage.py shell <<'PYEOF'
import os
from apps.sitesettings.models import SiteSettings
s = SiteSettings.load()
s.company_name = os.environ['SEED_COMPANY_NAME']
s.save()
print(f"Seeded company_name={s.company_name!r}")
PYEOF

cat <<SUMMARY

✅ '${DISPLAY_NAME}' is live.

   Portal:         https://${HOST_IP}:${PORT}/
   Admin login:    admin / ${ADMIN_PASSWORD}
   Env file:       ${ENV_FILE}

⚠️  Before this company can take real payments or reach a router, edit
   ${ENV_FILE} and replace the MPESA_* and MIKROTIK_* CHANGE_ME values with
   their real credentials, then run:
   ${COMPOSE} up -d --force-recreate

SUMMARY
