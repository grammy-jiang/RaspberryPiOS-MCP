#!/bin/bash
# =============================================================================
# MCP Raspi Server Uninstall Script
# =============================================================================
#
# This script removes the Raspberry Pi MCP Server from the system.
#
# Usage:
#   sudo ./uninstall.sh [OPTIONS]
#
# Options:
#   --dry-run       Show what would be done without making changes
#   --keep-config   Keep configuration files
#   --keep-data     Keep data files (logs, metrics)
#   --keep-user     Keep the mcp-raspi system user
#   --purge         Remove everything including config, data, and user
#   --help          Show this help message
#
# =============================================================================

set -euo pipefail

# Configuration
MCP_USER="mcp-raspi"
MCP_GROUP="mcp-raspi"
MCP_INSTALL_DIR="/opt/mcp-raspi"
MCP_CONFIG_DIR="/etc/mcp-raspi"
MCP_LOG_DIR="/var/log/mcp-raspi"
MCP_DATA_DIR="/var/lib/mcp-raspi"
MCP_RUN_DIR="/run/mcp-raspi"

# Flags
DRY_RUN=false
KEEP_CONFIG=false
KEEP_DATA=false
KEEP_USER=false
PURGE=false

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

# =============================================================================
# Uninstall Functions
# =============================================================================

stop_services() {
    log_info "Stopping services..."
    
    if systemctl is-active --quiet mcp-raspi-server.service 2>/dev/null; then
        run_cmd systemctl stop mcp-raspi-server.service
        log_success "Stopped mcp-raspi-server"
    fi
    
    if systemctl is-active --quiet raspi-ops-agent.service 2>/dev/null; then
        run_cmd systemctl stop raspi-ops-agent.service
        log_success "Stopped raspi-ops-agent"
    fi
}

disable_services() {
    log_info "Disabling services..."
    
    if systemctl is-enabled --quiet mcp-raspi-server.service 2>/dev/null; then
        run_cmd systemctl disable mcp-raspi-server.service
        log_success "Disabled mcp-raspi-server"
    fi
    
    if systemctl is-enabled --quiet raspi-ops-agent.service 2>/dev/null; then
        run_cmd systemctl disable raspi-ops-agent.service
        log_success "Disabled raspi-ops-agent"
    fi
}

remove_systemd_files() {
    log_info "Removing systemd service files..."
    
    local SYSTEMD_DIR="/etc/systemd/system"
    
    if [ -f "$SYSTEMD_DIR/mcp-raspi-server.service" ]; then
        run_cmd rm -f "$SYSTEMD_DIR/mcp-raspi-server.service"
        log_success "Removed mcp-raspi-server.service"
    fi
    
    if [ -f "$SYSTEMD_DIR/raspi-ops-agent.service" ]; then
        run_cmd rm -f "$SYSTEMD_DIR/raspi-ops-agent.service"
        log_success "Removed raspi-ops-agent.service"
    fi
    
    run_cmd systemctl daemon-reload
}

remove_installation() {
    log_info "Removing installation directory..."
    
    if [ -d "$MCP_INSTALL_DIR" ]; then
        run_cmd rm -rf "$MCP_INSTALL_DIR"
        log_success "Removed $MCP_INSTALL_DIR"
    else
        log_info "Installation directory not found"
    fi
}

remove_config() {
    if [ "$KEEP_CONFIG" = true ]; then
        log_info "Keeping configuration files (--keep-config)"
        return
    fi
    
    log_info "Removing configuration files..."
    
    if [ -d "$MCP_CONFIG_DIR" ]; then
        run_cmd rm -rf "$MCP_CONFIG_DIR"
        log_success "Removed $MCP_CONFIG_DIR"
    else
        log_info "Configuration directory not found"
    fi
}

remove_data() {
    if [ "$KEEP_DATA" = true ]; then
        log_info "Keeping data files (--keep-data)"
        return
    fi
    
    log_info "Removing data files..."
    
    if [ -d "$MCP_LOG_DIR" ]; then
        run_cmd rm -rf "$MCP_LOG_DIR"
        log_success "Removed $MCP_LOG_DIR"
    fi
    
    if [ -d "$MCP_DATA_DIR" ]; then
        run_cmd rm -rf "$MCP_DATA_DIR"
        log_success "Removed $MCP_DATA_DIR"
    fi
    
    if [ -d "$MCP_RUN_DIR" ]; then
        run_cmd rm -rf "$MCP_RUN_DIR"
        log_success "Removed $MCP_RUN_DIR"
    fi
}

