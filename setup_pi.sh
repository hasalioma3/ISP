#!/bin/bash

# isp_billing setup script for Raspberry Pi
# Run this script on the Pi after copying the files

set -e

echo "[Setup] Updating system packages..."
sudo apt-get update

echo "[Setup] Installing system dependencies..."
sudo apt-get install -y python3-venv python3-pip python3-dev libpq-dev postgresql postgresql-contrib redis-server nginx git curl lsof

# Troubleshooting: Check/Kill process on port 80
if sudo lsof -i :80; then
    echo "[WARNING] Port 80 is in use. Attempting to free it..."
    
    # Check if it's docker
    if sudo ps aux | grep -v grep | grep "docker"; then
         echo "[Setup] Stopping Docker Service (Force)..."
         sudo systemctl stop docker.socket
         sudo systemctl stop docker.service
         # Stop all running containers to free ports
         sudo docker stop $(sudo docker ps -q) 2>/dev/null || true
    fi
    # Stop apache/nginx if running
    sudo systemctl stop apache2 || true
    sudo systemctl stop nginx || true
    
    # Final check
    sudo fuser -k 80/tcp || true
fi

# Troubleshooting: List directory to confirm extraction
ls -la

# Install Node.js 18.x
if ! command -v node &> /dev/null; then
    echo "[Setup] Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

echo "[Setup] Configuring PostgreSQL..."
# Check if database exists, if not create it
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'isp_billing'" | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE isp_billing;"
# Check if user exists, if not create it (password: isp_password)
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname = 'isp_user'" | grep -q 1 || sudo -u postgres psql -c "CREATE USER isp_user WITH PASSWORD 'isp_password';"
# Grant privileges
sudo -u postgres psql -c "ALTER ROLE isp_user SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE isp_user SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE isp_user SET timezone TO 'Africa/Nairobi';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE isp_billing TO isp_user;"
# Fix for Postgres 15+ ownership/schema permissions
sudo -u postgres psql -d isp_billing -c "GRANT ALL ON SCHEMA public TO isp_user;"

echo "[Setup] Setting up Backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
# Install requirements (using psycopg2-binary for simplicity, or build from source since we have libpq-dev)
pip install -r requirements.txt
pip install gunicorn

# Migrate database
# Note: Use env vars for DB connection
export DATABASE_URL=postgresql://isp_user:isp_password@localhost/isp_billing
python3 manage.py migrate
python3 manage.py collectstatic --noinput

echo "[Setup] Setting up Frontend..."
cd ../frontend
npm install
npm run build

echo "[Setup] Configuring Systemd Services..."
cd ..
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable isp-backend
sudo systemctl enable isp-worker
sudo systemctl enable isp-beat
sudo systemctl restart isp-backend
sudo systemctl restart isp-worker
sudo systemctl restart isp-beat

echo "[Setup] Configuring Nginx..."
sudo cp nginx/isp_billing.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/isp_billing.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "[Setup] Deployment Complete!"
echo "Access the system at http://192.168.88.11"
