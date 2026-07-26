@echo off
setlocal
cd /d "%~dp0"
set "POS_PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if exist "%POS_PYTHONW%" goto run
set "POS_PYTHONW=%~dp0..\thai-minimart-pos\.venv\Scripts\pythonw.exe"
if exist "%POS_PYTHONW%" goto run
echo ERROR: Python environment was not found. Run install-pos.bat first.
pause
exit /b 1
:run
start "" "%POS_PYTHONW%" "%~dp0pos_desktop.py"
exit /b 0
