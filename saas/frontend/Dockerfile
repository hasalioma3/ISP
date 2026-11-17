# ISP Cloud master UI. Build context is the REPO ROOT so the ISP billing
# app's Savanna components can be copied in read-only:
#   docker build -f saas/frontend/Dockerfile .
FROM node:18-alpine AS build
WORKDIR /app
COPY saas/frontend/package*.json ./
RUN npm ci --no-audit --no-fund --fetch-retries=6 --fetch-retry-mintimeout=20000 --fetch-timeout=120000
COPY frontend/src /app/isp-frontend/src
COPY frontend/tailwind.config.js /app/isp-frontend/tailwind.config.js
COPY saas/frontend/ /app/
ENV ISP_FRONTEND_DIR=/app/isp-frontend
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY saas/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80 443
