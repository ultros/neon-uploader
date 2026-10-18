@echo off
setlocal
cd /d "%~dp0"
call "%~dp0neon-client.bat" -Browse %*
