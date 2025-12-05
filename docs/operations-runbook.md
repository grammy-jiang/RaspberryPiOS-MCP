# Operations Runbook

This runbook provides operational procedures for managing and troubleshooting the Raspberry Pi MCP Server in production environments.

## Table of Contents

1. [Service Management](#1-service-management)
2. [Log Management](#2-log-management)
3. [Configuration Management](#3-configuration-management)
4. [Backup and Recovery](#4-backup-and-recovery)
5. [Update Procedures](#5-update-procedures)
6. [Performance Monitoring](#6-performance-monitoring)
7. [Common Issues](#7-common-issues)
8. [Emergency Procedures](#8-emergency-procedures)

---

## 1. Service Management

### Starting Services

```bash
# Start both services (agent first, then server)
sudo systemctl start raspi-ops-agent
sudo systemctl start mcp-raspi-server

# Or use a single command
sudo systemctl start raspi-ops-agent mcp-raspi-server
```

### Stopping Services

```bash
# Stop in reverse order
sudo systemctl stop mcp-raspi-server
sudo systemctl stop raspi-ops-agent
```

### Restarting Services

```bash
# Restart specific service
sudo systemctl restart mcp-raspi-server

# Restart both (dependency order handled automatically)
sudo systemctl restart raspi-ops-agent mcp-raspi-server
```

### Checking Status

```bash
# Check both services
sudo systemctl status mcp-raspi-server
sudo systemctl status raspi-ops-agent

# Quick status check
systemctl is-active mcp-raspi-server raspi-ops-agent
```

### Enabling/Disabling Auto-Start

```bash
# Enable auto-start on boot
sudo systemctl enable mcp-raspi-server raspi-ops-agent

# Disable auto-start
sudo systemctl disable mcp-raspi-server raspi-ops-agent
```

---

## 2. Log Management

### Log Locations

| Log Type | Location | Description |
|----------|----------|-------------|
| Application | `/var/log/mcp-raspi/app.log` | General application logs |
| Audit | `/var/log/mcp-raspi/audit.log` | Security and access logs |
| Agent | `/var/log/mcp-raspi/agent.log` | Privileged agent logs |
| Systemd | `journalctl -u <service>` | Service startup/errors |

### Viewing Logs

```bash
# Follow application logs in real-time
tail -f /var/log/mcp-raspi/app.log

# Follow audit logs
tail -f /var/log/mcp-raspi/audit.log

# View recent systemd logs
journalctl -u mcp-raspi-server -n 100

# Follow systemd logs in real-time
journalctl -u mcp-raspi-server -f

# View logs from both services
journalctl -u mcp-raspi-server -u raspi-ops-agent -f
```

### Searching Logs

```bash
# Search for errors
grep -i error /var/log/mcp-raspi/app.log

# Search for specific tool calls
grep "tool_call" /var/log/mcp-raspi/audit.log

# Search by date range
journalctl -u mcp-raspi-server --since "2024-01-01" --until "2024-01-02"

# Search for authentication events
grep -i "auth\|login\|jwt" /var/log/mcp-raspi/audit.log
```

### Log Rotation

Logs are automatically rotated based on configuration. Manual rotation:

```bash
# Force log rotation
sudo logrotate -f /etc/logrotate.d/mcp-raspi

# Check rotation status
ls -la /var/log/mcp-raspi/
```

### Log Retention

Configure retention in `/etc/mcp-raspi/config.yml`:

```yaml
logging:
  max_bytes: 104857600  # 100 MB per file
  backup_count: 5       # Keep 5 rotated files
  retention_days: 30    # Delete after 30 days
```

---

## 3. Configuration Management

### Configuration Files

| File | Purpose | Permissions |
|------|---------|-------------|
| `/etc/mcp-raspi/config.yml` | Main configuration | `640` (root:mcp-raspi) |
| `/etc/mcp-raspi/secrets.env` | Sensitive values | `600` (root:root) |

### Viewing Configuration

```bash
# View current configuration
cat /etc/mcp-raspi/config.yml

# Check for syntax errors
python3 -c "import yaml; yaml.safe_load(open('/etc/mcp-raspi/config.yml'))"
```

### Editing Configuration

```bash
# Edit main config
sudo nano /etc/mcp-raspi/config.yml

# Edit secrets
sudo nano /etc/mcp-raspi/secrets.env
```

### Applying Configuration Changes

Most changes require service restart:

```bash
# Restart to apply changes
sudo systemctl restart mcp-raspi-server

# For agent-specific changes
sudo systemctl restart raspi-ops-agent
```

### Configuration Backup

```bash
# Backup configuration
sudo cp /etc/mcp-raspi/config.yml /etc/mcp-raspi/config.yml.backup.$(date +%Y%m%d)

# Restore configuration
sudo cp /etc/mcp-raspi/config.yml.backup.20240101 /etc/mcp-raspi/config.yml
```

---

## 4. Backup and Recovery

### What to Backup

| Directory | Contains | Priority |
|-----------|----------|----------|
| `/etc/mcp-raspi/` | Configuration | **Critical** |
| `/var/lib/mcp-raspi/` | Metrics DB, state | **High** |
| `/var/log/mcp-raspi/` | Logs | Medium |
| `/opt/mcp-raspi/version.json` | Version state | High |

### Manual Backup

```bash
# Create backup directory
BACKUP_DIR="/backup/mcp-raspi/$(date +%Y%m%d)"
sudo mkdir -p "$BACKUP_DIR"

# Backup configuration
sudo cp -r /etc/mcp-raspi "$BACKUP_DIR/config"

# Backup data
sudo cp -r /var/lib/mcp-raspi "$BACKUP_DIR/data"

# Backup version state
sudo cp /opt/mcp-raspi/version.json "$BACKUP_DIR/"

# Create archive
cd /backup/mcp-raspi
sudo tar -czf "backup-$(date +%Y%m%d).tar.gz" "$(date +%Y%m%d)"
```

### Automated Backup Script

Create `/usr/local/bin/mcp-backup.sh`:

```bash
#!/bin/bash
BACKUP_BASE="/backup/mcp-raspi"
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_BASE/$DATE"

mkdir -p "$BACKUP_DIR"
cp -r /etc/mcp-raspi "$BACKUP_DIR/config"
cp -r /var/lib/mcp-raspi "$BACKUP_DIR/data"
cp /opt/mcp-raspi/version.json "$BACKUP_DIR/"

# Compress
tar -czf "$BACKUP_BASE/$DATE.tar.gz" -C "$BACKUP_BASE" "$DATE"
rm -rf "$BACKUP_DIR"

# Clean old backups (keep last 30)
find "$BACKUP_BASE" -name "*.tar.gz" -mtime +30 -delete
```

Schedule with cron:

```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/mcp-backup.sh
```

### Recovery Procedure

```bash
# 1. Stop services
sudo systemctl stop mcp-raspi-server raspi-ops-agent

# 2. Extract backup
cd /tmp
tar -xzf /backup/mcp-raspi/backup-20240101.tar.gz

# 3. Restore configuration
sudo cp -r /tmp/20240101/config/* /etc/mcp-raspi/

# 4. Restore data
sudo cp -r /tmp/20240101/data/* /var/lib/mcp-raspi/

# 5. Fix permissions
sudo chown -R mcp-raspi:mcp-raspi /var/lib/mcp-raspi
sudo chown root:mcp-raspi /etc/mcp-raspi/*
sudo chmod 640 /etc/mcp-raspi/config.yml
sudo chmod 600 /etc/mcp-raspi/secrets.env

# 6. Start services
sudo systemctl start raspi-ops-agent mcp-raspi-server

# 7. Verify
systemctl status mcp-raspi-server
```

---

## 5. Update Procedures

### Checking Current Version

```bash
# Check installed version
cat /opt/mcp-raspi/version.json

# Check Python package version
/opt/mcp-raspi/current/venv/bin/pip show mcp-raspi
```

### Standard Update Procedure

```bash
# 1. Backup first
sudo /usr/local/bin/mcp-backup.sh

# 2. Stop services
sudo systemctl stop mcp-raspi-server raspi-ops-agent

# 3. Update package
/opt/mcp-raspi/current/venv/bin/pip install --upgrade mcp-raspi

# 4. Start services
sudo systemctl start raspi-ops-agent mcp-raspi-server

# 5. Verify
systemctl status mcp-raspi-server
```

### Rollback Procedure

If an update fails:

```bash
# 1. Stop services
sudo systemctl stop mcp-raspi-server raspi-ops-agent

# 2. Check available versions
cat /opt/mcp-raspi/version.json

# 3. Switch to previous version (if using symlink versioning)
cd /opt/mcp-raspi
sudo rm current
sudo ln -s releases/1.0.0 current  # Previous version

# 4. Update version.json
sudo cat > /opt/mcp-raspi/version.json << EOF
{
  "current_version": "1.0.0",
  "previous_good_version": null,
  "last_update": {
    "status": "rolled_back",
    "timestamp": "$(date -Iseconds)"
  }
}
EOF

# 5. Start services
sudo systemctl start raspi-ops-agent mcp-raspi-server
```

---

## 6. Performance Monitoring

### System Health Check

```bash
# CPU, memory, disk overview
htop
# or
top -b -n 1 | head -20

# Disk usage
df -h /

# Memory usage
free -m

# CPU temperature
vcgencmd measure_temp
```

### MCP Server Health

```bash
# Check if server is responding
curl -s http://localhost:8000/health || echo "Server not responding"

# Check IPC socket
ls -la /run/mcp-raspi/ops-agent.sock

# Check resource usage of services
systemctl status mcp-raspi-server --no-pager
ps aux | grep mcp
```

### Metrics Database Health

```bash
# Check database size
du -h /var/lib/mcp-raspi/metrics/metrics.db

# Check database integrity
sqlite3 /var/lib/mcp-raspi/metrics/metrics.db "PRAGMA integrity_check;"

# Count metrics records
sqlite3 /var/lib/mcp-raspi/metrics/metrics.db "SELECT COUNT(*) FROM metrics;"
```

### Daily Health Check Script

```bash
#!/bin/bash
echo "=== MCP Raspi Health Check ==="
echo "Date: $(date)"
echo ""

# Services
echo "--- Services ---"
systemctl is-active --quiet mcp-raspi-server && echo "MCP Server: OK" || echo "MCP Server: FAILED"
systemctl is-active --quiet raspi-ops-agent && echo "Ops Agent: OK" || echo "Ops Agent: FAILED"

# System resources
echo ""
echo "--- System Resources ---"
echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print 100 - $8}')% used"
echo "Memory: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')"
echo "Disk: $(df / | tail -1 | awk '{print $5}')"
echo "Temp: $(vcgencmd measure_temp | cut -d= -f2)"

# Logs
echo ""
echo "--- Recent Errors ---"
journalctl -u mcp-raspi-server --since "24 hours ago" -p err --no-pager | tail -5
```

---

## 7. Common Issues

See [troubleshooting.md](troubleshooting.md) for detailed troubleshooting procedures.

### Quick Fixes

| Problem | Quick Fix |
|---------|-----------|
| Server won't start | `sudo journalctl -u mcp-raspi-server -n 50` |
| IPC connection failed | Restart agent: `sudo systemctl restart raspi-ops-agent` |
| Permission denied | Check ownership: `ls -la /var/lib/mcp-raspi` |
| Config syntax error | Validate: `python3 -c "import yaml; yaml.safe_load(open('/etc/mcp-raspi/config.yml'))"` |
| High memory usage | Restart services; check metrics retention |
| Disk full | Clear old logs: `sudo find /var/log/mcp-raspi -mtime +7 -delete` |

---

## 8. Emergency Procedures

### Service Crash Loop

```bash
# 1. Stop all services
sudo systemctl stop mcp-raspi-server raspi-ops-agent

# 2. Check logs for crash cause
sudo journalctl -u mcp-raspi-server -n 100
sudo journalctl -u raspi-ops-agent -n 100

# 3. Start in sandbox mode
sudo sed -i 's/sandbox_mode:.*/sandbox_mode: "full"/' /etc/mcp-raspi/config.yml

# 4. Start services
sudo systemctl start raspi-ops-agent mcp-raspi-server

# 5. Debug and fix issue

# 6. Restore normal mode
sudo sed -i 's/sandbox_mode:.*/sandbox_mode: "disabled"/' /etc/mcp-raspi/config.yml
sudo systemctl restart mcp-raspi-server
```

### Database Corruption

```bash
# 1. Stop services
sudo systemctl stop mcp-raspi-server

# 2. Backup corrupted database
sudo mv /var/lib/mcp-raspi/metrics/metrics.db /var/lib/mcp-raspi/metrics/metrics.db.corrupted

# 3. Restore from backup (if available)
sudo cp /backup/latest/data/metrics/metrics.db /var/lib/mcp-raspi/metrics/

# 4. Or create fresh database (loses data)
# The server will create a new one on startup

# 5. Fix permissions
sudo chown mcp-raspi:mcp-raspi /var/lib/mcp-raspi/metrics/metrics.db

# 6. Start services
sudo systemctl start mcp-raspi-server
```

### Complete System Recovery

```bash
# 1. Fresh install
sudo ./deployment/install.sh

# 2. Restore configuration from backup
sudo cp /backup/latest/config/* /etc/mcp-raspi/

# 3. Restore data
sudo cp -r /backup/latest/data/* /var/lib/mcp-raspi/

# 4. Fix permissions
sudo chown -R mcp-raspi:mcp-raspi /var/lib/mcp-raspi

# 5. Start services
sudo systemctl start raspi-ops-agent mcp-raspi-server

# 6. Verify
sudo ./verify-installation.sh
```

### Security Incident Response

If you suspect unauthorized access:

```bash
# 1. Immediately stop services
sudo systemctl stop mcp-raspi-server raspi-ops-agent

# 2. Preserve logs for investigation
sudo cp -r /var/log/mcp-raspi /tmp/incident-logs-$(date +%Y%m%d)

# 3. Check audit logs for suspicious activity
grep -E "auth|login|permission|denied" /tmp/incident-logs-*/audit.log

# 4. Review recent tool calls
tail -1000 /var/log/mcp-raspi/audit.log

# 5. If using Cloudflare Access, check their dashboard for access logs

# 6. Rotate secrets
sudo nano /etc/mcp-raspi/secrets.env  # Update credentials

# 7. Consider revoking service tokens in Cloudflare

# 8. Restart with new credentials
sudo systemctl start raspi-ops-agent mcp-raspi-server
```

---

## Related Documentation

- [Getting Started Guide](getting-started.md)
- [Troubleshooting Guide](troubleshooting.md)
- [Cloudflare Tunnel Setup](cloudflare-tunnel-setup.md)
- [Acceptance Checklist](acceptance-checklist.md)
- [Security Design](04-security-oauth-integration-and-access-control-design.md)
