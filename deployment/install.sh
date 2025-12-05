#!/bin/bash
# =============================================================================
# MCP Raspi Server Installation Script
# =============================================================================
#
# This script installs the Raspberry Pi MCP Server on a clean Raspberry Pi OS.
#
# Usage:
#   sudo ./install.sh [OPTIONS]
#
# Options:
#   --dry-run       Show what would be done without making changes
#   --skip-deps     Skip system dependency installation
#   --skip-service  Skip systemd service installation
#   --version VER   Install specific version (default: latest)
#   --channel CH    Update channel: stable, beta, dev (default: stable)
#   --help          Show this help message
#
# Requirements:
#   - Raspberry Pi OS (32-bit or 64-bit)
#   - Python 3.11 or higher
#   - Internet connection (for package installation)
#   - Root/sudo access
#
# See docs/12-deployment-systemd-integration-and-operations-runbook.md for details.
# =============================================================================

set -euo pipefail

# Configuration
MCP_VERSION="${MCP_VERSION:-latest}"
MCP_CHANNEL="${MCP_CHANNEL:-stable}"
MCP_USER="mcp-raspi"
MCP_GROUP="mcp-raspi"
MCP_INSTALL_DIR="/opt/mcp-raspi"
MCP_CONFIG_DIR="/etc/mcp-raspi"
MCP_LOG_DIR="/var/log/mcp-raspi"
MCP_DATA_DIR="/var/lib/mcp-raspi"
MCP_RUN_DIR="/run/mcp-raspi"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Flags
DRY_RUN=false
SKIP_DEPS=false
SKIP_SERVICE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] $*"
    else
        "$@"
    fi
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_os() {
    log_info "Checking operating system..."
    
    if [ ! -f /etc/os-release ]; then
        log_error "Cannot detect OS. /etc/os-release not found."
        exit 1
    fi
    
    source /etc/os-release
    
    if [[ "$ID" != "raspbian" && "$ID" != "debian" && "$ID_LIKE" != *"debian"* ]]; then
        log_warn "This script is designed for Raspberry Pi OS (Debian-based)."
        log_warn "Detected: $PRETTY_NAME"
        read -p "Continue anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    log_success "OS: $PRETTY_NAME"
}

check_python() {
    log_info "Checking Python version..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed. Please install Python 3.11 or higher."
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
        log_error "Python 3.11 or higher is required. Found: Python $PYTHON_VERSION"
        exit 1
    fi
    
    log_success "Python version: $PYTHON_VERSION"
}

check_disk_space() {
    log_info "Checking disk space..."
    
    # Require at least 500MB free
    AVAILABLE_MB=$(df / | awk 'NR==2 {print int($4/1024)}')
    
    if [ "$AVAILABLE_MB" -lt 500 ]; then
        log_error "Insufficient disk space. Required: 500MB, Available: ${AVAILABLE_MB}MB"
        exit 1
    fi
    
    log_success "Available disk space: ${AVAILABLE_MB}MB"
}

# =============================================================================
# Installation Functions
# =============================================================================

install_system_deps() {
    log_info "Installing system dependencies..."
    
    run_cmd apt-get update
    run_cmd apt-get install -y \
        python3-pip \
        python3-venv \
        i2c-tools \
        libgpiod2 \
        sqlite3
    
    log_success "System dependencies installed"
}

create_user() {
    log_info "Creating system user '$MCP_USER'..."
    
    if id "$MCP_USER" &>/dev/null; then
        log_info "User '$MCP_USER' already exists"
    else
        run_cmd useradd --system --no-create-home --shell /usr/sbin/nologin "$MCP_USER"
        log_success "User '$MCP_USER' created"
    fi
    
    # Add user to hardware access groups
    log_info "Adding user to hardware access groups..."
    run_cmd usermod -aG gpio,i2c,video "$MCP_USER" 2>/dev/null || true
}

create_directories() {
    log_info "Creating directories..."
    
    # Create installation directory
    run_cmd mkdir -p "$MCP_INSTALL_DIR/releases"
    run_cmd mkdir -p "$MCP_INSTALL_DIR/staging"
    run_cmd mkdir -p "$MCP_INSTALL_DIR/keys"
    
    # Create config directory
    run_cmd mkdir -p "$MCP_CONFIG_DIR"
    
    # Create log directory
    run_cmd mkdir -p "$MCP_LOG_DIR"
    
    # Create data directories
    run_cmd mkdir -p "$MCP_DATA_DIR/metrics"
    run_cmd mkdir -p "$MCP_DATA_DIR/media"
    
    # Create runtime directory (for socket)
    run_cmd mkdir -p "$MCP_RUN_DIR"
    
    log_success "Directories created"
}

