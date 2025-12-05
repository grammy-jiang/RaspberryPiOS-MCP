# Troubleshooting Guide

This guide provides solutions for common issues with the Raspberry Pi MCP Server.

## Table of Contents

1. [Service Issues](#1-service-issues)
2. [Connection Issues](#2-connection-issues)
3. [Authentication Issues](#3-authentication-issues)
4. [Hardware Access Issues](#4-hardware-access-issues)
5. [Performance Issues](#5-performance-issues)
6. [Update Issues](#6-update-issues)
7. [Logging Issues](#7-logging-issues)

---

## 1. Service Issues

### MCP Server Won't Start

**Symptoms:**
- `systemctl status mcp-raspi-server` shows `failed` or `inactive`
- Server exits immediately after starting

**Diagnosis:**

```bash
# Check detailed error messages
sudo journalctl -u mcp-raspi-server -n 50

# Try running manually to see errors
/opt/mcp-raspi/current/venv/bin/python -m mcp_raspi.server --config /etc/mcp-raspi/config.yml
```

**Common Causes and Solutions:**

| Cause | Solution |
|-------|----------|
| Configuration syntax error | Run: `python3 -c "import yaml; yaml.safe_load(open('/etc/mcp-raspi/config.yml'))"` |
| Missing configuration file | Copy template: `sudo cp /opt/mcp-raspi/deployment/config.example.yml /etc/mcp-raspi/config.yml` |
| Permission denied | Fix: `sudo chown -R mcp-raspi:mcp-raspi /var/lib/mcp-raspi /var/log/mcp-raspi` |
| Port already in use | Check: `sudo lsof -i :8000` and change port in config |
| Missing Python package | Reinstall: `/opt/mcp-raspi/current/venv/bin/pip install mcp-raspi` |

### Ops Agent Won't Start

**Symptoms:**
- `systemctl status raspi-ops-agent` shows `failed`
- IPC socket not created

**Diagnosis:**

```bash
# Check logs
sudo journalctl -u raspi-ops-agent -n 50

# Check socket directory
ls -la /run/mcp-raspi/
```

**Solutions:**

```bash
# Create socket directory if missing
sudo mkdir -p /run/mcp-raspi
sudo chown root:mcp-raspi /run/mcp-raspi
sudo chmod 750 /run/mcp-raspi

# Restart agent
sudo systemctl restart raspi-ops-agent
```

### Services Keep Crashing

**Diagnosis:**

```bash
# Check for crash loop
systemctl status mcp-raspi-server
# Look for "triggered" restarts

# Check memory issues
dmesg | grep -i "killed process"
journalctl | grep -i "oom"
```

**Solutions:**

```bash
# If OOM (Out of Memory) killed:
# 1. Reduce memory limits in service file
sudo systemctl edit mcp-raspi-server
# Add: [Service]
#      MemoryMax=200M

# 2. Or reduce metrics sampling
# Edit /etc/mcp-raspi/config.yml:
# metrics:
#   sampling_interval_seconds: 120

# 3. Restart
sudo systemctl restart mcp-raspi-server
```

---

## 2. Connection Issues

### Cannot Connect to MCP Server Locally

**Diagnosis:**

```bash
# Check if server is listening
curl -v http://localhost:8000/health

# Check port binding
sudo ss -tlnp | grep 8000

# Check firewall
sudo iptables -L -n
```

**Solutions:**

```bash
# If not listening:
sudo systemctl restart mcp-raspi-server

# If firewall blocking:
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
# Or with ufw:
sudo ufw allow 8000/tcp
```

### IPC Connection Failed

**Symptoms:**
- MCP server logs: "Failed to connect to ops agent"
- Operations that require privileged access fail

**Diagnosis:**

```bash
# Check socket exists
ls -la /run/mcp-raspi/ops-agent.sock

# Check agent is running
systemctl status raspi-ops-agent

# Check socket permissions
stat /run/mcp-raspi/ops-agent.sock
```

**Solutions:**

```bash
# If socket missing, restart agent
sudo systemctl restart raspi-ops-agent

# If permission denied:
# Agent must run as root or socket needs correct group ownership
sudo systemctl restart raspi-ops-agent

# Then restart server to reconnect
sudo systemctl restart mcp-raspi-server
```

### Cannot Connect via Cloudflare Tunnel

**Diagnosis:**

```bash
# Check cloudflared status
sudo systemctl status cloudflared

# Check tunnel is connected
sudo cloudflared tunnel info raspi-mcp-server

# Check DNS resolution
dig mcp.yourdomain.com
```

**Solutions:**

```bash
# If cloudflared not running:
sudo systemctl restart cloudflared

# If tunnel config wrong:
sudo nano /etc/cloudflared/config.yml
# Verify tunnel ID and credentials-file path

# If DNS not resolving:
sudo cloudflared tunnel route dns <tunnel-uuid> mcp.yourdomain.com
```

---

## 3. Authentication Issues

### JWT Validation Failed

**Symptoms:**
- Error: "Invalid JWT" or "Token expired"
- 401/403 responses from server

**Diagnosis:**

```bash
# Check JWT validation logs
grep -i jwt /var/log/mcp-raspi/app.log | tail -20

# Verify Cloudflare Access settings
cat /etc/mcp-raspi/config.yml | grep -A 10 cloudflare_access
```

**Solutions:**

```bash
# Verify audience tag matches Cloudflare dashboard
# Go to Cloudflare Zero Trust > Access > Applications > Your App
# Copy Application Audience (AUD) Tag

# Update config:
sudo nano /etc/mcp-raspi/config.yml
# Update: security.cloudflare_access.audience_tag

# Restart server
sudo systemctl restart mcp-raspi-server
```

### Permission Denied for Tool Call

**Symptoms:**
- Error: "permission_denied" or "unauthorized"
- User can access some tools but not others

**Diagnosis:**

```bash
# Check role mapping in audit log
grep -i "role\|permission" /var/log/mcp-raspi/audit.log | tail -20

# Check user's role
# Look for JWT claims in logs
```

**Solutions:**

```bash
# Verify role mappings in config
cat /etc/mcp-raspi/config.yml | grep -A 10 role_mappings

# Update role mappings:
sudo nano /etc/mcp-raspi/config.yml
# Example:
# security:
#   role_mappings:
#     groups_to_roles:
#       "mcp-admins": "admin"
#       "your-user@email.com": "admin"

# Restart
sudo systemctl restart mcp-raspi-server
```

### Rate Limited

**Symptoms:**
- Error: "rate_limit_exceeded"
- 429 responses

**Solutions:**

```bash
# Check rate limit settings
cat /etc/mcp-raspi/config.yml | grep -A 5 rate_limiting

# Increase limits if needed:
sudo nano /etc/mcp-raspi/config.yml
# security:
#   rate_limiting:
#     default_rpm: 120  # Increase from default

# Restart
sudo systemctl restart mcp-raspi-server
```

---

## 4. Hardware Access Issues

### GPIO Access Denied

**Symptoms:**
- Error: "GPIO pin not allowed" or "permission denied"
- GPIO operations fail

**Diagnosis:**

```bash
# Check user is in gpio group
groups mcp-raspi

# Check allowed pins in config
cat /etc/mcp-raspi/config.yml | grep -A 5 gpio

# Check GPIO device permissions
ls -la /dev/gpiochip*
```

**Solutions:**

```bash
# Add user to gpio group
sudo usermod -aG gpio mcp-raspi

# Update allowed pins:
sudo nano /etc/mcp-raspi/config.yml
# gpio:
#   allowed_pins: [17, 18, 27, 22, 23, 24]

# Restart agent
sudo systemctl restart raspi-ops-agent
```

### I2C Device Not Found

**Symptoms:**
- Error: "I2C device not found"
- i2cdetect shows no devices

**Diagnosis:**

```bash
# Check I2C is enabled
sudo raspi-config nonint get_i2c

# Detect devices
sudo i2cdetect -y 1

# Check permissions
ls -la /dev/i2c-*
```

**Solutions:**

```bash
# Enable I2C
sudo raspi-config
# Interface Options > I2C > Enable

# Or via command:
sudo raspi-config nonint do_i2c 0

# Add user to i2c group
sudo usermod -aG i2c mcp-raspi

# Update I2C config:
sudo nano /etc/mcp-raspi/config.yml
# i2c:
#   buses:
#     - bus: 1
#       mode: "full"
#       allow_addresses: [0x48, 0x68]

# Reboot
sudo reboot
```

### Camera Not Working

**Symptoms:**
- Error: "Camera not available"
- Camera operations fail

**Diagnosis:**

```bash
# Check camera is enabled
sudo raspi-config nonint get_camera

# Check camera detected
vcgencmd get_camera

# Check user in video group
groups mcp-raspi
```

**Solutions:**

```bash
# Enable camera
sudo raspi-config
# Interface Options > Camera > Enable

# Add user to video group
sudo usermod -aG video mcp-raspi

# Check libcamera
libcamera-hello --list-cameras

# Restart agent
sudo systemctl restart raspi-ops-agent
```

---

## 5. Performance Issues

### High CPU Usage

**Diagnosis:**

```bash
# Check process CPU usage
top -p $(pgrep -d',' -f mcp_raspi)

# Check what's using CPU
ps aux --sort=-%cpu | head -10
```

**Solutions:**

```bash
# Reduce metrics sampling frequency
sudo nano /etc/mcp-raspi/config.yml
# metrics:
#   sampling_interval_seconds: 120  # Increase from 60

# Disable unused tools
# tools:
#   camera:
#     enabled: false

# Restart
sudo systemctl restart mcp-raspi-server
```

### High Memory Usage

**Diagnosis:**

```bash
# Check memory usage
free -m
ps aux --sort=-%mem | head -10

# Check for memory leaks over time
watch -n 60 'ps aux | grep mcp_raspi'
```

**Solutions:**

```bash
# Reduce metrics retention
sudo nano /etc/mcp-raspi/config.yml
# metrics:
#   max_retention_days: 7  # Reduce from 30

# Set memory limits in systemd
sudo systemctl edit mcp-raspi-server
# Add:
# [Service]
# MemoryMax=200M
# MemoryHigh=150M

# Restart
sudo systemctl restart mcp-raspi-server
```

### Slow Response Times

**Diagnosis:**

```bash
# Check system load
uptime

# Check disk I/O
iostat -x 1 5

# Check for slow queries
grep -i "slow\|timeout" /var/log/mcp-raspi/app.log
```

**Solutions:**

```bash
# If disk I/O is high:
# - Check SD card health
# - Consider using USB SSD

# If metrics queries slow:
# - Reduce data retention
# - Add indexes to database

# If network slow:
# - Check Cloudflare tunnel latency
# - Use local access for testing
```

---

## 6. Update Issues

### Update Failed

**Diagnosis:**

```bash
# Check update logs
grep -i "update\|upgrade" /var/log/mcp-raspi/app.log | tail -20

# Check version state
cat /opt/mcp-raspi/version.json
```

**Solutions:**

```bash
# Manual rollback
cd /opt/mcp-raspi
sudo rm current
sudo ln -s releases/1.0.0 current  # Previous version

# Update version.json
sudo nano /opt/mcp-raspi/version.json

# Restart
sudo systemctl restart raspi-ops-agent mcp-raspi-server
```

### Cannot Download Updates

**Diagnosis:**

```bash
# Check internet connectivity
ping -c 3 pypi.org

# Check pip can access PyPI
/opt/mcp-raspi/current/venv/bin/pip search mcp-raspi
```

**Solutions:**

```bash
# If DNS issues:
sudo nano /etc/resolv.conf
# Add: nameserver 8.8.8.8

# If proxy needed:
export HTTPS_PROXY=http://proxy:port
/opt/mcp-raspi/current/venv/bin/pip install --upgrade mcp-raspi
```

---

## 7. Logging Issues

### Logs Not Being Written

**Diagnosis:**

```bash
# Check log directory exists and is writable
ls -la /var/log/mcp-raspi/

# Check disk space
df -h /var/log

# Check file handles
lsof | grep mcp-raspi | wc -l
```

**Solutions:**

```bash
# Fix permissions
sudo chown -R mcp-raspi:mcp-raspi /var/log/mcp-raspi
sudo chmod 755 /var/log/mcp-raspi

# If disk full, clean old logs
sudo find /var/log/mcp-raspi -name "*.log.*" -mtime +7 -delete

# Restart
sudo systemctl restart mcp-raspi-server
```

### Log Files Growing Too Large

**Diagnosis:**

```bash
# Check log sizes
du -sh /var/log/mcp-raspi/*

# Check rotation config
cat /etc/logrotate.d/mcp-raspi
```

**Solutions:**

```bash
# Update log settings
sudo nano /etc/mcp-raspi/config.yml
# logging:
#   max_bytes: 52428800  # 50 MB
#   backup_count: 3
#   level: "info"  # Reduce from "debug"

# Force rotation
sudo logrotate -f /etc/logrotate.d/mcp-raspi

# Restart
sudo systemctl restart mcp-raspi-server
```

### Cannot Find Log Entries

**Solutions:**

```bash
# Search across all logs
grep -r "search_term" /var/log/mcp-raspi/

# Search in rotated logs (compressed)
zgrep "search_term" /var/log/mcp-raspi/*.gz

# Search systemd journal
journalctl -u mcp-raspi-server --since "1 hour ago" | grep "search_term"
```

---

## Getting Help

If you cannot resolve an issue:

1. **Collect diagnostic information:**
   ```bash
   # Create diagnostic bundle
   sudo tar -czf /tmp/mcp-diag-$(date +%Y%m%d).tar.gz \
     /etc/mcp-raspi/config.yml \
     /var/log/mcp-raspi/ \
     /opt/mcp-raspi/version.json
   ```

2. **Check documentation:**
   - [Operations Runbook](operations-runbook.md)
   - [Getting Started Guide](getting-started.md)
   - [Design Documents](12-deployment-systemd-integration-and-operations-runbook.md)

3. **Report issues:**
   - GitHub Issues: [RaspberryPiOS-MCP](https://github.com/grammy-jiang/RaspberryPiOS-MCP/issues)
   - Include: Error messages, logs, configuration (remove secrets!), Raspberry Pi model
