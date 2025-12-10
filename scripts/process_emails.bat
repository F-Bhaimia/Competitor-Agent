@echo off
REM Process received newsletter emails and add to updates.csv

echo Processing newsletter emails...
echo.

cd /d "%~dp0.."
python -m jobs.process_emails

pause