remove_user() {
    if [ "$KEEP_USER" = true ]; then
        log_info "Keeping system user (--keep-user)"
        return
    fi
    
    log_info "Removing system user..."
    
    if id "$MCP_USER" &>/dev/null; then
        run_cmd userdel "$MCP_USER"
        log_success "Removed user '$MCP_USER'"
    else
        log_info "User '$MCP_USER' not found"
    fi
    
    # Remove group if it exists and is empty
    if getent group "$MCP_GROUP" &>/dev/null; then
        run_cmd groupdel "$MCP_GROUP" 2>/dev/null || true
        log_success "Removed group '$MCP_GROUP'"
    fi
}

print_help() {
    echo "MCP Raspi Server Uninstall Script"
    echo
    echo "Usage: sudo ./uninstall.sh [OPTIONS]"
    echo
    echo "Options:"
    echo "  --dry-run       Show what would be done without making changes"
    echo "  --keep-config   Keep configuration files"
    echo "  --keep-data     Keep data files (logs, metrics)"
    echo "  --keep-user     Keep the mcp-raspi system user"
    echo "  --purge         Remove everything including config, data, and user"
    echo "  --help          Show this help message"
    echo
    echo "Examples:"
    echo "  sudo ./uninstall.sh                   # Remove with prompts"
    echo "  sudo ./uninstall.sh --dry-run         # Preview without changes"
    echo "  sudo ./uninstall.sh --keep-config     # Keep configuration"
    echo "  sudo ./uninstall.sh --purge           # Complete removal"
    echo
}

confirm_uninstall() {
    if [ "$DRY_RUN" = true ]; then
        return 0
    fi
    
    echo
    log_warn "This will remove the MCP Raspi Server from your system."
    echo
    echo "The following will be removed:"
    echo "  - Systemd services"
    echo "  - Installation directory: $MCP_INSTALL_DIR"
    
    if [ "$KEEP_CONFIG" = false ]; then
        echo "  - Configuration: $MCP_CONFIG_DIR"
    fi
    
    if [ "$KEEP_DATA" = false ]; then
        echo "  - Logs: $MCP_LOG_DIR"
        echo "  - Data: $MCP_DATA_DIR"
    fi
    
    if [ "$KEEP_USER" = false ]; then
        echo "  - System user: $MCP_USER"
    fi
    
    echo
    read -p "Are you sure you want to continue? [y/N] " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi
}

print_summary() {
    echo
    echo "============================================================================="
    echo "Uninstall Complete"
    echo "============================================================================="
    echo
    
    if [ "$KEEP_CONFIG" = true ]; then
        echo "Configuration preserved at: $MCP_CONFIG_DIR"
    fi
    
    if [ "$KEEP_DATA" = true ]; then
        echo "Data preserved at:"
        echo "  - Logs: $MCP_LOG_DIR"
        echo "  - Data: $MCP_DATA_DIR"
    fi
    
    if [ "$KEEP_USER" = true ]; then
        echo "System user preserved: $MCP_USER"
    fi
    
    echo
    echo "============================================================================="
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
            --keep-config)
                KEEP_CONFIG=true
                shift
                ;;
            --keep-data)
                KEEP_DATA=true
                shift
                ;;
            --keep-user)
                KEEP_USER=true
                shift
                ;;
            --purge)
                PURGE=true
                KEEP_CONFIG=false
                KEEP_DATA=false
                KEEP_USER=false
                shift
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
    echo "MCP Raspi Server Uninstall"
    echo "============================================================================="
    echo
    
    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN MODE - No changes will be made"
        echo
    fi
    
    check_root
    confirm_uninstall
    
    echo
    log_info "Starting uninstallation..."
    echo
    
    # Uninstall steps
    stop_services
    disable_services
    remove_systemd_files
    remove_installation
    remove_config
    remove_data
    remove_user
    
    # Summary
    print_summary
    
    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN COMPLETE - No changes were made"
    else
        log_success "Uninstall complete!"
    fi
}

main "$@"
