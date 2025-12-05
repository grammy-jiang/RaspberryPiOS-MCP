# Getting Started Guide

This guide helps you get the Raspberry Pi MCP Server up and running quickly.

## Overview

The Raspberry Pi MCP Server enables AI assistants to manage and observe your Raspberry Pi devices through a standardized Model Context Protocol (MCP) interface.

**Key Features:**
- System monitoring (CPU, memory, disk, temperature)
- GPIO control for electronics projects
- I2C device communication
- Camera capture
- Service and process management
- Secure internet access via Cloudflare Tunnel

## Prerequisites

### Hardware
- Raspberry Pi 3, 4, or 5 (or Zero 2W)
- SD card with Raspberry Pi OS installed
- Network connection (Ethernet or Wi-Fi)
- Power supply

### Software
- Raspberry Pi OS (Bullseye or Bookworm, 32-bit or 64-bit)
- Python 3.11 or higher
- Internet access for package installation

## Quick Start

### 1. Download the Installation Script

```bash
# Clone the repository
git clone https://github.com/grammy-jiang/RaspberryPiOS-MCP.git
cd RaspberryPiOS-MCP

# Or download just the deployment files
wget https://raw.githubusercontent.com/grammy-jiang/RaspberryPiOS-MCP/main/deployment/install.sh
chmod +x install.sh
```

### 2. Run the Installer

```bash
# Preview what will be installed (dry run)
sudo ./deployment/install.sh --dry-run

# Run the installation
sudo ./deployment/install.sh
```

The installer will:
1. Create the `mcp-raspi` system user
2. Set up directories and permissions
3. Install the MCP server package
4. Configure systemd services
5. Start the services

### 3. Verify Installation

```bash
# Check service status
sudo systemctl status mcp-raspi-server
sudo systemctl status raspi-ops-agent

# Test local connection
curl http://localhost:8000/health
```

### 4. Configure for Your Use Case

Edit the configuration file:

```bash
sudo nano /etc/mcp-raspi/config.yml
```

Key settings to customize:

```yaml
# GPIO pins you want to control
gpio:
  allowed_pins: [17, 18, 27, 22]

# I2C devices
i2c:
  buses:
    - bus: 1
      mode: "full"
      allow_addresses: [0x48, 0x68]

# Logging level
logging:
  level: "info"
```

Restart after changes:

```bash
sudo systemctl restart mcp-raspi-server
```

## Installation Options

### Development Installation

For development and testing:

```bash
# Clone repo
git clone https://github.com/grammy-jiang/RaspberryPiOS-MCP.git
cd RaspberryPiOS-MCP

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run server locally
python -m mcp_raspi.server --config ./deployment/config.example.yml
```

### Production Installation

For production use:

```bash
# Run installer with all components
sudo ./deployment/install.sh

# Enable services to start on boot
sudo systemctl enable mcp-raspi-server raspi-ops-agent
```

## Connecting to the MCP Server

### Local Network Access

By default, the server listens on `127.0.0.1:8000` (localhost only).

To allow LAN access, edit config:

```yaml
server:
  listen: "0.0.0.0:8000"
```

**Warning:** Only do this on trusted networks!

### Internet Access via Cloudflare Tunnel

For secure internet access, set up Cloudflare Tunnel:

1. Follow the [Cloudflare Tunnel Setup Guide](cloudflare-tunnel-setup.md)
2. Configure authentication in Cloudflare Access
3. Update MCP server config for JWT validation

### Using with AI Assistants

Configure your AI assistant to connect to the MCP server:

**Claude Desktop Example:**
```json
{
  "mcpServers": {
    "raspberry-pi": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic-ai/mcp-client",
        "http://your-pi.local:8000"
      ]
    }
  }
}
```

## Available Tools

The MCP server provides these tool namespaces:

| Namespace | Description | Safety Level |
|-----------|-------------|--------------|
| `system.*` | System info, health, reboot | Read-only to Admin |
| `metrics.*` | CPU, memory, disk metrics | Read-only |
| `service.*` | Systemd service management | Safe control |
| `process.*` | Process listing and management | Safe control |
| `gpio.*` | GPIO pin control | Safe control |
| `i2c.*` | I2C device communication | Safe control |
| `camera.*` | Camera capture | Safe control |
| `logs.*` | Log viewing | Read-only |
| `manage.*` | Server management, updates | Admin |

