#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

mkdir -p logs
TS="$(date -u +'%Y%m%d_%H%M%S')"
LOG="logs/pipeline_${TS}.log"

# prevent overlapping runs
LOCK="/tmp/ms_competitor_pipeline.lock"
exec 9>"$LOCK"
flock -n 9 || { echo "Another run is in progress" | tee -a "$LOG"; exit 0; }

# env
if [ -d .venv ]; then source .venv/bin/activate; fi
export PYTHONUNBUFFERED=1
[ -f .env ] && set -a && source .env && set +a

echo "=== $(date -u) :: START ===" | tee -a "$LOG"
python -m jobs.fetch_rss        2>&1 | tee -a "$LOG"
python -m jobs.enrich_updates   2>&1 | tee -a "$LOG"
echo "=== $(date -u) :: DONE ==="  | tee -a "$LOG"

# keep last 15 logs
ls -1t logs/pipeline_*.log | tail -n +16 | xargs -r rm -f