set_permissions() {
    log_info "Setting permissions..."
    
    # Installation directory - owned by mcp-raspi
    run_cmd chown -R "$MCP_USER:$MCP_GROUP" "$MCP_INSTALL_DIR"
    run_cmd chmod 755 "$MCP_INSTALL_DIR"
    
    # Config directory - root owns, mcp-raspi can read
    run_cmd chown root:"$MCP_GROUP" "$MCP_CONFIG_DIR"
    run_cmd chmod 750 "$MCP_CONFIG_DIR"
    
    # Log directory - mcp-raspi owns
    run_cmd chown -R "$MCP_USER:$MCP_GROUP" "$MCP_LOG_DIR"
    run_cmd chmod 755 "$MCP_LOG_DIR"
    
    # Data directory - mcp-raspi owns
    run_cmd chown -R "$MCP_USER:$MCP_GROUP" "$MCP_DATA_DIR"
    run_cmd chmod 755 "$MCP_DATA_DIR"
    
    # Runtime directory
    run_cmd chown root:"$MCP_GROUP" "$MCP_RUN_DIR"
    run_cmd chmod 750 "$MCP_RUN_DIR"
    
    log_success "Permissions set"
}

install_mcp_server() {
    log_info "Installing MCP Raspi Server..."
    
    # Determine version
    local VERSION="$MCP_VERSION"
    if [ "$VERSION" = "latest" ]; then
        VERSION="0.1.0"  # Default to current version
    fi
    
    local RELEASE_DIR="$MCP_INSTALL_DIR/releases/$VERSION"
    
    # Create release directory
    run_cmd mkdir -p "$RELEASE_DIR"
    
    # Create virtual environment
    log_info "Creating virtual environment..."
    run_cmd python3 -m venv "$RELEASE_DIR/venv"
    
    # Upgrade pip
    run_cmd "$RELEASE_DIR/venv/bin/pip" install --upgrade pip
    
    # Install MCP Raspi package
    log_info "Installing mcp-raspi package..."
    if [ -f "$SCRIPT_DIR/../pyproject.toml" ]; then
        # Install from local source (development)
        run_cmd "$RELEASE_DIR/venv/bin/pip" install "$SCRIPT_DIR/.."
    else
        # Install from PyPI
        run_cmd "$RELEASE_DIR/venv/bin/pip" install "mcp-raspi"
    fi
    
    # Create 'current' symlink
    log_info "Creating 'current' symlink..."
    run_cmd ln -sfn "$RELEASE_DIR" "$MCP_INSTALL_DIR/current"
    
    # Create version.json
    local VERSION_JSON="$MCP_INSTALL_DIR/version.json"
    if [ "$DRY_RUN" = false ]; then
        cat > "$VERSION_JSON" << EOF
{
  "current_version": "$VERSION",
  "previous_good_version": null,
  "installed_versions": ["$VERSION"],
  "last_update": {
    "timestamp": "$(date -Iseconds)",
    "status": "succeeded",
    "from_version": null,
    "to_version": "$VERSION"
  }
}
EOF
    fi
    run_cmd chown "$MCP_USER:$MCP_GROUP" "$VERSION_JSON"
    
    log_success "MCP Raspi Server v$VERSION installed"
}

