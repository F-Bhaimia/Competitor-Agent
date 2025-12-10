#!/bin/bash
# Stop Competitor Analysis Dashboard and Webhook Server
# Usage: ./stop_dashboard.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping Competitor Analysis services..."
echo ""

# Try to stop using saved PIDs first
if [ -f "logs/dashboard.pid" ]; then
    PID=$(cat logs/dashboard.pid)
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping dashboard (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    rm -f logs/dashboard.pid
fi

if [ -f "logs/webhook.pid" ]; then
    PID=$(cat logs/webhook.pid)
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping webhook server (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    rm -f logs/webhook.pid
fi

# Also kill by process name as fallback
pkill -f "streamlit.*Home.py" 2>/dev/null || true
pkill -f "app.webhook_server" 2>/dev/null || true

echo ""
echo "All services stopped."
