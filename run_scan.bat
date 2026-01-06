@echo off
title Competitor Agent - Manual Scan
cd /d "%~dp0"

echo ============================================
echo   Competitor Agent - Manual Scan
echo ============================================
echo.
echo Starting scan at %date% %time%
echo.

:: Activate virtual environment and run scan
call .venv\Scripts\activate
python -m jobs.daily_scan

echo.
echo ============================================
echo   Scan Complete
echo ============================================
echo.
pause
