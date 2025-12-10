# Deployment Guide - Vultr Server

This guide will walk you through deploying the Competitor News Monitor on your Vultr server.

## Prerequisites

- Vultr server with Ubuntu 20.04/22.04 or Debian
- SSH access to your server
- Root or sudo privileges
- Your server IP address or domain name

## Step 1: Connect to Your Vultr Server

```bash
ssh root@your-server-ip
# OR
ssh your-username@your-server-ip
```

## Step 2: Update System and Install Dependencies

```bash
# Update package lists
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3 python3-pip python3-venv git nginx ufw screen

# Install system dependencies for Playwright
sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0
```

## Step 3: Create Application Directory and Clone Repository

```bash
# Create application directory
cd /opt
sudo mkdir -p competitor-agent
sudo chown $USER:$USER competitor-agent
cd competitor-agent

# Clone the repository
git clone https://github.com/F-Bhaimia/Competitor-Agent.git .

# Verify files are present
ls -la
```

## Step 4: Set Up Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Step 5: Configure Environment Variables

```bash
# Create .env file
nano .env
```

Add the following content (replace with your actual keys):
```env
OPENAI_API_KEY=sk-your-openai-api-key-here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Save and exit (Ctrl+X, then Y, then Enter)

```bash
# Secure the .env file
chmod 600 .env

# Verify it was created
cat .env
```

## Step 6: Test the Application

```bash
# Make sure you're in the virtual environment
source .venv/bin/activate

# Test a quick crawl
python3 -m app.crawl

# If that works, test the full pipeline (optional)
./scripts/run_pipeline.sh
```

## Step 7: Set Up Systemd Services

### 7a. Dashboard Service

```bash
# Create systemd service file
sudo nano /etc/systemd/system/competitor-dashboard.service
```

Add the following content (adjust paths if needed):
```ini
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
```

Save and exit (Ctrl+X, then Y, then Enter)

### 7b. Webhook Server Service (for newsletter ingestion)

```bash
# Create webhook service file
sudo nano /etc/systemd/system/competitor-webhook.service
```

Add the following content:
```ini
[Unit]
Description=Competitor News Monitor Webhook Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/competitor-agent
Environment="PATH=/opt/competitor-agent/.venv/bin"
ExecStart=/opt/competitor-agent/.venv/bin/python -m app.webhook_server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save and exit (Ctrl+X, then Y, then Enter)

### 7c. Enable and Start Services

```bash
# Reload systemd to recognize new services
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable competitor-dashboard
sudo systemctl enable competitor-webhook

# Start the services
sudo systemctl start competitor-dashboard
sudo systemctl start competitor-webhook

# Check service status
sudo systemctl status competitor-dashboard
sudo systemctl status competitor-webhook

# View logs if needed
sudo journalctl -u competitor-dashboard -f
sudo journalctl -u competitor-webhook -f
```

## Step 8: Configure Nginx Reverse Proxy

```bash
# Create Nginx configuration
sudo nano /etc/nginx/sites-available/competitor-dashboard
```

Add the following content:
```nginx
server {
    listen 80;
    server_name your-server-ip;  # Replace with your domain or IP

    # Webhook endpoint for CloudMailin email ingestion
    location /email {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Dashboard
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }
}
```

Save and exit (Ctrl+X, then Y, then Enter)

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/competitor-dashboard /etc/nginx/sites-enabled/

# Remove default Nginx site (optional)
sudo rm /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Enable Nginx to start on boot
sudo systemctl enable nginx
```

## Step 9: Configure Firewall

```bash
# Allow SSH (important - don't lock yourself out!)
sudo ufw allow 22/tcp

# Allow HTTP
sudo ufw allow 80/tcp

# Allow HTTPS (for future SSL setup)
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw --force enable

