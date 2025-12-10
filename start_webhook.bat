@echo off
REM Start the webhook server for receiving newsletter emails
REM This should run alongside the Streamlit dashboard

echo Starting Competitor Agent Webhook Server...
echo.
echo Configure CloudMailin to POST to: http://YOUR_DOMAIN:8001/email
echo.

cd /d "%~dp0"
python -m app.webhook_server

pause
