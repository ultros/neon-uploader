@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0neon-client.ps1" %*
if errorlevel 1 (
    echo.
    echo Neon Uploader Windows client failed. Check the error above.
    pause
)
