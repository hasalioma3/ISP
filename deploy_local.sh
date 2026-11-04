#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

WITH_WORKERS=0
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf 'Usage: ./deploy_local.sh [--with-workers]\n'
    printf 'Celery workers are opt-in because scheduled tasks may contact configured routers.\n'
    exit 0
elif [[ "${1:-}" == "--with-workers" ]]; then
    WITH_WORKERS=1
elif [[ -n "${1:-}" ]]; then
    printf 'Unknown option: %s\nUsage: ./deploy_local.sh [--with-workers]\n' "$1" >&2
    exit 2
fi

ENV_FILE="${ISP_LOCAL_ENV_FILE:-.env.local}"
if [[ ! -f "$ENV_FILE" ]]; then
    cp .env.local.example "$ENV_FILE"
    printf 'Created %s from the local sandbox template. Review it, then rerun this script.\n' "$ENV_FILE"
    exit 0
fi

MPESA_ENVIRONMENT_COUNT="$(grep -Ec '^[[:space:]]*MPESA_ENVIRONMENT[[:space:]]*=' "$ENV_FILE" || true)"
if [[ "$MPESA_ENVIRONMENT_COUNT" != "1" ]] || ! grep -Eq '^[[:space:]]*MPESA_ENVIRONMENT[[:space:]]*=[[:space:]]*sandbox([[:space:]]*(#.*)?)?$' "$ENV_FILE"; then
    printf 'Refusing local deploy: %s must set MPESA_ENVIRONMENT=sandbox.\n' "$ENV_FILE" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    printf 'Docker is unavailable. Start Docker Desktop and retry.\n' >&2
    exit 1
fi

export ISP_ENV_FILE="$ENV_FILE"
export ISP_COMPOSE_NAME=isp-local
export ISP_BACKEND_PORT=8000
export ISP_HTTP_PORT=80
export ISP_HTTPS_PORT=443
export ISP_POSTGRES_VOLUME=isp_local_postgres_data
export ISP_STATIC_VOLUME=isp_local_static_volume
export ISP_MEDIA_VOLUME=isp_local_media_volume
export ISP_WHATSAPP_VOLUME=isp_local_whatsapp_session
export ISP_GENIEACS_VOLUME=isp_local_genieacs_mongo_data
export ISP_SHARED_NETWORK=isp-local_shared_network

COMPOSE=(docker compose --env-file "$ENV_FILE" --project-name isp-local -f docker-compose.yml)

docker volume create "$ISP_POSTGRES_VOLUME" >/dev/null
docker volume create "$ISP_STATIC_VOLUME" >/dev/null
docker volume create "$ISP_MEDIA_VOLUME" >/dev/null
docker volume create "$ISP_WHATSAPP_VOLUME" >/dev/null
docker volume create "$ISP_GENIEACS_VOLUME" >/dev/null

printf 'Building and starting the isolated local web stack...\n'
"${COMPOSE[@]}" up -d --build db redis backend frontend

printf 'Waiting for local PostgreSQL...\n'
for attempt in {1..30}; do
    if "${COMPOSE[@]}" exec -T db pg_isready -q; then
        break
    fi
    if [[ "$attempt" -eq 30 ]]; then
        printf 'PostgreSQL did not become ready.\n' >&2
        exit 1
    fi
    sleep 2
done

printf 'Applying database migrations...\n'
"${COMPOSE[@]}" exec -T backend python manage.py migrate
"${COMPOSE[@]}" exec -T backend python manage.py check

if [[ "$WITH_WORKERS" -eq 1 ]]; then
    printf 'Starting background workers. Scheduled tasks may contact routers configured in the local database.\n'
    "${COMPOSE[@]}" up -d --build celery_worker celery_beat whatsapp_service
fi

printf '\nLocal test stack is ready.\n'
printf 'Portal:  https://localhost (accept the local certificate warning)\n'
printf 'Backend: http://localhost:%s\n' "$ISP_BACKEND_PORT"
printf 'Create local admin: docker compose --env-file %s -p isp-local exec backend python manage.py createsuperuser\n' "$ENV_FILE"
printf 'Stop containers without deleting local data: docker compose --env-file %s -p isp-local stop\n' "$ENV_FILE"
"${COMPOSE[@]}" ps
