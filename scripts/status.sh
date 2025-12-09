#!/usr/bin/env bash
# status.sh - Health check and status report for Competitor News Monitor
set -euo pipefail

# Configuration
APP_DIR="/opt/competitor-agent"
VENV_DIR="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
DATA_DIR="$APP_DIR/data"
SERVICE_NAME="competitor-dashboard"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Status indicators
OK="${GREEN}●${NC}"
WARN="${YELLOW}●${NC}"
FAIL="${RED}●${NC}"

print_header() {
    echo ""
    echo -e "${BOLD}${CYAN}$1${NC}"
    echo "──────────────────────────────────────────"
}

check_service() {
    local service=$1
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        echo -e "  $OK $service is running"
        return 0
    else
        echo -e "  $FAIL $service is stopped"
        return 1
    fi
}

check_port() {
    local port=$1
    local name=$2
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        echo -e "  $OK Port $port ($name) is listening"
        return 0
    else
        echo -e "  $FAIL Port $port ($name) is not listening"
        return 1
    fi
}

check_file() {
    local file=$1
    local name=$2
    if [ -f "$file" ]; then
        local size=$(du -h "$file" 2>/dev/null | cut -f1)
        local modified=$(stat -c %y "$file" 2>/dev/null | cut -d. -f1)
        echo -e "  $OK $name: $size (modified: $modified)"
        return 0
    else
        echo -e "  $WARN $name: not found"
        return 1
    fi
}

check_dir() {
    local dir=$1
    local name=$2
    if [ -d "$dir" ]; then
        local count=$(find "$dir" -type f 2>/dev/null | wc -l)
        echo -e "  $OK $name: $count files"
        return 0
    else
        echo -e "  $FAIL $name: directory not found"
        return 1
    fi
}

# ============================================
# MAIN STATUS REPORT
# ============================================

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        COMPETITOR NEWS MONITOR - STATUS REPORT               ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Generated: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Hostname:  $(hostname)"

# ============================================
# VERSION INFO
# ============================================
print_header "VERSION INFO"

if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    echo "  Branch:  $(git branch --show-current 2>/dev/null || echo 'unknown')"
    echo "  Commit:  $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
    echo "  Date:    $(git log -1 --format='%ci' 2>/dev/null || echo 'unknown')"

    # Check if up to date with remote
    git fetch origin --quiet 2>/dev/null || true
    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "")

    if [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
        BEHIND=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo "?")
        echo -e "  Status:  ${YELLOW}$BEHIND commits behind origin/main${NC}"
    else
        echo -e "  Status:  ${GREEN}Up to date${NC}"
    fi
else
    echo "  Git repository not found"
fi

# ============================================
# SERVICES
# ============================================
print_header "SERVICES"

SERVICES_OK=true
check_service "$SERVICE_NAME" || SERVICES_OK=false
check_service "nginx" || SERVICES_OK=false

# ============================================
# NETWORK
# ============================================
print_header "NETWORK"

check_port 8501 "Streamlit"
check_port 80 "HTTP"
check_port 443 "HTTPS" || true  # Optional, don't fail

# Get server IP
SERVER_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
echo ""
echo "  Dashboard URL: http://$SERVER_IP"

# ============================================
# DATA FILES
# ============================================
print_header "DATA FILES"

check_file "$DATA_DIR/updates.csv" "Raw updates"
check_file "$DATA_DIR/enriched_updates.csv" "Enriched updates"
check_file "$DATA_DIR/updates.parquet" "Parquet mirror"

# Show record counts
if [ -f "$DATA_DIR/updates.csv" ]; then
    RAW_COUNT=$(wc -l < "$DATA_DIR/updates.csv" 2>/dev/null || echo 0)
    RAW_COUNT=$((RAW_COUNT - 1))  # Subtract header
    echo "  Raw records: $RAW_COUNT"
fi

if [ -f "$DATA_DIR/enriched_updates.csv" ]; then
    ENRICHED_COUNT=$(wc -l < "$DATA_DIR/enriched_updates.csv" 2>/dev/null || echo 0)
    ENRICHED_COUNT=$((ENRICHED_COUNT - 1))  # Subtract header
    echo "  Enriched records: $ENRICHED_COUNT"
fi

# ============================================
# ENVIRONMENT
# ============================================
print_header "ENVIRONMENT"

check_dir "$VENV_DIR" "Virtual environment"
check_file "$APP_DIR/.env" "Environment file"

