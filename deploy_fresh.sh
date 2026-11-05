#!/bin/bash
set -e

# Configuration
PI_HOST="192.168.56.245"
PI_USER="ali"
REMOTE_DIR="~/ISP"

echo "🚀 Deploying to Raspberry Pi ($PI_HOST)..."

# 1. Sync Files
#
# --delete removes files on the Pi that no longer exist locally (e.g. a
# renamed/deleted migration file) -- without it, a deleted file just sits
# on the Pi forever, which is exactly what caused a migration-graph
# conflict (two divergent migration chains, old + new) on a prior deploy.
# .env.prod is intentionally copied from this machine to configure the
# deployment. The other excluded paths are server-only or generated secrets.
echo "📦 Syncing files..."
rsync -avz --delete --progress \
    --exclude 'node_modules' --exclude '.git' --exclude '__pycache__' \
    --exclude '.env' --exclude 'backend/.env' --exclude 'frontend/.env' \
    --exclude 'companies/*.env' --exclude 'vps' --exclude 'teststk.py' \
    ./ ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# 2. Remote Commands
echo "🔧 Executing remote rebuild..."
set +e
ssh -t ${PI_USER}@${PI_HOST} "\
    if ! command -v docker >/dev/null 2>&1; then \
        echo '🐳 Docker not found on the Pi -- installing...' && \
        curl -fsSL https://get.docker.com | sudo sh && \
        sudo usermod -aG docker \$USER && \
        echo '✅ Docker installed.' && \
        exit 42; \
    fi && \
    if ! docker info >/dev/null 2>&1; then \
        echo '🔐 Checking Docker group permissions...' && \
        sudo -v && \
        if sudo -n docker info >/dev/null 2>&1; then \
            sudo usermod -aG docker \$USER && \
            echo '✅ Added this account to the docker group.' && \
            exit 42; \
        else \
            echo '❌ Docker is installed but unavailable. Check that the daemon is running and this account can use sudo.'; \
            exit 1; \
        fi; \
    fi && \
    cd ${REMOTE_DIR} && \
    echo '📦 Ensuring external volumes exist...' && \
    docker volume create isp_postgres_data >/dev/null && \
    docker volume create isp_static_volume >/dev/null && \
    docker volume create isp_media_volume >/dev/null && \
    docker volume create isp_whatsapp_session >/dev/null && \
    if docker compose ps -q db 2>/dev/null | grep -q .; then \
        echo '💾 Backing up database before redeploy...' && \
        mkdir -p ~/isp_backups && \
        docker compose exec -T db pg_dump --clean --if-exists -U isp_user isp_billing_prod > ~/isp_backups/pre_deploy_\$(date +%Y%m%d_%H%M%S).sql; \
    else \
        echo '⏭️  No running db container yet -- skipping pre-deploy backup (this looks like the first deploy).'; \
    fi && \
    echo '🛑 Stopping containers...' && \
    docker compose down && \
    echo '🏗️ Rebuilding and Starting...' && \
    docker compose --progress=plain up -d --build --force-recreate && \
    echo '✨ Applying migrations...' && \
    docker compose exec -T backend python manage.py migrate && \
    if ! docker compose exec -T backend python manage.py shell -c 'from apps.customers.models import Customer; import sys; sys.exit(0 if Customer.objects.filter(is_superuser=True).exists() else 1)' >/dev/null 2>&1; then \
        echo 'No superuser exists. Create one now:' && \
        docker compose exec backend python manage.py createsuperuser; \
    else \
        echo 'ℹ️  Superuser already exists, skipping.'; \
    fi"
DEPLOY_EXIT=$?
set -e

if [ "$DEPLOY_EXIT" -eq 42 ]; then
    echo "🔄 Docker setup or group membership changed on the server."
    echo "   Run ./deploy_fresh.sh again; the next SSH login will apply the change."
    exit 0
elif [ "$DEPLOY_EXIT" -ne 0 ]; then
    echo "❌ Deploy failed (exit ${DEPLOY_EXIT})."
    exit "$DEPLOY_EXIT"
fi

echo "✅ Deployment Complete!"
