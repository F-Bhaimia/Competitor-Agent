#!/bin/bash
# Start Competitor Analysis Dashboard and Webhook Server
# Usage: ./start_dashboard.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Competitor Analysis Dashboard Launcher"
echo "============================================"
echo ""

# Create logs directory if it doesn't exist
mkdir -p logs

# Stop any existing processes
echo "Stopping any running services..."
pkill -f "streamlit.*Home.py" 2>/dev/null || true
pkill -f "app.webhook_server" 2>/dev/null || true
sleep 2

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo ""
echo "Starting services..."
echo ""

# Start webhook server in background
echo "Starting webhook server on port 8001..."
nohup python -m app.webhook_server > logs/webhook.log 2>&1 &
WEBHOOK_PID=$!
echo "Webhook PID: $WEBHOOK_PID"

sleep 1

# Start Streamlit dashboard in background
echo "Starting dashboard on port 8501..."
nohup python -m streamlit run streamlit_app/Home.py --server.port 8501 > logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "Dashboard PID: $DASHBOARD_PID"

# Save PIDs for stop script
echo "$WEBHOOK_PID" > logs/webhook.pid
echo "$DASHBOARD_PID" > logs/dashboard.pid

echo ""
echo "============================================"
echo "  Dashboard:  http://localhost:8501"
echo "  Webhook:    http://localhost:8001/email"
echo "============================================"
echo ""
echo "Services started in background."
echo "Logs: logs/dashboard.log, logs/webhook.log"
echo "Run ./stop_dashboard.sh to stop all services."
echo ""
