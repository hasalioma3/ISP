@echo off
setlocal
echo Deploying ISP Billing System Locally (Docker Desktop)...

:: 1. Shared Infrastructure (DB + Redis)
echo [1/4] Starting Shared Infrastrucure...
docker network create isp_network 2>nul
:: Ensure network exists (ignore 'already exists')

:: Redis
docker run -d --name isp-redis --network isp_network -p 6379:6379 --restart always redis:alpine 2>nul
if %errorlevel% neq 0 echo Redis container might already be running (ignoring error).

:: Postgres
docker run -d --name isp-db --network isp_network -p 5432:5432 --restart always -e POSTGRES_PASSWORD=isp_password postgres:15-alpine 2>nul
if %errorlevel% neq 0 (
    echo Postgres container might already be running.
) else (
    echo Waiting for DB to initialize...
    timeout /t 5 >nul
    :: Setup isp_user
    echo Creating/Updating isp_user permissions...
    docker exec -i isp-db psql -U postgres -c "CREATE USER isp_user WITH PASSWORD 'isp_password';" 2>nul
    docker exec -i isp-db psql -U postgres -c "ALTER ROLE isp_user WITH CREATEDB CREATEROLE;"
)

:: 2. Build Core Image
echo [2/4] Building ISP Core Image...
docker build -f backend/Dockerfile -t isp_core:latest .

:: 3. Build Manager Image
echo [3/4] Building Manager App Image...
docker build -f manager/Dockerfile -t isp_manager:latest manager/

:: 4. Start Manager
echo [4/4] Starting Manager App...
docker stop isp-manager 2>nul
docker rm isp-manager 2>nul

:: Note: We use 'host.docker.internal' so the manager (in container) can talk to Postgres (on host port 5432 or mapped)
:: We map docker.sock so manager can spawn siblings.
docker run -d ^
  --name isp-manager ^
  --network isp_network ^
  -p 8501:8501 ^
  --restart always ^
  -v //var/run/docker.sock:/var/run/docker.sock ^
  -e HOST_IP=localhost ^
  -e DOCKER_GATEWAY=host.docker.internal ^
  -e DB_HOST=isp-db ^
  -e DB_USER=isp_user ^
  -e DB_PASSWORD=isp_password ^
  isp_manager:latest

echo. 
echo [SUCCESS] Manager is running at http://localhost:8501
echo.
endlocal