### Example Tool Calls

**Get system information:**
```json
{
  "method": "system.get_basic_info",
  "params": {}
}
```

**Read GPIO pin:**
```json
{
  "method": "gpio.read_pin",
  "params": {
    "pin": 17
  }
}
```

**Get CPU metrics:**
```json
{
  "method": "metrics.get_snapshot",
  "params": {}
}
```

## Security

### Role-Based Access Control

Three roles with different permissions:

| Role | Allowed Levels | Description |
|------|----------------|-------------|
| `viewer` | read_only | Can only read data |
| `operator` | read_only, safe_control | Can perform safe operations |
| `admin` | all | Full access including reboot/shutdown |

### Sandbox Mode

For testing, enable sandbox mode to simulate dangerous operations:

```yaml
testing:
  sandbox_mode: "full"  # Simulates all dangerous operations
```

Options:
- `"disabled"` - Normal operation (production)
- `"partial"` - Block reboot/shutdown/updates
- `"full"` - Simulate all dangerous operations

### Authentication

**Local Mode:** No authentication (LAN only)
```yaml
security:
  mode: "local"
```

**Cloudflare Mode:** JWT validation via Cloudflare Access
```yaml
security:
  mode: "cloudflare"
  cloudflare_access:
    enabled: true
    team_domain: "your-team.cloudflareaccess.com"
    audience_tag: "your-audience-tag"
```

## Common Tasks

### Viewing Logs

```bash
# Application logs
tail -f /var/log/mcp-raspi/app.log

# Audit logs (tool calls)
tail -f /var/log/mcp-raspi/audit.log

# Systemd logs
journalctl -u mcp-raspi-server -f
```

### Restarting Services

```bash
# Restart server
sudo systemctl restart mcp-raspi-server

# Restart agent
sudo systemctl restart raspi-ops-agent

# Restart both
sudo systemctl restart raspi-ops-agent mcp-raspi-server
```

### Checking Health

```bash
# Service status
systemctl status mcp-raspi-server

# API health check
curl http://localhost:8000/health
```

### Updating

```bash
# Manual update
/opt/mcp-raspi/current/venv/bin/pip install --upgrade mcp-raspi
sudo systemctl restart mcp-raspi-server raspi-ops-agent
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u mcp-raspi-server -n 50

# Check configuration
python3 -c "import yaml; yaml.safe_load(open('/etc/mcp-raspi/config.yml'))"
```

### Permission Denied

```bash
# Fix permissions
sudo chown -R mcp-raspi:mcp-raspi /var/lib/mcp-raspi /var/log/mcp-raspi
```

### Cannot Connect

```bash
# Check if server is listening
ss -tlnp | grep 8000

# Test local connection
curl -v http://localhost:8000/health
```

See [Troubleshooting Guide](troubleshooting.md) for more solutions.

## Next Steps

1. **Configure GPIO/I2C** for your hardware project
2. **Set up Cloudflare Tunnel** for secure internet access
3. **Connect your AI assistant** to the MCP server
4. **Explore the tools** available in each namespace

## Documentation

- [Operations Runbook](operations-runbook.md) - Day-to-day operations
- [Troubleshooting Guide](troubleshooting.md) - Common issues and solutions
- [Cloudflare Tunnel Setup](cloudflare-tunnel-setup.md) - Internet exposure
- [Configuration Reference](14-configuration-reference-and-examples.md) - All config options
- [Security Design](04-security-oauth-integration-and-access-control-design.md) - Security model
- [MCP Tools Reference](05-mcp-tools-interface-and-json-schema-specification.md) - Tool specifications

## Support

- **Documentation:** [docs/](.)
- **Issues:** [GitHub Issues](https://github.com/grammy-jiang/RaspberryPiOS-MCP/issues)
- **Discussions:** [GitHub Discussions](https://github.com/grammy-jiang/RaspberryPiOS-MCP/discussions)
