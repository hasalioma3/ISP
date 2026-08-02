#!/bin/bash
set -e

# Configuration
PI_HOST="192.168.88.249"
PI_USER="pi"
REMOTE_DIR="~/ISP"

echo "🚀 Deploying to Raspberry Pi ($PI_HOST)..."

# 1. Sync Files
echo "📦 Syncing files..."
rsync -avz --progress --exclude 'node_modules' --exclude '.git' --exclude '__pycache__' ./ ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# 2. Remote Commands
echo "🔧 Executing remote rebuild..."
set +e
ssh ${PI_USER}@${PI_HOST} "\
    if ! command -v docker >/dev/null 2>&1; then \
        echo '🐳 Docker not found on the Pi -- installing...' && \
        curl -fsSL https://get.docker.com | sudo sh && \
        sudo usermod -aG docker \$USER && \
        echo '✅ Docker installed.' && \
        exit 42; \
    fi && \
    cd ${REMOTE_DIR} && \
    echo '📦 Ensuring external volumes exist...' && \
    docker volume create isp_postgres_data >/dev/null && \
    docker volume create isp_static_volume >/dev/null && \
    docker volume create isp_media_volume >/dev/null && \
    if docker compose ps -q db 2>/dev/null | grep -q .; then \
        echo '💾 Backing up database before redeploy...' && \
        mkdir -p ~/isp_backups && \
        docker compose exec -T db pg_dump --clean --if-exists -U isp_user isp_billing_prod > ~/isp_backups/pre_deploy_\$(date +%Y%m%d_%H%M%S).sql; \
    else \
        echo '⏭️  No running db container yet -- skipping pre-deploy backup (this looks like the first deploy).'; \
    fi && \
    echo '🛑 Stopping containers...' && \
    docker compose down && \
    echo '🧹 Pruning unused images and build cache (volumes are left untouched)...' && \
    docker system prune -af && \
    echo '🏗️ Rebuilding and Starting...' && \
    docker compose up -d --build --force-recreate && \
    echo '✨ Applying migrations...' && \
    docker compose exec -T backend python manage.py migrate && \
    if ! docker compose exec -T backend python manage.py shell -c 'from apps.customers.models import Customer; import sys; sys.exit(0 if Customer.objects.filter(is_superuser=True).exists() else 1)' >/dev/null 2>&1; then \
        ADMIN_PW=\$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | head -c 14) && \
        docker compose exec -T -e DJANGO_SUPERUSER_USERNAME=admin -e DJANGO_SUPERUSER_EMAIL=admin@isp.local -e DJANGO_SUPERUSER_PASSWORD=\$ADMIN_PW backend python manage.py createsuperuser --noinput && \
        echo '✅ No superuser existed -- created one: admin /' \$ADMIN_PW '(SAVE THIS, shown once)'; \
    else \
        echo 'ℹ️  Superuser already exists, skipping.'; \
    fi"
DEPLOY_EXIT=$?
set -e

if [ "$DEPLOY_EXIT" -eq 42 ]; then
    echo "🐳 Docker was just installed on the Pi for the first time."
    echo "   Re-run ./deploy_fresh.sh now -- each SSH connection is a fresh login, so"
    echo "   the new docker group membership is already active for the next run."
    exit 0
elif [ "$DEPLOY_EXIT" -ne 0 ]; then
    echo "❌ Deploy failed (exit ${DEPLOY_EXIT})."
    exit "$DEPLOY_EXIT"
fi

echo "✅ Deployment Complete!"
