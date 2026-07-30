#!/bin/bash
set -e

# Configuration
PI_HOST="192.168.88.253"
PI_USER="pi"
REMOTE_DIR="~/ISP"

echo "🚀 Deploying to Raspberry Pi ($PI_HOST)..."

# 1. Sync Files
echo "📦 Syncing files..."
rsync -avz --progress --exclude 'node_modules' --exclude '.git' --exclude '__pycache__' ./ ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# 2. Remote Commands
echo "🔧 Executing remote rebuild..."
ssh ${PI_USER}@${PI_HOST} "cd ${REMOTE_DIR} && \
    echo '💾 Backing up database before redeploy...' && \
    mkdir -p ~/isp_backups && \
    docker compose exec -T db pg_dump --clean --if-exists -U isp_user isp_billing_prod > ~/isp_backups/pre_deploy_\$(date +%Y%m%d_%H%M%S).sql && \
    echo '🛑 Stopping containers...' && \
    docker compose down && \
    echo '🧹 Pruning unused images and build cache (volumes are left untouched)...' && \
    docker system prune -af && \
    echo '🏗️ Rebuilding and Starting...' && \
    docker compose up -d --build --force-recreate && \
    echo '✨ Applying migrations...' && \
    docker compose exec -T backend python manage.py migrate"

echo "✅ Deployment Complete!"
