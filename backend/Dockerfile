# Stage 1: Build Frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

# Stage 2: Build Backend
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WORKDIR=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    netcat-openbsd \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN pip install gunicorn whitenoise

# Copy backend code
COPY backend /app/

# Copy built frontend assets to staticfiles directory for Whitenoise to serve
COPY --from=frontend-builder /app/frontend/dist /app/frontend_dist
RUN ls -R /app/frontend_dist

# Copy entrypoint
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Create directory for static collection
RUN mkdir -p /app/staticfiles

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "isp_billing.wsgi:application", "--bind", "0.0.0.0:8000"]
