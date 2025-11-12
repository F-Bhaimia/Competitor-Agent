#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/competitor_news_monitor"   # <- adjust to your path on Vultr
VENV_DIR="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"
cd "$APP_DIR"

# Activate venv
source "$VENV_DIR/bin/activate"

# Env for OpenAI (or put in systemd unit Environment=)
# export OPENAI_API_KEY=...

# Run coordinator (default since=yesterday)
python -m jobs.update_daily >> "$LOG_DIR/update_daily.log" 2>&1
