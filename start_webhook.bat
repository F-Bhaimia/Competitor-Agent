@echo off
title Competitor Agent Webhook Server
cd /d "%~dp0"

echo ============================================
echo   Competitor Agent Webhook Server
echo ============================================
echo.

:: Kill any existing process on port 8001
echo Stopping any existing webhook server...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8001 ^| findstr LISTENING') do (
    echo Killing process %%a on port 8001
    taskkill /F /PID %%a >nul 2>&1
)

:: Brief pause to ensure port is released
timeout /t 2 /nobreak >nul

echo.
echo Starting webhook server...
echo Configure CloudMailin to POST to: http://YOUR_DOMAIN:8001/email
echo.

python -m app.webhook_server

pause
