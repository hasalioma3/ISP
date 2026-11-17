#!/bin/bash
# Builds the images every ISP instance runs, from the ISP billing app in
# this repo (../backend, ../frontend, ../whatsapp-service) -- unchanged, using
# its own Dockerfiles. Each build gets a clean copy of just what it needs, so
# venv/node_modules/db files never go into the build context.
#
#   ./saas/build_tenant_images.sh [tag]      (default tag: latest)
#
# New sign-ups get SAAS_IMAGE_TAG; to move existing ISPs to a new build,
# use "Re-apply config" on the tenant (or set its image tag) in the master app.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:-latest}"
PREFIX="${SAAS_IMAGE_PREFIX:-isp-saas/tenant-}"
CTX="$(mktemp -d)"
trap 'rm -rf "$CTX"' EXIT

echo "==> backend"
# Excludes are anchored (leading /) so only the top-level dirs match --
# an unanchored "backups" would also drop apps/backups.
rsync -a --delete --exclude /venv --exclude '__pycache__' --exclude /db.sqlite3 --exclude '/logs/*' \
      --exclude /mediafiles --exclude /staticfiles --exclude /backups --exclude '/.env*' backend/ "$CTX/backend/"
docker build -t "${PREFIX}backend:${TAG}" "$CTX/backend"

echo "==> frontend"
mkdir -p "$CTX/fe"
rsync -a --delete --exclude /node_modules --exclude /dist --exclude '/.env*' frontend/ "$CTX/fe/frontend/"
rsync -a nginx/default.conf "$CTX/fe/nginx/"
docker build -t "${PREFIX}frontend:${TAG}" -f "$CTX/fe/frontend/Dockerfile" \
       --build-arg VITE_API_URL=/api --build-arg VITE_DEFAULT_PORTAL_URL= "$CTX/fe"

echo "==> whatsapp"
rsync -a --delete --exclude /node_modules --exclude /auth whatsapp-service/ "$CTX/whatsapp/"
docker build -t "${PREFIX}whatsapp:${TAG}" "$CTX/whatsapp"

echo "Built ${PREFIX}{backend,frontend,whatsapp}:${TAG}"
