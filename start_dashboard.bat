@echo off
title Competitor Analysis Dashboard
cd /d "%~dp0"

echo ============================================
echo   Competitor Analysis Dashboard Launcher
echo ============================================
echo.

:: Kill any existing processes on our ports
echo Stopping any running services...

:: Kill process on port 8501 (dashboard)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501 ^| findstr LISTENING') do (
    echo Killing dashboard process %%a
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill process on port 8001 (webhook)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8001 ^| findstr LISTENING') do (
    echo Killing webhook process %%a
    taskkill /F /PID %%a >nul 2>&1
)

:: Brief pause to ensure ports are released
timeout /t 2 /nobreak >nul

:: Ensure logs directory exists
if not exist logs mkdir logs

echo.
echo Starting services...
echo.

:: Start webhook server in background
echo Starting webhook server on port 8001...
start /b python -m app.webhook_server > logs\webhook.log 2>&1

:: Brief pause for webhook to start
timeout /t 2 /nobreak >nul

echo Starting dashboard on port 8501...
echo.
echo ============================================
echo   Dashboard:  http://localhost:8501
echo   Webhook:    http://localhost:8001/email
echo ============================================
echo.
echo Press Ctrl+C to stop all services.
echo.

:: Start Streamlit (foreground - will block)
python -m streamlit run streamlit_app/Home.py --server.port 8501

:: If we get here, Streamlit was stopped - also stop webhook
echo.
echo Stopping webhook server...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8001 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo All services stopped.
pause
