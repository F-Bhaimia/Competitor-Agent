#!/bin/bash

# Competitor News Monitor - Automated Deployment Script
# Works on fresh Ubuntu/Debian servers OR existing installations
# Usage: sudo ./deploy.sh [OPTIONS]
#   --no-nginx    Skip nginx setup (if you have your own reverse proxy)
#   --no-ssl      Skip SSL setup prompts
#   --app-dir     Custom application directory (default: /opt/competitor-agent)

set -e  # Exit on error

# ============================================
# CONFIGURATION
# ============================================
APP_DIR="${APP_DIR:-/opt/competitor-agent}"
GIT_REPO="https://github.com/F-Bhaimia/Competitor-Agent.git"
SETUP_NGINX=true
SETUP_SSL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-nginx) SETUP_NGINX=false; shift ;;
        --no-ssl) SETUP_SSL=false; shift ;;
        --app-dir) APP_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}→ $1${NC}"; }
print_warn() { echo -e "${YELLOW}! $1${NC}"; }

echo ""
echo "=========================================="
echo "   COMPETITOR NEWS MONITOR - DEPLOYMENT"
echo "=========================================="
echo ""
echo "  App Directory: $APP_DIR"
echo "  Setup Nginx:   $SETUP_NGINX"
echo ""

# ============================================
# PRE-FLIGHT CHECKS
# ============================================

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root or with sudo"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    print_info "Detected OS: $OS $VERSION_ID"
else
    print_warn "Could not detect OS, assuming Debian-based"
    OS="debian"
fi

# ============================================
# STEP 1: SYSTEM DEPENDENCIES
# ============================================
print_info "Step 1/8: Installing system dependencies..."

apt-get update -qq

# Core packages
apt-get install -y -qq python3 python3-pip python3-venv git curl

# Playwright system dependencies
apt-get install -y -qq \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0 2>/dev/null || true

# Nginx (if needed)
if [ "$SETUP_NGINX" = true ]; then
    apt-get install -y -qq nginx
fi

# Firewall
apt-get install -y -qq ufw

print_success "System dependencies installed"

# ============================================
# STEP 2: APPLICATION DIRECTORY
# ============================================
print_info "Step 2/8: Setting up application directory..."

mkdir -p "$APP_DIR"
cd "$APP_DIR"

# Clone or pull repository
if [ -d ".git" ]; then
    print_info "Repository exists, pulling latest changes..."
    git fetch origin
    git reset --hard origin/main
else
    print_info "Cloning repository..."
    git clone "$GIT_REPO" .
fi

# Create required directories
mkdir -p logs data exports backups

print_success "Application directory ready: $APP_DIR"

# ============================================
# STEP 3: PYTHON ENVIRONMENT
# ============================================
print_info "Step 3/8: Setting up Python environment..."

# Detect Python executable
PYTHON_CMD=""
STREAMLIT_CMD=""
PIP_CMD=""

# Check for existing venv
if [ -d "$APP_DIR/.venv" ]; then
    print_info "Found existing virtual environment"
    PYTHON_CMD="$APP_DIR/.venv/bin/python"
    STREAMLIT_CMD="$APP_DIR/.venv/bin/streamlit"
    PIP_CMD="$APP_DIR/.venv/bin/pip"
    source "$APP_DIR/.venv/bin/activate"
elif [ -d "$APP_DIR/venv" ]; then
    print_info "Found existing virtual environment (venv)"
    PYTHON_CMD="$APP_DIR/venv/bin/python"
    STREAMLIT_CMD="$APP_DIR/venv/bin/streamlit"
    PIP_CMD="$APP_DIR/venv/bin/pip"
    source "$APP_DIR/venv/bin/activate"
else
    # Check if streamlit is already available system-wide
    if command -v streamlit &> /dev/null; then
        print_info "Found system-wide streamlit installation"
        PYTHON_CMD=$(which python3)
        STREAMLIT_CMD=$(which streamlit)
        PIP_CMD=$(which pip3)
    else
        # Create new virtual environment
        print_info "Creating new virtual environment..."
        python3 -m venv .venv
        PYTHON_CMD="$APP_DIR/.venv/bin/python"
        STREAMLIT_CMD="$APP_DIR/.venv/bin/streamlit"
        PIP_CMD="$APP_DIR/.venv/bin/pip"
        source "$APP_DIR/.venv/bin/activate"
    fi
fi

# Install/upgrade dependencies
print_info "Installing Python dependencies..."
$PIP_CMD install --upgrade pip -q
$PIP_CMD install -r requirements.txt -q

print_success "Python environment configured"
print_info "  Python: $PYTHON_CMD"
print_info "  Streamlit: $STREAMLIT_CMD"

# ============================================
# STEP 4: PLAYWRIGHT BROWSERS
# ============================================
print_info "Step 4/8: Installing Playwright browsers..."

