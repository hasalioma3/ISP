#!/bin/bash
# Tears down a company provisioned by provision_company.sh: stops and
# removes its containers, drops its database + role from the shared
# Postgres server, and deletes its env file. Destructive and irreversible --
# confirms by requiring you to re-type the slug.
#
# Usage:
#   ./deprovision_company.sh <slug>
set -e

SLUG="$1"
ENV_FILE="companies/${SLUG}.env"

if [ -z "$SLUG" ]; then
    echo "Usage: $0 <slug>"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ ${ENV_FILE} doesn't exist -- '${SLUG}' isn't a provisioned company."
    exit 1
fi

DB_NAME="isp_${SLUG}"
DB_USER="isp_${SLUG}_user"

echo "⚠️  This permanently deletes '${SLUG}': its containers, its database"
echo "   (${DB_NAME}), and ${ENV_FILE}. This cannot be undone."
read -r -p "Type the company slug ('${SLUG}') to confirm: " CONFIRM
if [ "$CONFIRM" != "$SLUG" ]; then
    echo "Aborted -- input didn't match."
    exit 1
fi

echo "🛑 Stopping and removing containers + volumes..."
docker compose -f docker-compose.company.yml --env-file "$ENV_FILE" -p "isp-${SLUG}" down -v

echo "🗄️  Dropping database ${DB_NAME}..."
docker compose exec -T db psql -U isp_user -d isp_billing_prod -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS ${DB_NAME};
DROP ROLE IF EXISTS ${DB_USER};
SQL

echo "🧹 Removing ${ENV_FILE}..."
rm "$ENV_FILE"

echo "✅ '${SLUG}' fully deprovisioned."
