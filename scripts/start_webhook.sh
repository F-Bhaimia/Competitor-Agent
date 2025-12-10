#!/bin/bash
# Start the webhook server for receiving newsletter emails
# This should run alongside the Streamlit dashboard

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting Competitor Agent Webhook Server..."
echo ""
echo "Configure CloudMailin to POST to: http://YOUR_DOMAIN:8001/email"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

python -m app.webhook_server
