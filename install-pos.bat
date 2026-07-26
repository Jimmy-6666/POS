@echo off
setlocal
cd /d "%~dp0"
echo Installing Saengngam Minimart POS 2.0 Production...
where python >nul 2>&1
if errorlevel 1 goto python_missing
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "from pos_app import create_app; create_app()"
if errorlevel 1 goto failed
echo.
echo Installation complete.
echo Start with start-pos.bat and open http://127.0.0.1:8000
echo Initial administrator PIN: 1234
pause
exit /b 0
:python_missing
echo ERROR: Python 3.11 or newer was not found.
echo Install Python from python.org and enable Add Python to PATH.
goto failed
:failed
echo ERROR: Installation did not complete. See FIRST_INSTALLATION.md.
pause
exit /b 1
