@echo off
setlocal
echo Starting ISP Billing System Development Environment...

:: Get the directory where this script is located
set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"

echo Project Root: %PROJECT_ROOT%

:: --- Check for Dependencies ---
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Node.js npm is not installed or not in PATH.
    echo Frontend setup and launch will be skipped.
    set "SKIP_FRONTEND=true"
) else (
    set "SKIP_FRONTEND=false"
)

:: --- Backend Setup ---
echo [Setup] Checking Backend...
cd "%BACKEND_DIR%"

if not exist "venv" (
    echo [Setup] Creating virtual environment...
    python -m venv venv
)

:: Upgrade pip first
echo [Setup] Upgrading pip...
"%BACKEND_DIR%\venv\Scripts\python" -m pip install --upgrade pip

echo [Setup] Installing/Updating Python dependencies...
"%BACKEND_DIR%\venv\Scripts\python" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies.
    echo [TIP] If you see a "Fatal error in launcher", your virtual environment might be corrupted.
    echo        Try deleting the 'backend\venv' folder and running this script again.
    echo.
    echo [TIP] If you see "postgres" or "psycopg2" errors:
    echo        1. Ensure you have installed PostgreSQL.
    echo        2. Try installing 'psycopg2' instead of 'psycopg2-binary' in requirements.txt
    pause
    exit /b 1
)

:: --- Frontend Setup ---
if "%SKIP_FRONTEND%"=="false" (
    echo [Setup] Checking Frontend...
    cd "%FRONTEND_DIR%"
    
    if not exist "node_modules" (
        echo [Setup] Installing Node.js dependencies...
        call npm install
    )
)

:: --- Launch Services ---
echo [Launch] Starting Services...

:: 1. Backend Server
echo Starting Django Backend...
start "Django Backend" /D "%BACKEND_DIR%" cmd /k "call venv\Scripts\activate && python manage.py runserver 0.0.0.0:8000"

:: 2. Celery Worker
echo Starting Celery Worker...
start "Celery Worker" /D "%BACKEND_DIR%" cmd /k "call venv\Scripts\activate && celery -A isp_billing worker -l info --pool=solo"

:: 3. Celery Beat
echo Starting Celery Beat...
start "Celery Beat" /D "%BACKEND_DIR%" cmd /k "call venv\Scripts\activate && celery -A isp_billing beat -l info"

:: 4. Frontend
if "%SKIP_FRONTEND%"=="false" (
    echo Starting React Frontend...
    start "React Frontend" /D "%FRONTEND_DIR%" cmd /k "npm run dev"
) else (
    echo [INFO] Skipping Frontend launch because npm was not found.
)

echo All available services launch commands issued.
endlocal
