#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting ISP Billing System Development Environment...${NC}"

# Kill all child processes on script exit
trap 'kill 0' SIGINT SIGTERM EXIT

# 1. Backend Server
echo -e "${GREEN}[1/4] Starting Django Backend...${NC}"
(
    cd backend
    source venv/bin/activate
    python manage.py runserver 0.0.0.0:8000
) &
BACKEND_PID=$!

# 2. Celery Worker
echo -e "${GREEN}[2/4] Starting Celery Worker...${NC}"
(
    cd backend
    source venv/bin/activate
    celery -A isp_billing worker -l info
) &
WORKER_PID=$!

# 3. Celery Beat
echo -e "${GREEN}[3/4] Starting Celery Beat...${NC}"
(
    cd backend
    source venv/bin/activate
    celery -A isp_billing beat -l info
) &
BEAT_PID=$!

# 4. Frontend
echo -e "${GREEN}[4/4] Starting React Frontend...${NC}"
(
    cd frontend
    npm run dev
) &
FRONTEND_PID=$!

# Wait for all processes
wait
