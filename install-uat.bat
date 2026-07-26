@echo off
setlocal
cd /d "%~dp0"
echo Installing Saengngam Minimart POS 2.0 UAT...
set "POS_RUNTIME_ROOT=%~dp0uat_runtime"
where python >nul 2>&1
if errorlevel 1 goto python_missing
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" seed_uat.py
if errorlevel 1 goto failed
echo.
echo UAT installation complete.
echo Start with start-uat.bat and open http://127.0.0.1:8001
echo Demo PINs: Admin 1234, Manager 2222, Cashier 3333
pause
exit /b 0
:python_missing
echo ERROR: Python 3.11 or newer was not found.
goto failed
:failed
echo ERROR: UAT installation did not complete. See FIRST_INSTALLATION.md.
pause
exit /b 1
