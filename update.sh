#!/bin/bash
# Competitor News Monitor - Update Script
# Usage: ./update.sh [quick]
#   quick  - Skip Docker rebuild, just restart containers (faster)

set -e

# Find app directory (script location or /opt/competitor-agent)
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
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${BLUE}[INFO]${NC} Updating Competitor News Monitor..."
echo ""

# Check for quick mode
QUICK_MODE=false
if [ "$1" = "quick" ]; then
    QUICK_MODE=true
    echo -e "${YELLOW}[INFO]${NC} Quick mode - skipping rebuild"
fi

# Pull latest code
echo -e "${BLUE}[INFO]${NC} Pulling latest code..."
git fetch origin
git reset --hard origin/main

if [ "$QUICK_MODE" = true ]; then
    # Quick restart without rebuild
    echo -e "${BLUE}[INFO]${NC} Restarting containers..."
    docker compose restart
else
    # Full rebuild
    echo -e "${BLUE}[INFO]${NC} Rebuilding containers..."
    docker compose build --quiet

    echo -e "${BLUE}[INFO]${NC} Restarting services..."
    docker compose down
    docker compose up -d
fi

# Show status
echo ""
echo -e "${GREEN}[OK]${NC} Update complete!"
echo ""
docker compose ps --format "table {{.Name}}\t{{.Status}}"
echo ""

# Show recent commits
echo -e "${BLUE}[INFO]${NC} Recent changes:"
git log --oneline -5
echo ""
