#!/bin/bash

# Configuration
PI_HOST="192.168.88.253"
PI_USER="pi"
REMOTE_DIR="~/ISP"

echo "🚀 Starting Nuclear Deployment to Raspberry Pi..."

# 1. Sync Files
echo "📦 Syncing files..."
rsync -avz --progress --exclude 'node_modules' --exclude '.git' --exclude '__pycache__' ./ ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# 2. Remote Commands
echo "🔧 Executing remote rebuild..."
ssh ${PI_USER}@${PI_HOST} "cd ${REMOTE_DIR} && \
    echo '🛑 Stopping containers...' && \
    docker compose down && \
    echo '🧹 Pruning system (removing unused images/containers)...' && \
    docker system prune -af --volumes && \
    echo '🏗️ Rebuilding and Starting...' && \
    docker compose up -d --build --force-recreate && \
    echo '✨ Applying migrations...' && \
    docker compose exec backend python manage.py migrate"

echo "✅ Deployment Complete! The system has been completely rebuilt."