# Check firewall status
sudo ufw status
```

## Step 10: Set Up Automated Daily Crawls (Cron Job)

```bash
# Make scripts executable
chmod +x /opt/competitor-agent/scripts/*.sh

# Edit crontab
crontab -e
```

Add the following lines:
```cron
# Process newsletter emails every hour
0 * * * * cd /opt/competitor-agent && .venv/bin/python -m jobs.process_emails >> /opt/competitor-agent/logs/cron.log 2>&1

# Run daily crawl at 2 AM server time
0 2 * * * /opt/competitor-agent/scripts/update_daily.sh >> /opt/competitor-agent/logs/cron.log 2>&1
```

Save and exit

```bash
# Create logs directory
mkdir -p /opt/competitor-agent/logs

# Verify cron job was added
crontab -l
```

## Step 11: Access Your Dashboard

Open your web browser and go to:
```
http://your-server-ip
```

You should see your Streamlit dashboard running!

## Step 12: (Optional) Set Up SSL with Let's Encrypt

If you have a domain name pointed to your server:

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com

# Certbot will automatically configure Nginx for HTTPS
# Follow the prompts

# Test auto-renewal
sudo certbot renew --dry-run
```

## Useful Management Commands

### Check Service Status
```bash
sudo systemctl status competitor-dashboard
sudo systemctl status competitor-webhook
```

### Restart Services
```bash
sudo systemctl restart competitor-dashboard
sudo systemctl restart competitor-webhook
```

### View Logs
```bash
# Dashboard logs
sudo journalctl -u competitor-dashboard -f

# Webhook server logs
sudo journalctl -u competitor-webhook -f
```

### View Cron Job Logs
```bash
tail -f /opt/competitor-agent/logs/cron.log
```

### Manual Pipeline Run
```bash
cd /opt/competitor-agent
source .venv/bin/activate
./scripts/run_pipeline.sh
```

### Update Code from GitHub

**Recommended: Use the update script**
```bash
sudo /opt/competitor-agent/scripts/update.sh
```

This interactive script will:
- Show current version info
- Create a backup before updating
- Pull latest code from git
- Update Python dependencies if changed
- Restart services automatically

**Quick update (for automation/cron)**
```bash
sudo /opt/competitor-agent/scripts/update.sh quick
```

**Manual update (if needed)**
```bash
cd /opt/competitor-agent
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart competitor-dashboard
```

### Check Nginx Status
```bash
sudo systemctl status nginx
```

### View Nginx Error Logs
```bash
sudo tail -f /var/log/nginx/error.log
```

### System Health Check
```bash
sudo /opt/competitor-agent/scripts/status.sh
```

This will show a comprehensive status report including:
- Current version and git status
- Service status (dashboard, nginx)
- Network ports and connectivity
- Data file sizes and record counts
- Recent crawl activity
- System resources (disk, memory, load)
- Health check results

---

## Updating the Application

### Update Script Reference

The `update.sh` script provides several commands for managing updates:

| Command | Description |
|---------|-------------|
| `sudo ./scripts/update.sh` | Interactive update with prompts |
| `sudo ./scripts/update.sh quick` | Quick update without prompts (for automation) |
| `sudo ./scripts/update.sh status` | Show current version and service status |
| `sudo ./scripts/update.sh rollback` | Rollback to a previous version |
| `sudo ./scripts/update.sh deps` | Update dependencies only (no git pull) |
| `sudo ./scripts/update.sh restart` | Restart services only |

### Automated Updates (Optional)

To automatically check for and apply updates weekly:

```bash
# Edit crontab
sudo crontab -e

# Add weekly update check (Sundays at 3 AM)
0 3 * * 0 /opt/competitor-agent/scripts/update.sh quick >> /opt/competitor-agent/logs/update.log 2>&1
```

### Rollback Procedure

If an update causes issues:

```bash
# Interactive rollback
sudo /opt/competitor-agent/scripts/update.sh rollback

# Or manual rollback
cd /opt/competitor-agent
git log --oneline -10  # Find the commit to rollback to
git checkout <commit-hash>
sudo systemctl restart competitor-dashboard
```

### Backups

The update script automatically creates backups in `/opt/competitor-agent/backups/` before each update. To manually backup:

```bash
# Create backup of data directory
cd /opt/competitor-agent
tar -czf backups/manual-backup-$(date +%Y%m%d).tar.gz data config .env

# Download backup to local machine
scp root@your-server-ip:/opt/competitor-agent/backups/*.tar.gz ./
```

---

## Troubleshooting

### Dashboard Won't Start
```bash
# Check logs
sudo journalctl -u competitor-dashboard -n 50

# Verify virtual environment
ls -la /opt/competitor-agent/.venv

# Test Streamlit manually
cd /opt/competitor-agent
source .venv/bin/activate
streamlit run streamlit_app/Home.py
```

### Can't Access Dashboard from Browser
```bash
# Check if service is running
sudo systemctl status competitor-dashboard

# Check if Nginx is running
sudo systemctl status nginx

# Check firewall
sudo ufw status

# Check if port 8501 is listening
sudo netstat -tulpn | grep 8501
```

### Playwright/Crawling Issues
```bash
# Reinstall Playwright browsers
cd /opt/competitor-agent
source .venv/bin/activate
playwright install chromium
playwright install-deps
```

### Permission Issues
```bash
# Fix ownership
sudo chown -R $USER:$USER /opt/competitor-agent

# Fix .env permissions
chmod 600 /opt/competitor-agent/.env
```

## Monitoring and Maintenance

### Disk Space
```bash
# Check disk usage
df -h

# Check data directory size
du -sh /opt/competitor-agent/data/
```

### Memory Usage
```bash
# Check memory
free -h

# Check processes
top
# or
htop
```

### Backup Data
```bash
# Create backup of data directory
tar -czf competitor-data-backup-$(date +%Y%m%d).tar.gz /opt/competitor-agent/data/

# Copy to local machine
scp root@your-server-ip:/root/competitor-data-backup-*.tar.gz ./
```

## Security Recommendations

1. **Change default SSH port** (optional but recommended)
2. **Set up SSH key authentication** and disable password login
3. **Keep system updated**: `sudo apt update && sudo apt upgrade` regularly
4. **Monitor logs** for suspicious activity
5. **Restrict Nginx access** by IP if dashboard should be private
6. **Use strong passwords** for all accounts
7. **Enable automatic security updates**

## Performance Optimization

### If server runs out of memory:
```bash
# Create swap file (2GB)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Limit Playwright memory usage:
Edit `config/monitors.yaml` and reduce `max_pages_per_site`

## Next Steps

1. Access your dashboard at `http://your-server-ip`
2. Wait for the first automated crawl (2 AM) or run manually
3. Monitor the logs to ensure everything is working
4. Set up SSL if you have a domain
5. Configure Slack alerts in your `.env` file

## Support

If you encounter issues:
- Check the logs: `sudo journalctl -u competitor-dashboard -f`
- Review this guide's Troubleshooting section
- Check GitHub repository issues

Your Competitor News Monitor is now deployed and running 24/7!
