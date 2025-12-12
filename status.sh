#!/bin/bash
# Competitor News Monitor - Status Check Script
# Usage: ./status.sh

cd /opt/competitor-agent 2>/dev/null || cd "$(dirname "$0")"

echo "============================================"
echo "  COMPETITOR MONITOR - STATUS CHECK"
echo "============================================"
echo ""

echo "=== CONTAINERS ==="
docker compose ps
echo ""

echo "=== DASHBOARD LOGS (last 30 lines) ==="
docker compose logs --tail=30 dashboard
echo ""

echo "=== WEBHOOK LOGS (last 30 lines) ==="
docker compose logs --tail=30 webhook
echo ""

echo "=== PORTS LISTENING ==="
ss -tlnp | grep -E '8501|8001|80' || netstat -tlnp | grep -E '8501|8001|80' 2>/dev/null
echo ""

echo "=== NGINX STATUS ==="
systemctl status nginx --no-pager 2>/dev/null || echo "nginx not installed or not using systemd"
echo ""

echo "=== HEALTH CHECKS ==="
echo -n "Dashboard (8501): "
curl -s --connect-timeout 5 http://localhost:8501/_stcore/health || echo "FAILED"
echo ""
echo -n "Webhook (8001): "
curl -s --connect-timeout 5 http://localhost:8001/health || echo "FAILED"
echo ""

echo "============================================"
echo "  STATUS CHECK COMPLETE"
echo "============================================"
