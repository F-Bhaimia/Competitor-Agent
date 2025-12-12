#!/bin/bash
# Competitor News Monitor - Docker Installation Script
# Usage: curl -sSL https://raw.githubusercontent.com/F-Bhaimia/Competitor-Agent/main/install.sh | sudo bash
#   or:  sudo ./install.sh [OPTIONS]
#
# Options:
#   --no-nginx    Skip nginx reverse proxy setup
#   --no-cron     Skip cron job setup
#   --app-dir     Custom install directory (default: /opt/competitor-agent)

set -e

# ============================================
# CONFIGURATION
# ============================================
APP_DIR="${APP_DIR:-/opt/competitor-agent}"
GIT_REPO="https://github.com/F-Bhaimia/Competitor-Agent.git"
SETUP_NGINX=true
SETUP_CRON=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-nginx) SETUP_NGINX=false; shift ;;
        --no-cron) SETUP_CRON=false; shift ;;
        --app-dir) APP_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() { echo -e "${GREEN}[OK]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo ""
echo "============================================"
echo "  COMPETITOR NEWS MONITOR - INSTALLATION"
echo "============================================"
echo ""

# ============================================
# PRE-FLIGHT CHECKS
# ============================================
print_info "Checking prerequisites..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root or with sudo"
    exit 1
fi

# Check for Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first:"
    echo "  curl -fsSL https://get.docker.com | sh"
    exit 1
fi
print_success "Docker found: $(docker --version)"

# Check for Docker Compose
if ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not available. Please update Docker or install docker-compose."
    exit 1
fi
print_success "Docker Compose found"

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    print_error "Docker daemon is not running. Start it with: systemctl start docker"
    exit 1
fi
print_success "Docker daemon is running"

# ============================================
# STEP 1: CLONE/UPDATE REPOSITORY
# ============================================
print_info "Setting up application directory: $APP_DIR"

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ -d ".git" ]; then
    print_info "Repository exists, pulling latest changes..."
    git fetch origin
    git reset --hard origin/main
else
    print_info "Cloning repository..."
    git clone "$GIT_REPO" .
fi

# Create data directories
mkdir -p data logs exports config data/emails data/emails/processed data/emails/deleted

print_success "Application code ready"

# ============================================
# STEP 2: ENVIRONMENT FILE
# ============================================
print_info "Configuring environment..."

if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << 'EOF'
# Competitor News Monitor Configuration
# Edit these values with your actual keys

OPENAI_API_KEY=sk-your-openai-api-key-here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
EOF
    chmod 600 "$APP_DIR/.env"
    print_warn "Created .env template - YOU MUST EDIT THIS FILE!"
    print_warn "Run: nano $APP_DIR/.env"
else
    print_info ".env file already exists"
fi

# ============================================
# STEP 3: BUILD AND START CONTAINERS
# ============================================
print_info "Building Docker images (this may take a few minutes)..."

docker compose build --quiet

print_info "Starting services..."

# Stop any existing containers
docker compose down 2>/dev/null || true

# Start services
docker compose up -d

print_success "Docker containers started"

# ============================================
# STEP 4: NGINX REVERSE PROXY (optional)
# ============================================
if [ "$SETUP_NGINX" = true ]; then
    print_info "Setting up Nginx reverse proxy..."

    # Install nginx if not present
    if ! command -v nginx &> /dev/null; then
        apt-get update -qq
        apt-get install -y -qq nginx
    fi

    SERVER_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

    cat > /etc/nginx/sites-available/competitor-dashboard << NGINXEOF
server {
    listen 80;
    server_name $SERVER_IP _;

    # Webhook endpoint for email ingestion
    location /email {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://localhost:8001/health;
    }

    # Dashboard (Streamlit)
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 86400;
    }
}
NGINXEOF

    ln -sf /etc/nginx/sites-available/competitor-dashboard /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

    nginx -t && systemctl restart nginx && systemctl enable nginx
    print_success "Nginx configured"
else
    print_info "Skipping Nginx setup (--no-nginx)"
fi

# ============================================
# STEP 5: CRON JOBS (optional)
# ============================================
if [ "$SETUP_CRON" = true ]; then
    print_info "Setting up cron jobs..."

    # Cron job for daily pipeline (RSS + enrichment) at 6am
    CRON_PIPELINE="0 6 * * * cd $APP_DIR && docker compose run --rm pipeline >> $APP_DIR/logs/cron.log 2>&1"

    # Cron job for weekly blog crawl on Sundays at 3am
    CRON_CRAWLER="0 3 * * 0 cd $APP_DIR && docker compose run --rm crawler >> $APP_DIR/logs/cron.log 2>&1"

    # Remove old entries and add new ones
    (crontab -l 2>/dev/null | grep -v "competitor" | grep -v "docker compose run"; \
     echo "$CRON_PIPELINE"; \
     echo "$CRON_CRAWLER") | crontab -

    print_success "Cron jobs configured"
    print_info "  - Daily pipeline: 6:00 AM"
    print_info "  - Weekly crawl: Sundays 3:00 AM"
else
    print_info "Skipping cron setup (--no-cron)"
fi

# ============================================
# STEP 6: FIREWALL
# ============================================
if command -v ufw &> /dev/null; then
    print_info "Configuring firewall..."
    ufw allow 22/tcp >/dev/null 2>&1 || true
    ufw allow 80/tcp >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    ufw --force enable >/dev/null 2>&1 || true
    print_success "Firewall configured"
fi

# ============================================
# VERIFY SERVICES
# ============================================
print_info "Waiting for services to start..."
sleep 5

echo ""
echo "============================================"
echo "          INSTALLATION COMPLETE"
echo "============================================"
echo ""

# Check container status
if docker compose ps | grep -q "running"; then
    print_success "Services are running"
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
else
    print_warn "Some services may not be running. Check with:"
    echo "  cd $APP_DIR && docker compose logs"
fi

echo ""
echo "============================================"
echo "              NEXT STEPS"
echo "============================================"
echo ""
echo "1. Edit your API keys:"
echo "   nano $APP_DIR/.env"
echo ""
echo "2. Restart services after editing .env:"
echo "   cd $APP_DIR && docker compose restart"
echo ""
echo "3. Access your dashboard:"
SERVER_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo "   http://$SERVER_IP"
echo ""
echo "4. View logs:"
echo "   cd $APP_DIR && docker compose logs -f"
echo ""
echo "5. Update to latest version:"
echo "   $APP_DIR/update.sh"
echo ""
echo "============================================"
print_success "Installation completed!"
