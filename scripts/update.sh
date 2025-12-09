#!/usr/bin/env bash
# update.sh - Update Competitor News Monitor application
# Pulls latest code, updates dependencies, and restarts services
set -euo pipefail

# Configuration
APP_DIR="/opt/competitor-agent"
VENV_DIR="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
BACKUP_DIR="$APP_DIR/backups"
SERVICE_NAME="competitor-dashboard"
GIT_REMOTE="origin"
GIT_BRANCH="main"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root (required for systemctl)
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root or with sudo"
        exit 1
    fi
}

# Show current version info
show_version() {
    cd "$APP_DIR"
    echo ""
    echo "=========================================="
    echo "       CURRENT VERSION INFO"
    echo "=========================================="
    echo "Branch: $(git branch --show-current)"
    echo "Commit: $(git rev-parse --short HEAD)"
    echo "Date:   $(git log -1 --format='%ci')"
    echo "=========================================="
    echo ""
}

# Create backup before update
create_backup() {
    log_info "Creating backup..."
    mkdir -p "$BACKUP_DIR"

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"

    # Backup data and config (not venv or git)
    tar -czf "$BACKUP_FILE" \
        --exclude='.venv' \
        --exclude='.git' \
        --exclude='backups' \
        --exclude='__pycache__' \
        -C "$APP_DIR" data config .env 2>/dev/null || true

    if [ -f "$BACKUP_FILE" ]; then
        log_success "Backup created: $BACKUP_FILE"
    else
        log_warn "Backup may be incomplete (some files may not exist yet)"
    fi

    # Keep only last 5 backups
    ls -1t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm -f
}

# Check for local changes
check_local_changes() {
    cd "$APP_DIR"

    if [ -n "$(git status --porcelain)" ]; then
        log_warn "Local changes detected:"
        git status --short
        echo ""
        read -p "Stash local changes and continue? (y/N): " response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            git stash push -m "Auto-stash before update $(date +%Y%m%d_%H%M%S)"
            log_success "Changes stashed"
        else
            log_error "Aborted. Please commit or stash your changes first."
            exit 1
        fi
    fi
}

# Pull latest code
pull_code() {
    log_info "Fetching latest code from $GIT_REMOTE/$GIT_BRANCH..."
    cd "$APP_DIR"

    # Fetch and show what's new
    git fetch "$GIT_REMOTE"

    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse "$GIT_REMOTE/$GIT_BRANCH")

    if [ "$LOCAL" = "$REMOTE" ]; then
        log_success "Already up to date!"
        return 1  # Return non-zero to indicate no update needed
    fi

    # Show incoming changes
    echo ""
    log_info "Incoming changes:"
    git log --oneline HEAD.."$GIT_REMOTE/$GIT_BRANCH"
    echo ""

    # Pull changes
    git pull "$GIT_REMOTE" "$GIT_BRANCH"
    log_success "Code updated successfully"
    return 0
}

# Update Python dependencies
update_dependencies() {
    log_info "Checking Python dependencies..."
    cd "$APP_DIR"

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"

    # Check if requirements.txt changed
    if git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -q "requirements.txt"; then
        log_info "requirements.txt changed, updating dependencies..."
        pip install --upgrade pip
        pip install -r requirements.txt
        log_success "Dependencies updated"
    else
        log_info "No dependency changes detected"
    fi
}

# Update Playwright browsers if needed
update_playwright() {
    log_info "Checking Playwright browsers..."
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"

    # Check if playwright was updated
    if git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -q "requirements.txt"; then
        log_info "Ensuring Playwright browsers are up to date..."
        playwright install chromium 2>/dev/null || true
        log_success "Playwright checked"
    fi
}

# Restart services
restart_services() {
    log_info "Restarting services..."

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl restart "$SERVICE_NAME"
        sleep 3

        if systemctl is-active --quiet "$SERVICE_NAME"; then
            log_success "Service '$SERVICE_NAME' restarted successfully"
        else
            log_error "Service failed to restart!"
            log_info "Check logs with: journalctl -u $SERVICE_NAME -n 50"
            return 1
        fi
    else
        log_warn "Service '$SERVICE_NAME' was not running, starting it..."
        systemctl start "$SERVICE_NAME"
        sleep 3

        if systemctl is-active --quiet "$SERVICE_NAME"; then
            log_success "Service started successfully"
        else
            log_error "Service failed to start!"
            return 1
        fi
    fi
}

# Show post-update status
show_status() {
    echo ""
    echo "=========================================="
    echo "       UPDATE COMPLETE"
    echo "=========================================="
    show_version

    echo "Service Status:"
    systemctl is-active "$SERVICE_NAME" && echo -e "  ${GREEN}●${NC} $SERVICE_NAME is running" || echo -e "  ${RED}●${NC} $SERVICE_NAME is stopped"
    systemctl is-active nginx && echo -e "  ${GREEN}●${NC} nginx is running" || echo -e "  ${RED}●${NC} nginx is stopped"
    echo ""

    # Show access URL
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo "Dashboard URL: http://$SERVER_IP"
    echo ""
}

# Rollback to previous version
rollback() {
    log_info "Rolling back to previous version..."
    cd "$APP_DIR"

    # Show recent commits
    echo "Recent commits:"
    git log --oneline -10
    echo ""

    read -p "Enter commit hash to rollback to (or press Enter to go back 1 commit): " commit_hash

    if [ -z "$commit_hash" ]; then
        commit_hash="HEAD~1"
    fi

    git checkout "$commit_hash"
    log_success "Rolled back to $commit_hash"

    restart_services
}

# Main update function
do_update() {
    echo ""
    echo "=========================================="
    echo "   COMPETITOR NEWS MONITOR - UPDATE"
    echo "=========================================="
    echo ""

    check_root
    show_version

    read -p "Proceed with update? (Y/n): " response
    if [[ "$response" =~ ^[Nn]$ ]]; then
        log_info "Update cancelled"
        exit 0
    fi

    create_backup
    check_local_changes

    if pull_code; then
        update_dependencies
        update_playwright
        restart_services
        show_status
    else
        log_info "No updates available"
    fi
}

# Quick update (no prompts)
do_quick_update() {
    echo ""
    log_info "Running quick update (no prompts)..."

    check_root
    create_backup

    cd "$APP_DIR"
    git stash push -m "Auto-stash $(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

    if pull_code; then
        update_dependencies
        update_playwright
        restart_services
        log_success "Quick update complete!"
    else
        log_info "No updates available"
    fi
}

# Show help
show_help() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  (none)     Interactive update with prompts"
    echo "  quick      Quick update without prompts"
    echo "  status     Show current version and service status"
    echo "  rollback   Rollback to a previous version"
    echo "  deps       Update dependencies only (no git pull)"
    echo "  restart    Restart services only"
    echo "  help       Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo $0           # Interactive update"
    echo "  sudo $0 quick     # Quick update for automation"
    echo "  sudo $0 status    # Check current status"
    echo ""
}

# Parse command line arguments
case "${1:-}" in
    quick)
        do_quick_update
        ;;
    status)
        show_version
        echo "Service Status:"
        systemctl status "$SERVICE_NAME" --no-pager -l || true
        ;;
    rollback)
        check_root
        rollback
        ;;
    deps)
        check_root
        update_dependencies
        update_playwright
        restart_services
        ;;
    restart)
        check_root
        restart_services
        ;;
    help|--help|-h)
        show_help
        ;;
    "")
        do_update
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
