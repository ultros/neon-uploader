@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 run.py %*
) else (
    python run.py %*
)
if errorlevel 1 (
    echo.
    echo Neon Uploader could not start. Review the error above.
    pause
)
