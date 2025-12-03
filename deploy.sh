#!/bin/bash

# Competitor News Monitor - Automated Deployment Script for Vultr
# This script automates the deployment process on a fresh Ubuntu/Debian server

set -e  # Exit on error

echo "=========================================="
echo "Competitor News Monitor - Deployment"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root or with sudo"
    exit 1
fi

print_info "Starting deployment..."
echo ""

# Step 1: Update system
print_info "Step 1/10: Updating system packages..."
apt update && apt upgrade -y
print_success "System updated"
echo ""

# Step 2: Install dependencies
print_info "Step 2/10: Installing system dependencies..."
apt install -y python3 python3-pip python3-venv git nginx ufw screen curl

# Playwright system dependencies
apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0

print_success "Dependencies installed"
echo ""

# Step 3: Set up application directory
print_info "Step 3/10: Setting up application directory..."
APP_DIR="/opt/competitor-agent"
mkdir -p $APP_DIR
cd $APP_DIR

# Clone or pull repository
if [ -d ".git" ]; then
    print_info "Repository exists, pulling latest changes..."
    git pull origin main
else
    print_info "Cloning repository..."
    git clone https://github.com/F-Bhaimia/Competitor-Agent.git .
fi

print_success "Application directory ready"
echo ""

# Step 4: Set up Python virtual environment
print_info "Step 4/10: Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
print_success "Python environment configured"
echo ""

# Step 5: Install Playwright browsers
print_info "Step 5/10: Installing Playwright browsers..."
playwright install chromium
print_success "Playwright installed"
echo ""

# Step 6: Configure environment variables
print_info "Step 6/10: Configuring environment variables..."
if [ ! -f ".env" ]; then
    echo "OPENAI_API_KEY=your-key-here" > .env
    echo "SLACK_WEBHOOK_URL=your-webhook-here" >> .env
    chmod 600 .env
    print_info "Created .env template - YOU NEED TO EDIT THIS FILE!"
    echo ""
    echo "Run: nano $APP_DIR/.env"
    echo "And add your actual API keys"
    echo ""
else
    print_info ".env file already exists, skipping..."
fi
print_success "Environment configuration ready"
echo ""

# Step 7: Create logs directory
print_info "Creating logs directory..."
mkdir -p $APP_DIR/logs
mkdir -p $APP_DIR/data
mkdir -p $APP_DIR/exports
print_success "Directories created"
echo ""

# Step 8: Set up systemd service
print_info "Step 7/10: Setting up systemd service..."
cat > /etc/systemd/system/competitor-dashboard.service << 'EOL'
[Unit]
Description=Competitor News Monitor Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/competitor-agent
Environment="PATH=/opt/competitor-agent/.venv/bin"
ExecStart=/opt/competitor-agent/.venv/bin/streamlit run streamlit_app/Home.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

systemctl daemon-reload
systemctl enable competitor-dashboard
print_success "Systemd service configured"
echo ""

# Step 9: Configure Nginx
print_info "Step 8/10: Configuring Nginx..."

# Get server IP
SERVER_IP=$(curl -s ifconfig.me)
print_info "Detected server IP: $SERVER_IP"

cat > /etc/nginx/sites-available/competitor-dashboard << EOL
server {
    listen 80;
    server_name $SERVER_IP;

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
EOL

# Enable site
ln -sf /etc/nginx/sites-available/competitor-dashboard /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and restart Nginx
nginx -t
systemctl restart nginx
systemctl enable nginx
print_success "Nginx configured"
echo ""

# Step 10: Configure firewall
print_info "Step 9/10: Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
print_success "Firewall configured"
echo ""

# Step 11: Set up cron job
print_info "Step 10/10: Setting up automated crawls..."
chmod +x $APP_DIR/scripts/*.sh

# Create cron job
CRON_JOB="0 2 * * * $APP_DIR/scripts/update_daily.sh >> $APP_DIR/logs/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "update_daily.sh"; echo "$CRON_JOB") | crontab -
print_success "Cron job configured (runs daily at 2 AM)"
echo ""

# Start the service
print_info "Starting dashboard service..."
systemctl start competitor-dashboard
sleep 3
print_success "Dashboard service started"
echo ""

# Final status check
echo "=========================================="
echo "         DEPLOYMENT COMPLETE!"
echo "=========================================="
echo ""

# Check service status
if systemctl is-active --quiet competitor-dashboard; then
    print_success "Dashboard is running"
else
    print_error "Dashboard failed to start - check logs with: journalctl -u competitor-dashboard -n 50"
fi

if systemctl is-active --quiet nginx; then
    print_success "Nginx is running"
else
    print_error "Nginx failed to start"
fi

echo ""
echo "=========================================="
echo "         IMPORTANT NEXT STEPS"
echo "=========================================="
echo ""
echo "1. Edit your API keys:"
echo "   nano $APP_DIR/.env"
echo ""
echo "2. Restart the dashboard after editing .env:"
echo "   systemctl restart competitor-dashboard"
echo ""
echo "3. Access your dashboard at:"
echo "   http://$SERVER_IP"
echo ""
echo "4. Check service status:"
echo "   systemctl status competitor-dashboard"
echo ""
echo "5. View logs:"
echo "   journalctl -u competitor-dashboard -f"
echo ""
echo "=========================================="
echo "         USEFUL COMMANDS"
echo "=========================================="
echo ""
echo "Restart dashboard:    systemctl restart competitor-dashboard"
echo "View logs:            journalctl -u competitor-dashboard -f"
echo "Run manual crawl:     cd $APP_DIR && source .venv/bin/activate && ./scripts/run_pipeline.sh"
echo "Update code:          cd $APP_DIR && git pull origin main && systemctl restart competitor-dashboard"
echo ""
print_success "Deployment completed successfully!"
