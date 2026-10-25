# Built once, run as three separate services (cwmp/nbi/fs) in docker-compose.yml
# via different `command:` overrides -- same pattern already used for
# backend/celery_worker/celery_beat sharing one build in this same compose
# file. Installed from the official npm package (not a third-party Docker
# Hub image) since this handles real customer CPE devices.
FROM node:20-alpine

# Pin an exact version -- never a floating tag, this talks to customer
# devices in the field.
RUN npm install -g genieacs@1.2.16

# Extension scripts directory GenieACS expects to exist (provision
# scripts/virtual parameters live here later, if needed).
RUN mkdir -p /opt/genieacs/ext

WORKDIR /opt/genieacs
