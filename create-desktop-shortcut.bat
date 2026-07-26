@echo off
setlocal
cd /d "%~dp0"
set "POS_SHORTCUT_TARGET=%~dp0start-server.bat"
set "POS_SHORTCUT_WORKDIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop=[Environment]::GetFolderPath('Desktop');$shell=New-Object -ComObject WScript.Shell;$shortcut=$shell.CreateShortcut((Join-Path $desktop 'Saengngam POS 2.1.lnk'));$shortcut.TargetPath=$env:POS_SHORTCUT_TARGET;$shortcut.WorkingDirectory=$env:POS_SHORTCUT_WORKDIR;$shortcut.Description='Start Saengngam Minimart POS 2.1 desktop launcher';$shortcut.Save()"
if errorlevel 1 goto failed

echo Desktop shortcut created: Saengngam POS 2.1
pause
exit /b 0

:failed
echo ERROR: Desktop shortcut could not be created.
pause
exit /b 1
