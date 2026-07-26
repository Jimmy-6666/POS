@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto path_error

set "POS_PYTHON=.venv\Scripts\python.exe"
if not exist "%POS_PYTHON%" goto venv_missing

"%POS_PYTHON%" -c "import flask, waitress" >nul 2>&1
if errorlevel 1 goto dependencies_missing

"%POS_PYTHON%" -m pos_app.launcher
if errorlevel 1 goto server_error
goto end

:path_error
echo ERROR: Cannot open the POS project directory.
goto failed

:venv_missing
echo ERROR: The virtual environment was not found.
echo Run: python -m venv .venv
echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
goto failed

:dependencies_missing
echo ERROR: Required Python packages are not installed.
echo Run: .venv\Scripts\python.exe -m pip install -r requirements.txt
goto failed

:server_error
echo ERROR: The POS server could not start.
goto failed

:failed
echo See README.md for troubleshooting instructions.
pause
exit /b 1

:end
endlocal
