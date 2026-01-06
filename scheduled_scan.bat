@echo off
:: Scheduled Scan - runs silently for Task Scheduler
cd /d "%~dp0"

:: Log start time
echo [%date% %time%] Starting scheduled scan >> logs\scheduled_scan.log

:: Activate virtual environment and run scan
call .venv\Scripts\activate
python -m jobs.daily_scan >> logs\scheduled_scan.log 2>&1

:: Log completion
echo [%date% %time%] Scan completed >> logs\scheduled_scan.log
echo. >> logs\scheduled_scan.log
