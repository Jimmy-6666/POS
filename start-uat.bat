@echo off
setlocal
cd /d "%~dp0"

set "POS_PORT=8001"
set "POS_RUNTIME_ROOT=%~dp0uat_runtime"
set "LINE_LIFF_ID=2010868041-LtumrXtt"
set "LINE_LOGIN_CHANNEL_ID=2010868041"
set "APP_BASE_URL=https://online.raisanngam.com"
set "POS_TRUST_PROXY=1"
set "POS_DISPLAY_STATE_FILE=%POS_RUNTIME_ROOT%\display_state.json"
set "POS_LAUNCHER_TITLE=Saengngam POS 2.4.2 UAT"
set "POS_LAUNCHER_MUTEX=SaengngamPOS242DesktopLauncherUAT"
set "POS_PYTHONW=%~dp0.venv\Scripts\pythonw.exe"

if not exist "%POS_PYTHONW%" goto missing

start "" "%POS_PYTHONW%" "%~dp0pos_desktop.py"
exit /b 0

:missing
echo ERROR: Python environment was not found. Run install-uat.bat first.
pause
exit /b 1
