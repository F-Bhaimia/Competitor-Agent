#!/usr/bin/env bash
# update_daily.sh - Daily crawl and enrichment job
# Runs via cron to fetch competitor updates and enrich with AI
set -euo pipefail

APP_DIR="/opt/competitor-agent"
VENV_DIR="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
LOCK_FILE="/tmp/competitor-agent-daily.lock"

# Ensure directories exist
mkdir -p "$LOG_DIR"
cd "$APP_DIR"

# Prevent overlapping runs
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S')] Another update is already running, skipping..." >> "$LOG_DIR/update_daily.log"
    exit 0
fi

# Activate virtual environment
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S')] ERROR: Virtual environment not found at $VENV_DIR" >> "$LOG_DIR/update_daily.log"
    exit 1
fi

# Load environment variables
if [ -f "$APP_DIR/.env" ]; then
    set -a
    source "$APP_DIR/.env"
    set +a
fi

# Run the daily update pipeline
echo "[$(date -u +'%Y-%m-%d %H:%M:%S')] Starting daily update..." >> "$LOG_DIR/update_daily.log"
python -m jobs.update_daily >> "$LOG_DIR/update_daily.log" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S')] Daily update completed successfully" >> "$LOG_DIR/update_daily.log"
else
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S')] Daily update failed with exit code $EXIT_CODE" >> "$LOG_DIR/update_daily.log"
fi

# Keep last 30 days of logs (rotate by truncating old entries)
if [ -f "$LOG_DIR/update_daily.log" ]; then
    tail -n 10000 "$LOG_DIR/update_daily.log" > "$LOG_DIR/update_daily.log.tmp" 2>/dev/null || true
    mv "$LOG_DIR/update_daily.log.tmp" "$LOG_DIR/update_daily.log" 2>/dev/null || true
fi

exit $EXIT_CODE
