# ISP Cloud master app (API, Celery worker and beat share this image).
# Build context is the REPO ROOT, so the few ISP-app modules it imports
# can be copied in read-only:
#   docker build -f saas/backend/Dockerfile .
FROM docker:27-cli AS dockercli

FROM python:3.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# The worker drives tenant stacks through the host's Docker socket.
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
RUN apt-get update && apt-get install -y --no-install-recommends netcat-openbsd && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY saas/backend/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Imported from the ISP billing app (see ISP_BACKEND_DIR in settings.py).
COPY backend/apps/__init__.py /isp_backend/apps/__init__.py
COPY backend/apps/notifications/__init__.py backend/apps/notifications/fields.py /isp_backend/apps/notifications/

COPY saas/backend/ /app/
COPY saas/tenant/ /app/tenant/
RUN chmod +x /app/entrypoint.sh

ENV ISP_BACKEND_DIR=/isp_backend \
    SAAS_TENANT_COMPOSE_FILE=/app/tenant/docker-compose.tenant.yml \
    SAAS_DATA_DIR=/data
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "saas_master.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4"]