install_config() {
    log_info "Installing configuration..."
    
    local CONFIG_FILE="$MCP_CONFIG_DIR/config.yml"
    local SECRETS_FILE="$MCP_CONFIG_DIR/secrets.env"
    
    # Install config template
    if [ ! -f "$CONFIG_FILE" ]; then
        if [ -f "$SCRIPT_DIR/config.example.yml" ]; then
            run_cmd cp "$SCRIPT_DIR/config.example.yml" "$CONFIG_FILE"
        else
            log_warn "config.example.yml not found, creating minimal config"
            if [ "$DRY_RUN" = false ]; then
                cat > "$CONFIG_FILE" << 'EOF'
# MCP Raspi Server Configuration
# See docs/14-configuration-reference-and-examples.md for full options

version: "1.0.0"

server:
  listen: "127.0.0.1:8000"
  log_level: "info"

security:
  mode: "local"

logging:
  app_log_path: "/var/log/mcp-raspi/app.log"
  audit_log_path: "/var/log/mcp-raspi/audit.log"
  level: "info"

ipc:
  socket_path: "/run/mcp-raspi/ops-agent.sock"

testing:
  sandbox_mode: "partial"
EOF
            fi
        fi
        run_cmd chown root:"$MCP_GROUP" "$CONFIG_FILE"
        run_cmd chmod 640 "$CONFIG_FILE"
        log_success "Configuration installed to $CONFIG_FILE"
    else
        log_info "Configuration already exists at $CONFIG_FILE"
    fi
    
    # Create secrets file
    if [ ! -f "$SECRETS_FILE" ]; then
        if [ "$DRY_RUN" = false ]; then
            cat > "$SECRETS_FILE" << 'EOF'
# MCP Raspi Secrets
# This file contains sensitive configuration values.
# Do NOT commit this file to version control!

# Cloudflare Access settings (if using Cloudflare)
# MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__TEAM_DOMAIN=your-team.cloudflareaccess.com
# MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__AUDIENCE_TAG=your-audience-tag

# Update credentials (if using private package index)
# PIP_INDEX_URL=https://user:token@private.pypi.example.com/simple/
EOF
        fi
        run_cmd chown root:root "$SECRETS_FILE"
        run_cmd chmod 600 "$SECRETS_FILE"
        log_success "Secrets file created at $SECRETS_FILE"
    else
        log_info "Secrets file already exists at $SECRETS_FILE"
    fi
}

install_systemd_services() {
    log_info "Installing systemd services..."
    
    local SYSTEMD_DIR="/etc/systemd/system"
    
    # Copy service files
    if [ -f "$SCRIPT_DIR/systemd/mcp-raspi-server.service" ]; then
        run_cmd cp "$SCRIPT_DIR/systemd/mcp-raspi-server.service" "$SYSTEMD_DIR/"
    else
        log_warn "mcp-raspi-server.service not found in $SCRIPT_DIR/systemd/"
    fi
    
    if [ -f "$SCRIPT_DIR/systemd/raspi-ops-agent.service" ]; then
        run_cmd cp "$SCRIPT_DIR/systemd/raspi-ops-agent.service" "$SYSTEMD_DIR/"
    else
        log_warn "raspi-ops-agent.service not found in $SCRIPT_DIR/systemd/"
    fi
    
    # Reload systemd
    run_cmd systemctl daemon-reload
    
    # Enable services
    log_info "Enabling services..."
    run_cmd systemctl enable raspi-ops-agent.service
    run_cmd systemctl enable mcp-raspi-server.service
    
    log_success "Systemd services installed and enabled"
}

start_services() {
    log_info "Starting services..."
    
    run_cmd systemctl start raspi-ops-agent.service
    sleep 2  # Give agent time to create socket
    run_cmd systemctl start mcp-raspi-server.service
    
    # Wait a moment for services to start
    sleep 3
    
    # Check status
    if systemctl is-active --quiet raspi-ops-agent.service; then
        log_success "raspi-ops-agent is running"
    else
        log_error "raspi-ops-agent failed to start"
        log_info "Check logs with: journalctl -u raspi-ops-agent"
    fi
    
    if systemctl is-active --quiet mcp-raspi-server.service; then
        log_success "mcp-raspi-server is running"
    else
        log_error "mcp-raspi-server failed to start"
        log_info "Check logs with: journalctl -u mcp-raspi-server"
    fi
}

verify_installation() {
    log_info "Verifying installation..."
    
    local ERRORS=0
    
    # Check user exists
    if id "$MCP_USER" &>/dev/null; then
        log_success "User '$MCP_USER' exists"
    else
        log_error "User '$MCP_USER' not found"
        ((ERRORS++))
    fi
    
    # Check directories
    for DIR in "$MCP_INSTALL_DIR" "$MCP_CONFIG_DIR" "$MCP_LOG_DIR" "$MCP_DATA_DIR"; do
        if [ -d "$DIR" ]; then
            log_success "Directory $DIR exists"
        else
            log_error "Directory $DIR not found"
            ((ERRORS++))
        fi
    done
    
    # Check current symlink
    if [ -L "$MCP_INSTALL_DIR/current" ]; then
        log_success "Current version symlink exists"
    else
        log_error "Current version symlink not found"
        ((ERRORS++))
    fi
    
    # Check config
    if [ -f "$MCP_CONFIG_DIR/config.yml" ]; then
        log_success "Configuration file exists"
    else
        log_error "Configuration file not found"
        ((ERRORS++))
    fi
    
    # Check virtual environment
    if [ -f "$MCP_INSTALL_DIR/current/venv/bin/python" ]; then
        log_success "Virtual environment exists"
    else
        log_error "Virtual environment not found"
        ((ERRORS++))
    fi
    
    if [ $ERRORS -eq 0 ]; then
        log_success "Installation verification passed"
        return 0
    else
        log_error "Installation verification failed with $ERRORS errors"
        return 1
    fi
}

