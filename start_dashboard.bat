@echo off
title Competitor Analysis Dashboard
cd /d "%~dp0"

echo ============================================
echo   Competitor Analysis Dashboard Launcher
echo ============================================
echo.

:: Kill any existing Streamlit processes
echo Stopping any running Streamlit sessions...
taskkill /F /IM "streamlit.exe" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq streamlit*" >nul 2>&1

:: Also kill Python processes running streamlit (more thorough)
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%streamlit%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%i >nul 2>&1
)

:: Brief pause to ensure ports are released
timeout /t 2 /nobreak >nul

echo.
echo Starting new dashboard session...
echo.
echo Dashboard will open at: http://localhost:8501
echo Press Ctrl+C to stop the server.
echo ============================================
echo.

:: Start Streamlit
python -m streamlit run streamlit_app/Home.py --server.port 8501

:: If we get here, Streamlit was stopped
echo.
echo Dashboard stopped.
pause
