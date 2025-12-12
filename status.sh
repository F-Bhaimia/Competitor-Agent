#!/bin/bash
# Competitor News Monitor - Status Check Script
# Usage: ./status.sh

set -euo pipefail

# Find app directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    APP_DIR="$SCRIPT_DIR"
elif [ -f "/opt/competitor-agent/docker-compose.yml" ]; then
    APP_DIR="/opt/competitor-agent"
else
    echo "Error: Cannot find docker-compose.yml"
    exit 1
fi

cd "$APP_DIR"

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

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        COMPETITOR NEWS MONITOR - STATUS REPORT               ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Generated: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Hostname:  $(hostname)"
echo "  App Dir:   $APP_DIR"

# ============================================
# VERSION INFO
# ============================================
print_header "VERSION INFO"

if [ -d "$APP_DIR/.git" ]; then
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
# DOCKER CONTAINERS
# ============================================
print_header "DOCKER CONTAINERS"

if command -v docker &> /dev/null; then
    # Check each container
    for container in competitor-dashboard competitor-webhook; do
        STATUS=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "not found")
        HEALTH=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "")

        if [ "$STATUS" = "running" ]; then
            if [ "$HEALTH" = "healthy" ]; then
                echo -e "  $OK $container: running (healthy)"
            elif [ "$HEALTH" = "unhealthy" ]; then
                echo -e "  $WARN $container: running (unhealthy)"
            else
                echo -e "  $OK $container: running"
            fi
        else
            echo -e "  $FAIL $container: $STATUS"
        fi
    done

    echo ""
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
else
    echo -e "  $FAIL Docker not installed"
fi

# ============================================
# NETWORK / PORTS
# ============================================
print_header "NETWORK"

check_port() {
    local port=$1
    local name=$2
    if ss -tlnp 2>/dev/null | grep -q ":$port " || netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        echo -e "  $OK Port $port ($name) is listening"
    else
        echo -e "  $FAIL Port $port ($name) is not listening"
    fi
}

check_port 8501 "Streamlit/Docker"
check_port 8001 "Webhook"
check_port 80 "HTTP/nginx"
check_port 443 "HTTPS/nginx" || true

# Get server IP
SERVER_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
echo ""
echo "  Public IP: $SERVER_IP"
echo "  Dashboard: http://$SERVER_IP"

# ============================================
# NGINX STATUS
# ============================================
print_header "NGINX"

if command -v nginx &> /dev/null; then
    if systemctl is-active --quiet nginx 2>/dev/null; then
        echo -e "  $OK nginx is running"
    else
        echo -e "  $FAIL nginx is stopped"
    fi

    # Check config
    if nginx -t 2>&1 | grep -q "syntax is ok"; then
        echo -e "  $OK nginx config is valid"
    else
        echo -e "  $WARN nginx config has issues"
    fi

    # List enabled sites
    echo ""
    echo "  Enabled sites:"
    ls -1 /etc/nginx/sites-enabled/ 2>/dev/null | sed 's/^/    - /' || echo "    (none)"
else
    echo "  nginx not installed"
fi

# ============================================
# HEALTH CHECKS
# ============================================
print_header "HEALTH CHECKS"

# Test dashboard
echo -n "  Dashboard (8501): "
if curl -sf --connect-timeout 5 http://localhost:8501/_stcore/health >/dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# Test webhook
echo -n "  Webhook (8001):   "
WEBHOOK_RESP=$(curl -sf --connect-timeout 5 http://localhost:8001/health 2>/dev/null || echo "FAILED")
if [ "$WEBHOOK_RESP" != "FAILED" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# Test nginx proxy
echo -n "  Nginx proxy (80): "
HTTP_CODE=$(curl -sf --connect-timeout 5 -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED (HTTP $HTTP_CODE)${NC}"
fi

# ============================================
# DATA FILES
# ============================================
print_header "DATA FILES"

DATA_DIR="$APP_DIR/data"
if [ -d "$DATA_DIR" ]; then
    for file in updates.csv enriched_updates.csv updates.parquet; do
        if [ -f "$DATA_DIR/$file" ]; then
            SIZE=$(du -h "$DATA_DIR/$file" 2>/dev/null | cut -f1)
            MODIFIED=$(stat -c %y "$DATA_DIR/$file" 2>/dev/null | cut -d. -f1 || stat -f %Sm "$DATA_DIR/$file" 2>/dev/null)
            echo -e "  $OK $file: $SIZE (modified: $MODIFIED)"
        else
            echo -e "  $WARN $file: not found"
        fi
    done

    # Record counts
    if [ -f "$DATA_DIR/enriched_updates.csv" ]; then
        COUNT=$(($(wc -l < "$DATA_DIR/enriched_updates.csv") - 1))
        echo ""
        echo "  Total enriched records: $COUNT"
    fi
else
    echo "  Data directory not found"
fi

# ============================================
# ENVIRONMENT
# ============================================
print_header "ENVIRONMENT"

if [ -f "$APP_DIR/.env" ]; then
    echo -e "  $OK .env file exists"

    # Check API key (without revealing it)
    if grep -qE "OPENAI_API_KEY=sk-" "$APP_DIR/.env" 2>/dev/null; then
        echo -e "  $OK OpenAI API key configured"
    else
        echo -e "  $WARN OpenAI API key not configured"
    fi
else
    echo -e "  $FAIL .env file missing"
fi

# ============================================
# RECENT LOGS
# ============================================
print_header "RECENT CONTAINER LOGS"

echo "Dashboard (last 5 lines):"
docker compose logs --tail=5 dashboard 2>/dev/null | sed 's/^/  /' || echo "  (no logs)"

echo ""
echo "Webhook (last 5 lines):"
docker compose logs --tail=5 webhook 2>/dev/null | sed 's/^/  /' || echo "  (no logs)"

# ============================================
# SUMMARY
# ============================================
echo ""
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "Useful commands:"
echo "  View logs:        cd $APP_DIR && docker compose logs -f"
echo "  Restart:          cd $APP_DIR && docker compose restart"
echo "  Rebuild:          cd $APP_DIR && docker compose down && docker compose up -d --build"
echo "  Update:           cd $APP_DIR && ./update.sh"
echo ""