$PYTHON_CMD -m playwright install chromium 2>/dev/null || true
$PYTHON_CMD -m playwright install-deps 2>/dev/null || true

print_success "Playwright installed"

# ============================================
# STEP 5: ENVIRONMENT FILE
# ============================================
print_info "Step 5/8: Configuring environment..."

if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << 'ENVEOF'
# Competitor News Monitor Configuration
# Edit these values with your actual keys

OPENAI_API_KEY=your-openai-api-key-here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
ENVEOF
    chmod 600 "$APP_DIR/.env"
    print_warn "Created .env template - YOU MUST EDIT THIS FILE!"
    print_warn "Run: nano $APP_DIR/.env"
else
    print_info ".env file already exists"
fi

print_success "Environment configuration ready"

# ============================================
# STEP 6: SYSTEMD SERVICES
# ============================================
print_info "Step 6/8: Setting up systemd services..."

# Dashboard service
cat > /etc/systemd/system/competitor-dashboard.service << SVCEOF
[Unit]
Description=Competitor News Monitor Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$STREAMLIT_CMD run streamlit_app/Home.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

# Webhook service
cat > /etc/systemd/system/competitor-webhook.service << SVCEOF
[Unit]
Description=Competitor News Monitor Webhook Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_CMD -m app.webhook_server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

# Reload and enable services
systemctl daemon-reload
systemctl enable competitor-dashboard
systemctl enable competitor-webhook

print_success "Systemd services configured"

# ============================================
# STEP 7: NGINX (optional)
# ============================================
if [ "$SETUP_NGINX" = true ]; then
    print_info "Step 7/8: Configuring Nginx..."

    SERVER_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    print_info "Server IP: $SERVER_IP"

    cat > /etc/nginx/sites-available/competitor-dashboard << NGINXEOF
server {
    listen 80;
    server_name $SERVER_IP;

    # Webhook endpoint for email ingestion
    location /email {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Dashboard
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
    print_info "Step 7/8: Skipping Nginx setup (--no-nginx)"
fi

# ============================================
# STEP 8: FIREWALL & CRON
# ============================================
print_info "Step 8/8: Configuring firewall and cron jobs..."

# Firewall
ufw allow 22/tcp >/dev/null 2>&1
ufw allow 80/tcp >/dev/null 2>&1
ufw allow 443/tcp >/dev/null 2>&1
ufw --force enable >/dev/null 2>&1

# Make scripts executable
chmod +x "$APP_DIR/scripts/"*.sh 2>/dev/null || true
chmod +x "$APP_DIR/deploy.sh" 2>/dev/null || true

# Setup cron jobs
CRON_DAILY="0 2 * * * $APP_DIR/scripts/update_daily.sh >> $APP_DIR/logs/cron.log 2>&1"
CRON_EMAIL="0 * * * * cd $APP_DIR && $PYTHON_CMD -m jobs.process_emails >> $APP_DIR/logs/cron.log 2>&1"

(crontab -l 2>/dev/null | grep -v "update_daily.sh" | grep -v "process_emails"; echo "$CRON_DAILY"; echo "$CRON_EMAIL") | crontab -

print_success "Firewall and cron configured"

# ============================================
# START SERVICES
# ============================================
print_info "Starting services..."

systemctl start competitor-dashboard
systemctl start competitor-webhook

sleep 3

# ============================================
# FINAL STATUS
# ============================================
echo ""
echo "=========================================="
echo "         DEPLOYMENT COMPLETE!"
echo "=========================================="
echo ""

# Check services
if systemctl is-active --quiet competitor-dashboard; then
    print_success "Dashboard service is running"
else
    print_error "Dashboard service failed - check: journalctl -u competitor-dashboard -n 50"
fi

if systemctl is-active --quiet competitor-webhook; then
    print_success "Webhook service is running"
else
    print_warn "Webhook service not running (may need .env configuration)"
fi

if [ "$SETUP_NGINX" = true ] && systemctl is-active --quiet nginx; then
    print_success "Nginx is running"
fi

echo ""
echo "=========================================="
echo "         NEXT STEPS"
echo "=========================================="
echo ""
echo "1. Edit your API keys:"
echo "   nano $APP_DIR/.env"
echo ""
echo "2. Restart services after editing .env:"
echo "   systemctl restart competitor-dashboard competitor-webhook"
echo ""
echo "3. Access your dashboard:"
SERVER_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo "   http://$SERVER_IP"
echo ""
echo "4. Useful commands:"
echo "   Status:   $APP_DIR/scripts/status.sh"
echo "   Update:   sudo $APP_DIR/scripts/update.sh quick"
echo "   Logs:     journalctl -u competitor-dashboard -f"
echo ""
echo "=========================================="
print_success "Deployment completed!"
