#!/bin/bash
# Runs ON the Pi (invoked by deploy_update.sh after files are synced):
# backup, rebuild with cached layers, recreate changed containers, migrate.
set -e

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Docker is not installed on the Pi -- run ./deploy_fresh.sh first."
    exit 1
fi

if docker compose ps -q db 2>/dev/null | grep -q .; then
    echo "💾 Quick pre-update backup..."
    mkdir -p ~/isp_backups
    docker compose exec -T db pg_dump --clean --if-exists -U isp_user isp_billing_prod > ~/isp_backups/pre_update_$(date +%Y%m%d_%H%M%S).sql
else
    echo "⏭️  Nothing running yet -- run ./deploy_fresh.sh for the first deploy."
    exit 1
fi

echo "🏗️ Building (cached layers are reused -- only what changed rebuilds)..."
docker compose build

echo "🚀 Applying: only containers whose image actually changed get recreated..."
docker compose up -d

echo "✨ Applying migrations..."
docker compose exec -T backend python manage.py migrate