print_summary() {
    echo
    echo "============================================================================="
    echo "Installation Summary"
    echo "============================================================================="
    echo
    echo "Installation directory: $MCP_INSTALL_DIR"
    echo "Configuration:          $MCP_CONFIG_DIR/config.yml"
    echo "Secrets:                $MCP_CONFIG_DIR/secrets.env"
    echo "Logs:                   $MCP_LOG_DIR/"
    echo "Data:                   $MCP_DATA_DIR/"
    echo
    echo "Services:"
    echo "  - raspi-ops-agent.service (privileged operations)"
    echo "  - mcp-raspi-server.service (MCP server)"
    echo
    echo "Useful commands:"
    echo "  systemctl status mcp-raspi-server     # Check server status"
    echo "  systemctl status raspi-ops-agent      # Check agent status"
    echo "  journalctl -u mcp-raspi-server -f     # Follow server logs"
    echo "  journalctl -u raspi-ops-agent -f      # Follow agent logs"
    echo
    echo "Next steps:"
    echo "  1. Edit $MCP_CONFIG_DIR/config.yml to customize settings"
    echo "  2. Edit $MCP_CONFIG_DIR/secrets.env for sensitive values"
    echo "  3. (Optional) Set up Cloudflare Tunnel for secure internet access"
    echo "     See: docs/cloudflare-tunnel-setup.md"
    echo
    echo "============================================================================="
}

print_help() {
    echo "MCP Raspi Server Installation Script"
    echo
    echo "Usage: sudo ./install.sh [OPTIONS]"
    echo
    echo "Options:"
    echo "  --dry-run       Show what would be done without making changes"
    echo "  --skip-deps     Skip system dependency installation"
    echo "  --skip-service  Skip systemd service installation"
    echo "  --version VER   Install specific version (default: latest)"
    echo "  --channel CH    Update channel: stable, beta, dev (default: stable)"
    echo "  --help          Show this help message"
    echo
    echo "Examples:"
    echo "  sudo ./install.sh                     # Standard installation"
    echo "  sudo ./install.sh --dry-run           # Preview without changes"
    echo "  sudo ./install.sh --version 1.0.0     # Install specific version"
    echo
}

# =============================================================================
# Main
# =============================================================================

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --skip-deps)
                SKIP_DEPS=true
                shift
                ;;
            --skip-service)
                SKIP_SERVICE=true
                shift
                ;;
            --version)
                MCP_VERSION="$2"
                shift 2
                ;;
            --channel)
                MCP_CHANNEL="$2"
                shift 2
                ;;
            --help|-h)
                print_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                print_help
                exit 1
                ;;
        esac
    done
    
    echo "============================================================================="
    echo "MCP Raspi Server Installation"
    echo "============================================================================="
    echo
    
    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN MODE - No changes will be made"
        echo
    fi
    
    # Pre-installation checks
    check_root
    check_os
    check_python
    check_disk_space
    
    echo
    log_info "Starting installation..."
    echo
    
    # Installation steps
    if [ "$SKIP_DEPS" = false ]; then
        install_system_deps
    fi
    
    create_user
    create_directories
    set_permissions
    install_mcp_server
    install_config
    
    if [ "$SKIP_SERVICE" = false ]; then
        install_systemd_services
        
        if [ "$DRY_RUN" = false ]; then
            start_services
        fi
    fi
    
    # Verification
    echo
    if [ "$DRY_RUN" = false ]; then
        verify_installation
    fi
    
    # Summary
    print_summary
    
    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN COMPLETE - No changes were made"
    else
        log_success "Installation complete!"
    fi
}

main "$@"