# Check if API key is set (without revealing it)
if [ -f "$APP_DIR/.env" ]; then
    if grep -q "OPENAI_API_KEY=sk-" "$APP_DIR/.env" 2>/dev/null; then
        echo -e "  $OK OpenAI API key configured"
    elif grep -q "OPENAI_API_KEY=your-key-here" "$APP_DIR/.env" 2>/dev/null; then
        echo -e "  $WARN OpenAI API key NOT configured (still placeholder)"
    else
        echo -e "  $WARN OpenAI API key status unknown"
    fi
fi

# ============================================
# RECENT ACTIVITY
# ============================================
print_header "RECENT ACTIVITY"

# Last crawl time
if [ -f "$LOG_DIR/update_daily.log" ]; then
    LAST_RUN=$(grep -E "Starting daily update|Daily update completed" "$LOG_DIR/update_daily.log" 2>/dev/null | tail -1 || echo "")
    if [ -n "$LAST_RUN" ]; then
        echo "  Last daily job: $LAST_RUN"
    else
        echo "  Last daily job: No recent activity found"
    fi
fi

# Pipeline logs
if ls "$LOG_DIR"/pipeline_*.log 1>/dev/null 2>&1; then
    LATEST_PIPELINE=$(ls -1t "$LOG_DIR"/pipeline_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_PIPELINE" ]; then
        PIPELINE_TIME=$(stat -c %y "$LATEST_PIPELINE" 2>/dev/null | cut -d. -f1)
        echo "  Last pipeline: $PIPELINE_TIME"
    fi
fi

# Cron job status
if crontab -l 2>/dev/null | grep -q "update_daily.sh"; then
    CRON_TIME=$(crontab -l 2>/dev/null | grep "update_daily.sh" | awk '{print $1, $2}')
    echo -e "  $OK Cron job scheduled at: $CRON_TIME (minute hour)"
else
    echo -e "  $WARN Cron job not found"
fi

# ============================================
# SYSTEM RESOURCES
# ============================================
print_header "SYSTEM RESOURCES"

# Disk usage
DISK_USAGE=$(df -h "$APP_DIR" 2>/dev/null | tail -1 | awk '{print $5}')
DISK_AVAIL=$(df -h "$APP_DIR" 2>/dev/null | tail -1 | awk '{print $4}')
echo "  Disk usage: $DISK_USAGE (${DISK_AVAIL} available)"

# Memory
MEM_TOTAL=$(free -h 2>/dev/null | awk '/^Mem:/{print $2}')
MEM_USED=$(free -h 2>/dev/null | awk '/^Mem:/{print $3}')
MEM_AVAIL=$(free -h 2>/dev/null | awk '/^Mem:/{print $7}')
echo "  Memory: $MEM_USED / $MEM_TOTAL (${MEM_AVAIL} available)"

# Load average
LOAD=$(uptime 2>/dev/null | awk -F'load average:' '{print $2}' | xargs)
echo "  Load average: $LOAD"

# App data size
if [ -d "$DATA_DIR" ]; then
    DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1)
    echo "  Data directory size: $DATA_SIZE"
fi

# ============================================
# QUICK CHECKS
# ============================================
print_header "HEALTH CHECKS"

# Test dashboard endpoint
if curl -s --connect-timeout 5 "http://localhost:8501/_stcore/health" >/dev/null 2>&1; then
    echo -e "  $OK Dashboard responding"
else
    echo -e "  $FAIL Dashboard not responding"
fi

# Test nginx
if curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" "http://localhost/" 2>/dev/null | grep -q "200\|302"; then
    echo -e "  $OK Nginx proxy working"
else
    echo -e "  $WARN Nginx proxy may have issues"
fi

# ============================================
# SUMMARY
# ============================================
echo ""
echo "══════════════════════════════════════════════════════════════"

if [ "$SERVICES_OK" = true ]; then
    echo -e "  ${GREEN}${BOLD}All core services are running${NC}"
else
    echo -e "  ${RED}${BOLD}Some services need attention${NC}"
fi

echo "══════════════════════════════════════════════════════════════"
echo ""

# Commands hint
echo "Useful commands:"
echo "  View dashboard logs:  journalctl -u $SERVICE_NAME -f"
echo "  View crawl logs:      tail -f $LOG_DIR/update_daily.log"
echo "  Restart dashboard:    sudo systemctl restart $SERVICE_NAME"
echo "  Run manual update:    sudo $APP_DIR/scripts/update.sh"
echo ""
