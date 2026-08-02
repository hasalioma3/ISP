#!/bin/bash
# Fast path for routine code changes: syncs files, rebuilds with Docker's
# normal layer cache (so an unchanged requirements.txt/package.json means
# an unchanged, near-instant pip/npm layer), and only recreates the
# containers whose image actually changed -- no `down`, no
# `system prune -af`. That prune is what makes deploy_fresh.sh slow: it
# wipes the build cache on every run, forcing every layer (base image,
# pip install, npm install) to redo from scratch even for a one-line change.
#
# Use this for day-to-day updates. Use deploy_fresh.sh only for a genuinely
# new/from-scratch system, or if the Pi's Docker state needs a hard reset.
set -e

PI_HOST="192.168.88.249"
PI_USER="pi"
REMOTE_DIR="~/ISP"

echo "🔄 Updating Raspberry Pi ($PI_HOST)..."

# 1. Sync Files
echo "📦 Syncing files..."
rsync -avz --progress --exclude 'node_modules' --exclude '.git' --exclude '__pycache__' ./ ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# 2. Remote Commands
echo "🔧 Building and applying changes..."
set +e
ssh ${PI_USER}@${PI_HOST} "\
    if ! command -v docker >/dev/null 2>&1; then \
        echo '❌ Docker is not installed on the Pi -- run ./deploy_fresh.sh first.'; \
        exit 1; \
    fi && \
    cd ${REMOTE_DIR} && \
    if docker compose ps -q db 2>/dev/null | grep -q .; then \
        echo '💾 Quick pre-update backup...' && \
        mkdir -p ~/isp_backups && \
        docker compose exec -T db pg_dump --clean --if-exists -U isp_user isp_billing_prod > ~/isp_backups/pre_update_\$(date +%Y%m%d_%H%M%S).sql; \
    else \
        echo '⏭️  Nothing running yet -- run ./deploy_fresh.sh for the first deploy.'; \
        exit 1; \
    fi && \
    echo '🏗️ Building (cached layers are reused -- only what changed rebuilds)...' && \
    docker compose build && \
    echo '🚀 Applying: only containers whose image actually changed get recreated...' && \
    docker compose up -d && \
    echo '✨ Applying migrations...' && \
    docker compose exec -T backend python manage.py migrate"
DEPLOY_EXIT=$?
set -e

if [ "$DEPLOY_EXIT" -ne 0 ]; then
    echo "❌ Update failed (exit ${DEPLOY_EXIT})."
    exit "$DEPLOY_EXIT"
fi

echo "✅ Update complete!"
