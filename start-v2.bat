@echo off
setlocal
cd /d "%~dp0"
set "POS_PORT=8002"
set "POS_RUNTIME_ROOT=%~dp0runtime"
set "POS_PYTHON=.venv\Scripts\python.exe"
if exist "%POS_PYTHON%" goto run
set "POS_PYTHON=..\thai-minimart-pos\.venv\Scripts\python.exe"
if exist "%POS_PYTHON%" goto run
echo ERROR: Python environment was not found. Run install-pos.bat in the original app first.
pause
exit /b 1
:run
echo Thai Minimart POS - Release 2
echo Open: http://127.0.0.1:8002
"%POS_PYTHON%" -m pos_app.launcher
if errorlevel 1 pause
exit /b %errorlevel%
