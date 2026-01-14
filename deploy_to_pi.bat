@echo off
setlocal
echo Deploying ISP Billing to Raspberry Pi (192.168.88.11)...

set "PI_USER=pi"
set "PI_HOST=192.168.88.11"
set "TARGET_DIR=/home/pi/isp_billing"

:: Create exclusion file FIRST so xcopy can use it
echo [Deploy] Creating exclusion list...
(
echo venv\
echo __pycache__\
echo node_modules\
echo .git\
echo .env
echo db.sqlite3
) > "%PROJECT_ROOT%deploy_exclude.txt"

:: Create a temporary directory for staging
if exist temp_deploy rmdir /s /q temp_deploy
mkdir temp_deploy

:: Copy necessary files
echo [Deploy] Staging files...
xcopy /E /I /Y backend temp_deploy\backend /EXCLUDE:%PROJECT_ROOT%deploy_exclude.txt
xcopy /E /I /Y frontend temp_deploy\frontend /EXCLUDE:%PROJECT_ROOT%deploy_exclude.txt
xcopy /E /I /Y nginx temp_deploy\nginx
xcopy /E /I /Y systemd temp_deploy\systemd
copy setup_pi.sh temp_deploy\

:: Archive files (using tar on Windows if available, otherwise we might need 7-zip)
:: Assuming tar is available (standard on Win 10+)
echo [Deploy] Archiving...
cd temp_deploy
tar -czf ..\isp_billing.tar.gz *
cd ..

:: Transfer to Pi
echo [Deploy] Transferring archive to Pi...
echo (You may be asked for the password: pi)
scp isp_billing.tar.gz %PI_USER%@%PI_HOST%:/home/%PI_USER%/

:: Run setup on Pi
echo [Deploy] Extracting and running setup on Pi...
:: We use sed to strip CRLF from setup_pi.sh just in case
ssh %PI_USER%@%PI_HOST% "mkdir -p %TARGET_DIR% && tar -xzf isp_billing.tar.gz -C %TARGET_DIR% && cd %TARGET_DIR% && sed -i 's/\r$//' setup_pi.sh && chmod +x setup_pi.sh && ./setup_pi.sh"

:: Cleanup
echo [Deploy] Cleanup...
del isp_billing.tar.gz
del deploy_exclude.txt
rmdir /s /q temp_deploy

echo [Deploy] Done!
endlocal
