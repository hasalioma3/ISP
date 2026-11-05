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

PI_HOST="192.168.58.252"
# PI_HOST="192.168.56.117"
PI_USER="pi"
REMOTE_DIR="~/ISP"

echo "🔄 Updating Raspberry Pi ($PI_HOST)..."

# 1. Sync Files
#
# --delete removes files on the Pi that no longer exist locally (e.g. a
# renamed/deleted migration file) -- without it, a deleted file just sits
# on the Pi forever, which is exactly what caused a migration-graph
# conflict (two divergent migration chains, old + new) on a prior deploy.
# Every path below is excluded for the opposite reason: they're Pi-only or
# gitignored (.env.prod etc, generated per-company secrets) and must never
# be touched by --delete, since they don't exist in the local source tree
# to protect them -- plain --exclude keeps them untouched on both the copy
# and the delete pass.
echo "📦 Syncing files..."
rsync -avz --delete --progress \
    --exclude 'node_modules' --exclude '.git' --exclude '__pycache__' \
    --exclude '.env' --exclude '.env.prod' --exclude 'backend/.env' --exclude 'frontend/.env' \
    --exclude 'companies/*.env' --exclude 'vps' --exclude 'teststk.py' \
    ./ ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# 2. Remote Commands
echo "🔧 Running update script on the Pi..."
set +e
ssh ${PI_USER}@${PI_HOST} "bash ${REMOTE_DIR}/update_on_pi.sh"
DEPLOY_EXIT=$?
set -e

if [ "$DEPLOY_EXIT" -ne 0 ]; then
    echo "❌ Update failed (exit ${DEPLOY_EXIT})."
    exit "$DEPLOY_EXIT"
fi

echo "✅ Update complete!"
