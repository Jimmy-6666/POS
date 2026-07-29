@echo off
setlocal
cd /d "%~dp0"
set "POS_PORT=8002"
set "POS_RUNTIME_ROOT=%~dp0runtime"
set "POS_BIND_HOST=0.0.0.0"
set "POS_SERVER_IP=192.168.0.200"
set "POS_LAN_ACCESS_ENABLED=1"
set "POS_LAN_NETWORKS=192.168.0.0/24"
set "POS_APP_VERSION=3.0.4"
set "POS_PYTHON=.venv\Scripts\python.exe"
if exist "%POS_PYTHON%" goto run
set "POS_PYTHON=..\thai-minimart-pos\.venv\Scripts\python.exe"
if exist "%POS_PYTHON%" goto run
echo ERROR: Python environment was not found. Run install-pos.bat in the original app first.
pause
exit /b 1
:run
echo Saengngam POS - Release 3.0.4
echo Server: http://127.0.0.1:8002
echo Other POS/iPad: http://192.168.0.200:8002
"%POS_PYTHON%" -m pos_app.launcher
if errorlevel 1 pause
exit /b %errorlevel%
