@echo off
title Stop Competitor Analysis Services
cd /d "%~dp0"

echo Stopping Competitor Analysis services...
echo.

:: Kill Streamlit processes
echo Stopping dashboard...
taskkill /F /IM "streamlit.exe" >nul 2>&1
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%streamlit%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%i >nul 2>&1
)

:: Kill webhook server processes
echo Stopping webhook server...
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%webhook_server%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%i >nul 2>&1
)

echo.
echo All services stopped.
pause
