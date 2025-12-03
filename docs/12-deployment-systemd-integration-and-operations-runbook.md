# 12. Deployment, Systemd Integration & Operations Runbook

## 1. Document Purpose

- Describe deployment options and runtime modes for the Raspberry Pi MCP Server.
- Define how the server integrates with `systemd` on Raspberry Pi OS.
- Provide an operations runbook for day‑to‑day management and troubleshooting.

This document is aligned with:

- Platform constraints (document 03).
- Architecture (document 02).
- Self‑update design (document 10).
- Security/OAuth (document 04).
- Logging and diagnostics (document 09).
- Configuration reference (document 14).

## 2. Deployment Overview

### 2.1 Deployment Targets

- Raspberry Pi devices running Raspberry Pi OS:
  - Pi 2/3/3+/4/5/Zero 2W (see document 03 for details).
- Requirements:
  - Network connectivity (LAN/Wi‑Fi).
  - Sufficient storage for:
    - MCP server installation.
    - Logs and metrics data.
  - A user with administrative privileges (sudo/root) for setup.

### 2.2 Components

- `mcp-raspi-server`:
  - Non‑privileged MCP server process.
- `raspi-ops-agent`:
  - Privileged operations agent process, accessed via Unix domain socket IPC.
- Configuration and secret files:
  - `/etc/mcp-raspi/config.yml` – main configuration (see document 14).
  - `/etc/mcp-raspi/secrets.env` – sensitive values (tokens, credentials).
- Log directory:
  - `/var/log/mcp-raspi/` – application and audit logs.
- State and data directories:
  - Self‑update and version metadata:
    - `/var/lib/mcp-raspi/version.json` (see document 10).
  - Metrics data (optional, document 06):
    - `/var/lib/mcp-raspi/metrics/`.
- Release directories (Python package deployment, document 10 §3):
  - MCP install root:
    - `/opt/mcp-raspi/`.
  - Release directories:
    - `/opt/mcp-raspi/releases/<version>/`.
  - Current version symlink:
    - `/opt/mcp-raspi/current` (used by `systemd` units).

## 3. Installation Steps (Python Package Deployment)

This section assumes the Phase 1 layout recommended in document 10:

- Python package managed by `uv`.
- Releases in `/opt/mcp-raspi/releases/`.
- `current` symlink points to active release.

### 3.1 Prerequisites

- OS:
  - Raspberry Pi OS (32‑ or 64‑bit) within supported versions (document 03).
- Runtime:
  - System Python 3.11+ (or compatible).
  - `uv` installed (see document 13).
- Permissions:
  - Sudo/root access for installation and `systemd` configuration.
- Network:
  - Access to PyPI or an internal Python index (or mirror).
  - For private indices:
    - Ensure credentials and URLs are configured in `secrets.env` and `config.yml`.

### 3.2 Initial Install Procedure

1. **Prepare system and dependencies**
   - Optionally update system packages and security updates:
     - `sudo apt update && sudo apt upgrade`
   - Install Python/runtime if needed.

2. **Create system user and directories**
   - Create a non‑privileged system user:

     ```bash
     sudo useradd --system --no-create-home --shell /usr/sbin/nologin mcp
     ```

   - Create directories:
     - `/etc/mcp-raspi/` – configuration and secrets.
     - `/var/log/mcp-raspi/` – application and audit logs.
     - `/var/lib/mcp-raspi/` – version metadata, metrics, and other state.
     - `/opt/mcp-raspi/releases/` – release directories.
     - `/opt/mcp-raspi/current` – symlink to current release.
   - Set permissions (example):

     ```bash
     sudo chown -R mcp:mcp /var/log/mcp-raspi /var/lib/mcp-raspi /opt/mcp-raspi
     sudo chown root:mcp /etc/mcp-raspi
     sudo chmod 750 /etc/mcp-raspi
     sudo chmod 600 /etc/mcp-raspi/secrets.env
     ```

3. **Install MCP server (initial version)**
   - Choose an initial version (for example `1.0.0`).
   - Create the release directory and virtual environment:

     ```bash
     sudo mkdir -p /opt/mcp-raspi/releases/1.0.0
     sudo python3 -m venv /opt/mcp-raspi/releases/1.0.0/venv
     ```

   - Install `mcp-raspi` in that environment (using `uv` or `pip` as appropriate):

     ```bash
     sudo /opt/mcp-raspi/releases/1.0.0/venv/bin/pip install --upgrade pip
     sudo /opt/mcp-raspi/releases/1.0.0/venv/bin/pip install mcp-raspi
     ```

   - Initialize `current` symlink:

     ```bash
     sudo ln -sfn /opt/mcp-raspi/releases/1.0.0 /opt/mcp-raspi/current
     ```

   - In a `uv`-managed deployment:
     - This layout can be adapted by:
       - Using `uv` to manage environments.
       - Pointing `current/venv` to the appropriate `uv` environment.

4. **Configure MCP server**
   - Copy provided configuration template to `/etc/mcp-raspi/config.yml` and edit:
     - Server listen address and port.
     - Cloudflare Tunnel/OAuth configuration.
     - Enabled/disabled tools and safety levels.
     - Logging paths and levels.
     - Self‑update and OS update policies (`updates.*`).
   - Place sensitive information into `/etc/mcp-raspi/secrets.env`:
     - For example:
       - OAuth secrets.
       - Private PyPI credentials.
       - Cloudflare tokens.
   - Ensure `systemd` units reference `secrets.env` via `EnvironmentFile=`.

5. **Install `systemd` unit files**
   - Copy `mcp-raspi-server.service` and `raspi-ops-agent.service` from the repository to:
     - `/etc/systemd/system/`.
   - Update the `ExecStart` paths to point to:
     - `/opt/mcp-raspi/current/venv/bin/python -m mcp_raspi.server.app`.
     - `/opt/mcp-raspi/current/venv/bin/python -m mcp_raspi_ops.main`.
   - Reload `systemd`:

     ```bash
     sudo systemctl daemon-reload
     ```

6. **Enable and start services**

```bash
sudo systemctl enable mcp-raspi-server raspi-ops-agent
sudo systemctl start mcp-raspi-server raspi-ops-agent
```

- Verify status:

```bash
systemctl status mcp-raspi-server
systemctl status raspi-ops-agent
```

## 4. Systemd Integration

### 4.1 Service Separation

Use two separate systemd services:

- `mcp-raspi-server.service`:
  - Runs the MCP server under the `mcp` user (non‑privileged).
  - Handles JSON‑RPC over MCP, config loading, logging, and tool routing.
- `raspi-ops-agent.service`:
  - Runs the privileged operations agent.
  - Listens on a Unix domain socket (for example `/run/mcp-raspi/ops-agent.sock`).
  - Performs hardware and OS operations requested via IPC.

This separation:

- Enforces least privilege.
- Restricts the privileged surface area.

### 4.2 Example `mcp-raspi-server.service`

Example unit file (to be adapted in code/config):

```ini
[Unit]
Description=MCP Raspi Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mcp
Group=mcp
EnvironmentFile=/etc/mcp-raspi/secrets.env
WorkingDirectory=/opt/mcp-raspi/current
ExecStart=/opt/mcp-raspi/current/venv/bin/python -m mcp_raspi.server.app
Restart=on-failure
RestartSec=3
TimeoutStartSec=30
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

Key considerations:

- `WorkingDirectory`:
  - Points to `current` symlink so self‑update can switch versions transparently.
- `Restart=on-failure`:
  - Combined with self‑update startup health checks (document 10), this enables auto‑recovery or rollback.

### 4.3 Example `raspi-ops-agent.service`

Example unit file:

```ini
[Unit]
Description=MCP Raspi Privileged Ops Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=/etc/mcp-raspi/secrets.env
WorkingDirectory=/opt/mcp-raspi/current
ExecStart=/opt/mcp-raspi/current/venv/bin/python -m mcp_raspi_ops.main
Restart=on-failure
RestartSec=3
RuntimeDirectory=mcp-raspi
RuntimeDirectoryMode=0750

[Install]
WantedBy=multi-user.target
```

Key considerations:

- `User`:
  - May be root or a constrained account with necessary privileges and group memberships.
- IPC:
  - The agent creates a Unix socket in:
    - `/run/mcp-raspi/` (via `RuntimeDirectory`).
  - File permissions:
    - Ensure `mcp` user can connect but others cannot.

### 4.4 Systemd & Self‑Update

Integration points:

- `ExecStart` uses the `current` symlink:
  - After self‑update:
    - The privileged agent switches symlink.
    - Calls `systemctl restart mcp-raspi-server` (and itself if needed).
- `TimeoutStartSec`/`Restart`:
  - Combined with health checks:
    - If a new version fails repeatedly, document 10’s rollback strategy:
      - Switches back to `previous_good_version`.
      - Restarts services.

Systemd configuration must:

- Match the directory layout and update logic in document 10.
- Be kept in sync with installation scripts and runbook instructions.

## 5. Internet Exposure, Cloudflare Tunnel & OAuth

### 5.1 Cloudflare Tunnel

When exposing MCP over the internet:

- Use Cloudflare Tunnel (`cloudflared`) to:
  - Terminate TLS.
  - Restrict access via Cloudflare Access.
  - Hide direct device IP from the public internet.

Steps (high‑level):

1. Install and configure `cloudflared` on the device:
   - Follow Cloudflare’s documentation for Raspberry Pi.
2. Create a Tunnel:
   - Map a public hostname to:
     - Local MCP endpoint (`127.0.0.1:8000` or configured port).
3. Integrate with systemd:
   - Create a `cloudflared` service for automatic startup.

Example `cloudflared` service:

```ini
[Unit]
Description=Cloudflare Tunnel for MCP Raspi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=cloudflared
ExecStart=/usr/bin/cloudflared tunnel run mcp-raspi
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Notes:

- `mcp-raspi`:
  - The Tunnel name as configured in Cloudflare.
- Permissions:
  - `cloudflared` user must:
    - Read its config and credentials.
    - Not have unnecessary system privileges.

### 5.2 Cloudflare Access & OAuth

Access control:

- In Cloudflare dashboard:
  - Enable Access protection for the MCP hostname.
  - Configure OIDC/OAuth providers:
    - For example Google, GitHub, or an enterprise IdP.
  - Define policies for users or groups allowed to connect.

MCP server integration:

- Ensure MCP server validates:
  - Cloudflare Access JWT and headers.
  - As described in documents 02 and 04.
- Configuration:
  - Supply:
    - JWKS or public key URLs.
    - Audience/issuer configuration in `config.yml` and `secrets.env`.

## 6. Operations Runbook

### 6.1 Routine Operations

Common tasks:

- Check service status:

  ```bash
  systemctl status mcp-raspi-server
  systemctl status raspi-ops-agent
  ```

- View logs:

  ```bash
  journalctl -u mcp-raspi-server
  journalctl -u raspi-ops-agent
  ```

  or:

  ```bash
  ls /var/log/mcp-raspi/
  tail -f /var/log/mcp-raspi/app.log
  tail -f /var/log/mcp-raspi/audit.log
  ```

- Use MCP tools for routine operations:
  - Check system health and metrics.
  - Inspect service/process status.
  - Use log query tools.

#### 6.1.1 Recommended Daily Checks

Daily or weekly checks:

- Use `system.get_health_snapshot`:
  - Verify CPU/memory/disk within expected ranges.
- Use `metrics.*` tools:
  - Confirm metrics sampling works if enabled.
- Inspect logs:
  - `/var/log/mcp-raspi/app.log`.
  - `/var/log/mcp-raspi/audit.log`.
  - Look for:
    - Repeated errors.
    - Warnings related to resource limits, self‑update, or security.

After changes (config or updates):

- Confirm `mcp-raspi-server` and `raspi-ops-agent`:
  - Are `active (running)`.
- Use:
  - `logs.get_recent_app_logs`.
  - `logs.get_recent_audit_logs`.
  - To check recent events.
- If self‑update is enabled:
  - Check `manage.get_server_status`:
    - Version and `last_update` information.

### 6.2 Self‑Update Operations

Trigger self‑update:

- Via MCP:
  - Call `manage.update_server`.
  - Observe returned `UpdateStatus`.
- After update:
  - Use `manage.get_server_status` to confirm:
    - New `version`.
    - `last_update.status="succeeded"`.

If update fails:

- Check logs:
  - Application and audit logs.
  - Look for network/disk/permissions/validation errors.
- If auto‑rollback occurred:
  - Confirm:
    - `version.json` reports `current_version` as the previous version.
    - `manage.get_server_status` matches.
- If not auto‑rolled back:
  - Follow manual rollback instructions in document 10 (via CLI or MCP).

#### 6.2.1 Standard Update Procedure

Suggested workflow:

1. Pre‑maintenance preparation:
   - Use `manage.get_server_status` (or CLI) to:
     - Determine current version.
     - List installed versions if available.
   - Ensure recent backups exist:
     - At least `/etc/mcp-raspi/` and `/var/lib/mcp-raspi/`.

2. Initiate update:
   - MCP tool:
     - Call `manage.update_server` with `channel` or `target_version`.
   - CLI (if provided):
     - For example:

       ```bash
       sudo mcp-raspi-update server --channel stable
       ```

       (actual CLI details depend on implementation).

3. Monitor status:
   - From `UpdateStatus`:
     - Inspect `status` (`common_status`).
   - For synchronous operations:
     - Use direct result.
   - For asynchronous/long tasks:
     - Poll `manage.get_server_status.last_update`.

4. Verify update:

- Confirm `manage.get_server_status.version` changes as expected.
- Run smoke tests (document 11 §6):
  - Health snapshots.
  - Device control (non‑destructive).
  - Log queries.

5. If update fails:

- Review logs and audit entries:
  - Identify cause (network, disk, permission, validation).
- If auto‑rollback:
  - Confirm:
    - `version.json` and `manage.get_server_status` show the previous version restored.
- If no rollback:
  - Use manual rollback per document 10.

### 6.3 Troubleshooting

Common issues and suggested steps:

- **MCP server fails to start**
  - Check configuration:
    - Ensure `config.yml` syntax is valid.
  - Inspect `systemd` logs:

    ```bash
    journalctl -u mcp-raspi-server
    ```

- **Privileged operations failing**
  - Check `raspi-ops-agent`:

    ```bash
    systemctl status raspi-ops-agent
    ```

  - Verify IPC socket:
    - Path exists (for example `/run/mcp-raspi/ops-agent.sock`).
    - Permissions allow `mcp` user access.

- **Cannot reach MCP over the internet**
  - Check Cloudflare Tunnel:
    - `systemctl status cloudflared`.
    - `journalctl -u cloudflared`.
  - Check:
    - DNS configuration.
    - Cloudflare Access policies.

- **Performance issues**
  - Use system info and metrics tools:
    - Identify CPU, memory, and disk bottlenecks.
  - Inspect logs and sampling jobs:
    - Ensure metrics sampling and logging are not overly aggressive.

#### 6.3.1 Additional Scenarios

- **Self‑update failures or repeated restarts**
  - Check `version.json`:
    - Fields such as `current_version`, `previous_good_version`, and failure counters (if used).
  - Review `last_update` fields and logs:
    - Confirm whether automatic rollback occurred.
  - Temporarily disable remote self‑updates in `AppConfig`:
    - Investigate and fix root cause before re‑enabling.

- **Excessive log disk usage**
  - Check `/var/log/mcp-raspi/` disk usage:
    - Ensure logrotate/journald rotation is functioning as expected.
  - Adjust:
    - Logging levels.
    - Rotation and retention settings (document 09).

- **Unstable Cloudflare Tunnel**
  - Use:

    ```bash
    systemctl status cloudflared
    journalctl -u cloudflared
    ```

  - Confirm:
    - Local MCP server is reachable on the LAN.
    - When remote access is down, fall back to:
      - Local network.
      - SSH.

### 6.4 Backup & Restore

#### 6.4.1 Backup Policy

Backup scope:

- Must backup:
  - `/etc/mcp-raspi/`:
    - Configuration.
    - Secrets (with appropriate handling).
  - `/var/lib/mcp-raspi/`:
    - Includes `version.json`.
    - Metrics data (if required).
- Optional:
  - `/var/log/mcp-raspi/`:
    - Depends on compliance and disk capacity.
  - Release directories:
    - `/opt/mcp-raspi/releases/`:
      - At least current and previous known good versions.

Backup frequency:

- Configuration and state:
  - At least daily.
  - Before major configuration changes or upgrades.
- Logs:
  - Based on compliance and analysis needs:
    - Use logrotate or external log shipping.

#### 6.4.2 Restore Procedure

Steps:

1. Install MCP server on a new device or clean system:
   - Follow §3 installation steps.
2. Stop services:

   ```bash
   sudo systemctl stop mcp-raspi-server raspi-ops-agent
   ```

3. Restore backups:

   ```bash
   sudo rsync -a <backup>/etc/mcp-raspi/ /etc/mcp-raspi/
   sudo rsync -a <backup>/var/lib/mcp-raspi/ /var/lib/mcp-raspi/
   # Optional:
   sudo rsync -a <backup>/opt/mcp-raspi/releases/ /opt/mcp-raspi/releases/
   ```

4. Check consistency:
   - Verify:
     - `version.json.current_version` matches the `current` symlink.
   - If not:
     - Follow rollback procedures from document 10 to:
       - Rebuild `current` symlink.
       - Correct version metadata.

5. Start services and run smoke tests:
   - Start:

     ```bash
     sudo systemctl start mcp-raspi-server raspi-ops-agent
     ```

   - Run acceptance smoke tests (document 11 §6, `docs/acceptance-checklist.md`) to:
     - Confirm system functionality and expected version.

## 7. Future Enhancements

This section lists potential enhancements once the base deployment is stable.

### 7.1 Automated Provisioning

Automation for single devices and small fleets:

- Provide installation scripts:
  - For example `install.sh`:
    - Encapsulates §3 steps:
      - Create user and directories.
      - Install `mcp-raspi`.
      - Configure `systemd` and Cloudflare Tunnel.
    - Includes:
      - Safety checks (OS version, disk space, existing installations).
      - `--dry-run` mode to preview actions.
- Provide configuration‑management roles:
  - For example Ansible roles:
    - To install, configure, and update MCP.
    - Support:
      - Idempotent execution.
      - Multi‑host deployment.
      - Alignment with self‑update policies (document 10).

### 7.2 Fleet Management & Multi‑Device Operations

For multiple Raspberry Pi devices:

- Central management:
  - Record each device’s:
    - MCP version.
    - Config summary.
    - Self‑update status (via `manage.get_server_status`).
- Phased update strategy:
  - Use orchestrators or scripts to:
    - Update devices in batches.
    - Avoid updating all devices at once.
  - Although self‑update does not implement canary/blue‑green:
    - Higher‑level tools can implement these strategies.
- Provide:
  - Example scripts/Playbooks for:
    - Batch reboot.
    - Batch self‑update.
    - Log collection.

### 7.3 Monitoring & Alerting

Enhance monitoring:

- Metrics export:
  - Expose:
    - CPU/memory/disk.
    - Self‑update status.
    - Request rates and error rates.
  - Integrate with:
    - Prometheus.
    - Grafana dashboards.
- Alerting:
  - Based on logs and metrics:
    - Repeated self‑update failures or rollbacks.
    - Sudden increase in request error rates or latencies.
    - Resource thresholds exceeded (disk, memory).
  - Delivery channels:
    - Email.
    - Chat systems (Slack, Teams, etc.).

## 8. Implementation Checklist

- Provide and maintain clear `systemd` unit templates for:
  - `mcp-raspi-server`.
  - `raspi-ops-agent`.
- Ensure deployment scripts:
  - Check prerequisites (OS version, dependencies, disk space, writable directories).
  - Surface clear error messages on failure.
- Provide Cloudflare Tunnel:
  - Example configuration.
  - Troubleshooting guidance (e.g. how to inspect `cloudflared` logs).
- Keep operations runbook sections:
  - Updated with common issues and resolutions:
    - From start‑up failures to performance issues.
- Maintain consistency between:
  - Deployment documentation.
  - Self‑update/rollback (document 10).
  - Logging/audit (document 09).
  - Security (document 04).
- For each deployment mode (Python package/APT/Git/Archive, when added):
  - Provide clear installation instructions.
  - Document caveats:
    - Self‑update behavior.
    - Testing and sandbox implications (document 11).
- Include example files in the repository:
  - `config.example.yml`:
    - With secure defaults and comments.
  - Example `systemd` units and `cloudflared` configs.
- Provide short “post‑install acceptance steps”:
  - Aligned with document 11 §6 and `docs/acceptance-checklist.md`:
    - Run system info tools.
    - Run a self‑update dry‑run scenario (if supported).
    - Run log queries.
- Integrate deployment scripts into test/CI where practical:
  - Use containers or VMs to:
    - Regularly validate that automated install scripts still work.
  - Document:
    - Which deployment steps must be performed manually.
    - Which can be fully automated via scripts or configuration management tools.


---

<!-- Merged from 12-addendum-deployment-operations-enhancements.md -->


## 1. Cloudflare Tunnel Setup (Step-by-Step)

### 1.1 Overview

Cloudflare Tunnel (`cloudflared`) enables secure internet access to the MCP server without exposing ports or using port forwarding.

**Benefits**:
- No inbound firewall rules needed
- DDoS protection via Cloudflare
- Automatic HTTPS with Cloudflare certificates
- OAuth/OIDC integration via Cloudflare Access

**Architecture**:
```
AI Assistant → Cloudflare Edge → Cloudflare Tunnel → Raspberry Pi MCP Server
  (Internet)      (Global CDN)         (Encrypted)       (Local Network)
```

### 1.2 Prerequisites

1. **Cloudflare Account**: Free or paid plan
2. **Domain Name**: Registered and using Cloudflare DNS
3. **Raspberry Pi**: Running Raspberry Pi OS with internet connection
4. **MCP Server**: Installed and operational locally

### 1.3 Step 1: Install cloudflared

```bash
# Download cloudflared for ARM64 (Pi 4/5) or ARM (Pi 3/Zero 2W)
# For ARM64 (Raspberry Pi 4, 5):
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
sudo mv cloudflared-linux-arm64 /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# For ARM (Raspberry Pi 3, Zero 2W):
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm
sudo mv cloudflared-linux-arm /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# Verify installation
cloudflared version
```

### 1.4 Step 2: Authenticate with Cloudflare

```bash
# Login to Cloudflare (opens browser for OAuth)
cloudflared tunnel login

# This creates credentials at ~/.cloudflared/cert.pem
# Copy to system location
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/cert.pem /etc/cloudflared/
```

### 1.5 Step 3: Create Cloudflare Tunnel

```bash
# Create a named tunnel
sudo cloudflared tunnel create raspi-mcp-server

# This outputs a tunnel UUID, for example:
# Tunnel credentials written to /root/.cloudflared/<UUID>.json
# Copy credentials to standard location
sudo cp /root/.cloudflared/<UUID>.json /etc/cloudflared/tunnel-credentials.json

# Note your tunnel UUID for next steps
TUNNEL_UUID="<your-tunnel-uuid>"
```

### 1.6 Step 4: Configure Tunnel

Create `/etc/cloudflared/config.yml`:

```yaml
tunnel: <your-tunnel-uuid>
credentials-file: /etc/cloudflared/tunnel-credentials.json

ingress:
  # Route mcp.yourdomain.com to local MCP server
  - hostname: mcp.yourdomain.com
    service: http://localhost:8000
    originRequest:
      noTLSVerify: false
      connectTimeout: 30s
      keepAliveConnections: 100

  # Catch-all rule (required)
  - service: http_status:404
```

**For stdio-based MCP (default)**:
If your MCP server uses stdio (not HTTP), you'll need an HTTP wrapper or use SSH:

```yaml
tunnel: <your-tunnel-uuid>
credentials-file: /etc/cloudflared/tunnel-credentials.json

ingress:
  # Route to SSH server, then use SSH to invoke MCP server
  - hostname: mcp.yourdomain.com
    service: ssh://localhost:22
    originRequest:
      noTLSVerify: true

  - service: http_status:404
```

### 1.7 Step 5: Configure DNS

```bash
# Create DNS record pointing to tunnel
sudo cloudflared tunnel route dns <your-tunnel-uuid> mcp.yourdomain.com
```

This creates a CNAME record: `mcp.yourdomain.com → <UUID>.cfargotunnel.com`

### 1.8 Step 6: Test Tunnel

```bash
# Run tunnel in foreground for testing
sudo cloudflared tunnel --config /etc/cloudflared/config.yml run

# In another terminal, test connectivity
curl -I https://mcp.yourdomain.com
```

### 1.9 Step 7: Install as systemd Service

```bash
# Install cloudflared as systemd service
sudo cloudflared service install

# Enable and start service
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Check status
sudo systemctl status cloudflared

# View logs
sudo journalctl -u cloudflared -f
```

### 1.10 Step 8: Configure Cloudflare Access (OAuth)

**In Cloudflare Dashboard**:

1. Navigate to **Zero Trust** → **Access** → **Applications**
2. Click **Add an application** → **Self-hosted**
3. Configure application:
   - **Application name**: Raspberry Pi MCP Server
   - **Session duration**: 24 hours
   - **Application domain**: `mcp.yourdomain.com`

4. Add access policy:
   - **Policy name**: Allow authenticated users
   - **Action**: Allow
   - **Include**: Emails ending in `@yourdomain.com` (or specific emails)

5. Configure identity provider:
   - **Zero Trust** → **Settings** → **Authentication**
   - Add provider: Google, GitHub, Azure AD, etc.
   - Configure OAuth credentials

6. Get JWT public key:
   - Navigate to **Zero Trust** → **Settings** → **General**
   - Note your **Team domain**: `<team-name>.cloudflareaccess.com`
   - Public keys available at: `https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs`

### 1.11 Step 9: Configure MCP Server for Cloudflare Access

Update `/etc/mcp-raspi/config.yml`:

```yaml
security:
  auth_mode: "cloudflare_access"

  cloudflare_access:
    enabled: true
    team_domain: "<team-name>.cloudflareaccess.com"
    audience_tag: "<application-aud-from-cloudflare>"
    jwt_algorithm: "RS256"
    jwks_url: "https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs"
    jwks_cache_ttl_seconds: 3600

  # Role mapping from JWT claims
  role_mappings:
    - jwt_claim: "email"
      pattern: "admin@yourdomain.com"
      role: "admin"

    - jwt_claim: "email"
      pattern: ".*@yourdomain.com"
      role: "operator"

    - jwt_claim: "groups"
      value: "mcp-viewers"
      role: "viewer"
```

### 1.12 Step 10: Restart MCP Server

```bash
# Restart to apply new configuration
sudo systemctl restart mcp-raspi-server

# Verify it's using Cloudflare Access
sudo journalctl -u mcp-raspi-server -n 50
```

### 1.13 Testing the Complete Setup

```bash
# From external network:
# 1. Open https://mcp.yourdomain.com in browser
# 2. You should be redirected to Cloudflare Access login
# 3. Authenticate with configured identity provider
# 4. Access granted, JWT cookie set
# 5. MCP tools now accessible with JWT authentication

# Test with MCP client:
mcp-client connect https://mcp.yourdomain.com \
  --auth cloudflare \
  --cookies /path/to/cookies.txt
```

---

## 2. Backup Automation Scripts

### 2.1 Overview

Automated backups protect against data loss, failed updates, and hardware failures.

**Backup Targets**:
- Configuration files (`/etc/mcp-raspi/`)
- Metrics database (`/var/lib/mcp-raspi/metrics.db`)
- Audit logs (`/var/log/mcp-raspi/audit.log*`)
- Application logs (last 7 days)
- Version state (`/opt/mcp-raspi/current/`, `version.json`)

**Backup Destinations**:
- Local USB drive
- Network share (NFS, SMB)
- Cloud storage (S3, Google Cloud Storage, Dropbox)

### 2.2 Backup Script

```bash
#!/bin/bash
# /usr/local/bin/mcp-raspi-backup.sh
# Backup MCP Raspi Server configuration and data

set -euo pipefail

# Configuration
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/mnt/backup/mcp-raspi}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="${BACKUP_BASE_DIR}/${TIMESTAMP}"
LOG_FILE="/var/log/mcp-raspi/backup.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Create backup directory
log "Starting backup to ${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}"

# 1. Backup configuration
log "Backing up configuration..."
if [ -d "/etc/mcp-raspi" ]; then
    cp -r /etc/mcp-raspi "${BACKUP_DIR}/config"
fi

# 2. Backup metrics database (with SQLite integrity check)
log "Backing up metrics database..."
if [ -f "/var/lib/mcp-raspi/metrics.db" ]; then
    sqlite3 /var/lib/mcp-raspi/metrics.db "PRAGMA integrity_check"
    cp /var/lib/mcp-raspi/metrics.db "${BACKUP_DIR}/metrics.db"
fi

# 3. Backup audit logs
log "Backing up audit logs..."
if [ -d "/var/log/mcp-raspi" ]; then
    mkdir -p "${BACKUP_DIR}/logs"
    cp /var/log/mcp-raspi/audit.log* "${BACKUP_DIR}/logs/" 2>/dev/null || true
    # Backup recent application logs (last 7 days)
    find /var/log/mcp-raspi -name "*.log" -mtime -7 -exec cp {} "${BACKUP_DIR}/logs/" \;
fi

# 4. Backup version state
log "Backing up version state..."
if [ -f "/opt/mcp-raspi/version.json" ]; then
    cp /opt/mcp-raspi/version.json "${BACKUP_DIR}/version.json"
fi

# 5. Backup systemd units (for restore on new device)
log "Backing up systemd units..."
mkdir -p "${BACKUP_DIR}/systemd"
cp /etc/systemd/system/mcp-raspi-*.service "${BACKUP_DIR}/systemd/" 2>/dev/null || true

# 6. Export system information
log "Exporting system information..."
cat > "${BACKUP_DIR}/system-info.txt" <<EOF
Hostname: $(hostname)
Model: $(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)
Kernel: $(uname -r)
Backup Date: $(date)
MCP Version: $(cat /opt/mcp-raspi/version.json | jq -r .current_version)
EOF

# 7. Create checksums
log "Creating checksums..."
cd "${BACKUP_DIR}"
find . -type f -exec sha256sum {} \; > checksums.sha256

# 8. Compress backup
log "Compressing backup..."
cd "${BACKUP_BASE_DIR}"
tar -czf "${TIMESTAMP}.tar.gz" "${TIMESTAMP}"
BACKUP_SIZE=$(du -h "${TIMESTAMP}.tar.gz" | cut -f1)
log "Backup compressed: ${TIMESTAMP}.tar.gz (${BACKUP_SIZE})"

# 9. Remove uncompressed backup
rm -rf "${TIMESTAMP}"

# 10. Cleanup old backups
log "Cleaning up old backups (older than ${RETENTION_DAYS} days)..."
find "${BACKUP_BASE_DIR}" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete

# 11. Verify backup integrity
log "Verifying backup integrity..."
if tar -tzf "${BACKUP_BASE_DIR}/${TIMESTAMP}.tar.gz" > /dev/null; then
    log "Backup verification successful"
else
    log "ERROR: Backup verification failed!"
    exit 1
fi

log "Backup completed successfully: ${TIMESTAMP}.tar.gz"

# Optional: Upload to cloud storage (uncomment as needed)
# log "Uploading to S3..."
# aws s3 cp "${BACKUP_BASE_DIR}/${TIMESTAMP}.tar.gz" \
#     s3://my-bucket/mcp-raspi-backups/$(hostname)/

# Optional: Send notification
# curl -X POST https://hooks.slack.com/services/XXX/YYY/ZZZ \
#     -H 'Content-Type: application/json' \
#     -d "{\"text\": \"MCP Raspi backup completed: ${TIMESTAMP}.tar.gz (${BACKUP_SIZE})\"}"

exit 0
```

### 2.3 Restore Script

```bash
#!/bin/bash
# /usr/local/bin/mcp-raspi-restore.sh
# Restore MCP Raspi Server from backup

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-file.tar.gz>"
    exit 1
fi

BACKUP_FILE="$1"
RESTORE_DIR="/tmp/mcp-raspi-restore-$$"
LOG_FILE="/var/log/mcp-raspi/restore.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Verify backup exists
if [ ! -f "$BACKUP_FILE" ]; then
    log "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

log "Starting restore from ${BACKUP_FILE}"

# Extract backup
log "Extracting backup..."
mkdir -p "$RESTORE_DIR"
tar -xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

# Find the extracted directory
BACKUP_CONTENT=$(find "$RESTORE_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)

# Verify checksums
log "Verifying checksums..."
cd "$BACKUP_CONTENT"
if sha256sum -c checksums.sha256 --quiet; then
    log "Checksum verification passed"
else
    log "ERROR: Checksum verification failed!"
    exit 1
fi

# Stop services
log "Stopping MCP services..."
sudo systemctl stop mcp-raspi-server || true
sudo systemctl stop raspi-ops-agent || true

# Restore configuration
log "Restoring configuration..."
if [ -d "$BACKUP_CONTENT/config" ]; then
    sudo cp -r "$BACKUP_CONTENT/config"/* /etc/mcp-raspi/
    sudo chown -R mcp-raspi:mcp-raspi /etc/mcp-raspi
fi

# Restore metrics database
log "Restoring metrics database..."
if [ -f "$BACKUP_CONTENT/metrics.db" ]; then
    sudo mkdir -p /var/lib/mcp-raspi
    sudo cp "$BACKUP_CONTENT/metrics.db" /var/lib/mcp-raspi/metrics.db
    sudo chown mcp-raspi:mcp-raspi /var/lib/mcp-raspi/metrics.db
fi

# Restore audit logs
log "Restoring audit logs..."
if [ -d "$BACKUP_CONTENT/logs" ]; then
    sudo mkdir -p /var/log/mcp-raspi
    sudo cp "$BACKUP_CONTENT/logs"/* /var/log/mcp-raspi/
    sudo chown -R mcp-raspi:mcp-raspi /var/log/mcp-raspi
fi

# Restore version state
log "Restoring version state..."
if [ -f "$BACKUP_CONTENT/version.json" ]; then
    sudo cp "$BACKUP_CONTENT/version.json" /opt/mcp-raspi/version.json
fi

# Restore systemd units
log "Restoring systemd units..."
if [ -d "$BACKUP_CONTENT/systemd" ]; then
    sudo cp "$BACKUP_CONTENT/systemd"/* /etc/systemd/system/
    sudo systemctl daemon-reload
fi

# Start services
log "Starting MCP services..."
sudo systemctl start raspi-ops-agent
sudo systemctl start mcp-raspi-server

# Verify services
sleep 5
if sudo systemctl is-active --quiet mcp-raspi-server; then
    log "MCP server restored and running"
else
    log "WARNING: MCP server not running after restore"
fi

# Cleanup
log "Cleaning up..."
rm -rf "$RESTORE_DIR"

log "Restore completed successfully"

exit 0
```

### 2.4 Automated Backup Schedule

```bash
# Install backup script
sudo cp mcp-raspi-backup.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/mcp-raspi-backup.sh

# Create systemd timer for daily backups
cat > /etc/systemd/system/mcp-raspi-backup.service <<EOF
[Unit]
Description=MCP Raspi Server Backup
After=network.target

[Service]
Type=oneshot
Environment="BACKUP_BASE_DIR=/mnt/backup/mcp-raspi"
Environment="RETENTION_DAYS=30"
ExecStart=/usr/local/bin/mcp-raspi-backup.sh
User=root
StandardOutput=journal
StandardError=journal
EOF

cat > /etc/systemd/system/mcp-raspi-backup.timer <<EOF
[Unit]
Description=MCP Raspi Server Backup Timer
Requires=mcp-raspi-backup.service

[Timer]
OnCalendar=daily
OnCalendar=03:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable and start timer
sudo systemctl daemon-reload
sudo systemctl enable mcp-raspi-backup.timer
sudo systemctl start mcp-raspi-backup.timer

# Check timer status
sudo systemctl list-timers mcp-raspi-backup.timer
```

### 2.5 Cloud Backup Integration

#### AWS S3 Backup

```bash
# Install AWS CLI
sudo apt-get install -y awscli

# Configure AWS credentials
aws configure

# Add to backup script:
# Upload to S3 with encryption
aws s3 cp "${BACKUP_BASE_DIR}/${TIMESTAMP}.tar.gz" \
    s3://my-bucket/mcp-raspi-backups/$(hostname)/${TIMESTAMP}.tar.gz \
    --storage-class STANDARD_IA \
    --server-side-encryption AES256

# Set lifecycle policy to delete after 90 days (via AWS Console or CLI)
```

#### Dropbox Backup

```bash
# Install Dropbox Uploader
curl "https://raw.githubusercontent.com/andreafabrizi/Dropbox-Uploader/master/dropbox_uploader.sh" \
    -o /usr/local/bin/dropbox_uploader.sh
chmod +x /usr/local/bin/dropbox_uploader.sh

# Configure Dropbox (follow prompts)
/usr/local/bin/dropbox_uploader.sh

# Add to backup script:
/usr/local/bin/dropbox_uploader.sh upload \
    "${BACKUP_BASE_DIR}/${TIMESTAMP}.tar.gz" \
    /mcp-raspi-backups/$(hostname)/
```

---

## 3. Disaster Recovery Procedures

### 3.1 Disaster Scenarios & Recovery Steps

#### Scenario 1: MCP Server Won't Start

**Symptoms**:
- `systemctl status mcp-raspi-server` shows failed
- Logs show crash or error on startup

**Recovery**:

```bash
# 1. Check recent logs
sudo journalctl -u mcp-raspi-server -n 100

# 2. Try starting in debug mode
sudo /opt/mcp-raspi/current/bin/mcp-raspi-server \
    --config /etc/mcp-raspi/config.yml \
    --log-level DEBUG

# 3. If configuration error, restore from backup
sudo mcp-raspi-restore.sh /mnt/backup/mcp-raspi/latest.tar.gz

# 4. If code issue, rollback to previous version
sudo mcp-raspi-cli manage rollback

# 5. Restart services
sudo systemctl start raspi-ops-agent
sudo systemctl start mcp-raspi-server
```

#### Scenario 2: Corrupted Metrics Database

**Symptoms**:
- SQLite errors in logs
- Metrics queries failing

**Recovery**:

```bash
# 1. Stop server
sudo systemctl stop mcp-raspi-server

# 2. Check database integrity
sqlite3 /var/lib/mcp-raspi/metrics.db "PRAGMA integrity_check"

# 3. If corrupted, restore from backup
sudo cp /mnt/backup/mcp-raspi/latest/metrics.db \
    /var/lib/mcp-raspi/metrics.db

# 4. If no backup, rebuild database
sudo rm /var/lib/mcp-raspi/metrics.db
# Database will be recreated on next start

# 5. Restart server
sudo systemctl start mcp-raspi-server
```

#### Scenario 3: Failed Update (Stuck State)

**Symptoms**:
- Update in progress but not completing
- System unresponsive

**Recovery**:

```bash
# 1. Check current version state
cat /opt/mcp-raspi/version.json

# 2. Force rollback to previous_good version
sudo systemctl stop mcp-raspi-server
sudo systemctl stop raspi-ops-agent

# Manually switch symlink
cd /opt/mcp-raspi
PREVIOUS_VERSION=$(jq -r .previous_good_version version.json)
sudo rm current
sudo ln -s "releases/${PREVIOUS_VERSION}" current

# Update version.json
sudo jq '.current_version = .previous_good_version' version.json > version.json.tmp
sudo mv version.json.tmp version.json

# 3. Restart services
sudo systemctl start raspi-ops-agent
sudo systemctl start mcp-raspi-server

# 4. Verify
mcp-raspi-cli system get-info
```

#### Scenario 4: Complete SD Card Failure

**Symptoms**:
- Raspberry Pi won't boot
- Filesystem corruption

**Recovery**:

```bash
# 1. Prepare new SD card with fresh Raspberry Pi OS

# 2. Install MCP server (same version as backup)
curl -sSL https://releases.example.com/install.sh | bash

# 3. Restore from backup
scp backup-server:/backups/mcp-raspi/latest.tar.gz /tmp/
sudo mcp-raspi-restore.sh /tmp/latest.tar.gz

# 4. Verify services
sudo systemctl status mcp-raspi-server
sudo systemctl status raspi-ops-agent

# 5. Test connectivity
mcp-raspi-cli system get-info
```

#### Scenario 5: Lost Cloudflare Tunnel Credentials

**Symptoms**:
- Can't access MCP server from internet
- cloudflared authentication errors

**Recovery**:

```bash
# 1. Regenerate tunnel credentials
cloudflared tunnel login

# 2. Recreate tunnel (or use existing)
cloudflared tunnel list
# If old tunnel exists, download credentials:
cloudflared tunnel token <tunnel-uuid> > /etc/cloudflared/tunnel-credentials.json

# 3. Restart cloudflared
sudo systemctl restart cloudflared

# 4. Verify tunnel
sudo systemctl status cloudflared
cloudflared tunnel info <tunnel-uuid>
```

### 3.2 Disaster Recovery Runbook

**Recovery Time Objectives (RTO)**:
- Configuration restore: < 5 minutes
- Database restore: < 10 minutes
- Full system rebuild: < 1 hour
- SD card replacement: < 2 hours

**Recovery Point Objectives (RPO)**:
- Configuration: Last backup (daily = 24 hours max)
- Metrics data: Last backup (daily = 24 hours max)
- Audit logs: Real-time if log shipping enabled

**Runbook Steps**:

1. **Assess Situation** (2 min)
   - What failed? (service, database, hardware, network)
   - Is data accessible?
   - Are backups available?

2. **Stop Services** (1 min)
   ```bash
   sudo systemctl stop mcp-raspi-server raspi-ops-agent cloudflared
   ```

3. **Identify Recovery Path** (2 min)
   - Minor: Restart services
   - Moderate: Restore configuration
   - Major: Full restore from backup
   - Critical: Rebuild on new hardware

4. **Execute Recovery** (5-60 min)
   - Follow scenario-specific steps above
   - Verify each step before proceeding

5. **Validate** (5 min)
   ```bash
   # Check services
   sudo systemctl status mcp-raspi-server raspi-ops-agent

   # Test MCP tools
   mcp-raspi-cli system get-info
   mcp-raspi-cli system get-health

   # Check connectivity
   curl -I https://mcp.yourdomain.com
   ```

6. **Document Incident** (10 min)
   - What failed?
   - How was it detected?
   - What was the root cause?
   - How was it resolved?
   - How to prevent recurrence?

---

## 4. Fleet Management (Phase 2+)

### 4.1 Overview

Managing multiple Raspberry Pi devices as a coordinated fleet.

**Features**:
- Centralized configuration management
- Coordinated updates (rolling, canary)
- Health monitoring dashboard
- Bulk operations

### 4.2 Fleet Configuration Management

```yaml
# fleet-config.yml (stored centrally, synced to devices)

fleet:
  id: "production-sensors"
  region: "us-west"

  devices:
    - id: "pi-living-room"
      hostname: "pi-living-room.local"
      model: "pi4"
      role: "sensor"
      tags: ["indoor", "temperature", "motion"]

    - id: "pi-garage"
      hostname: "pi-garage.local"
      model: "pi3"
      role: "sensor"
      tags: ["outdoor", "camera", "door"]

  # Shared configuration (overridable per device)
  config_template:
    logging:
      level: "INFO"
      shipping:
        enabled: true
        backend: "fluent-bit"

    updates:
      schedule:
        enabled: true
        mode: "maintenance_window"
        maintenance_windows:
          - day_of_week: "sunday"
            start_time: "02:00"
            duration_minutes: 120

    security:
      auth_mode: "cloudflare_access"
```

### 4.3 Fleet Management CLI

```bash
# mcp-fleet - Fleet management CLI

# List all devices
mcp-fleet list

# Get device status
mcp-fleet status pi-living-room

# Execute command on all devices
mcp-fleet exec --all "mcp-raspi-cli system get-health"

# Execute on tagged devices
mcp-fleet exec --tag indoor "mcp-raspi-cli metrics get-snapshot"

# Deploy configuration update
mcp-fleet config deploy --file fleet-config.yml

# Initiate rolling update
mcp-fleet update --version 1.2.0 --strategy rolling --batch-size 5

# Get fleet health summary
mcp-fleet health
```

### 4.4 Fleet Health Dashboard (Phase 2+)

Web dashboard showing fleet status:

- Device list with health indicators
- Real-time metrics (CPU, temp, memory)
- Alert notifications
- Update status and history
- Configuration drift detection
- Audit log aggregation

**Technology**: Grafana + Prometheus + custom API

---

## 5. Monitoring & Alerting Integration

### 5.1 System Health Checks

```bash
# /usr/local/bin/mcp-raspi-healthcheck.sh
# Health check script for external monitoring

#!/bin/bash

# Check MCP server is running
if ! systemctl is-active --quiet mcp-raspi-server; then
    echo "CRITICAL: MCP server not running"
    exit 2
fi

# Check privileged agent is running
if ! systemctl is-active --quiet raspi-ops-agent; then
    echo "CRITICAL: Privileged agent not running"
    exit 2
fi

# Check IPC socket exists
if [ ! -S /var/run/mcp-raspi/agent.sock ]; then
    echo "WARNING: IPC socket missing"
    exit 1
fi

# Check CPU temperature
TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
TEMP_C=$((TEMP / 1000))

if [ $TEMP_C -gt 85 ]; then
    echo "CRITICAL: CPU temperature ${TEMP_C}°C > 85°C"
    exit 2
elif [ $TEMP_C -gt 75 ]; then
    echo "WARNING: CPU temperature ${TEMP_C}°C > 75°C"
    exit 1
fi

# Check disk space
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')

if [ $DISK_USAGE -gt 95 ]; then
    echo "CRITICAL: Disk usage ${DISK_USAGE}% > 95%"
    exit 2
elif [ $DISK_USAGE -gt 85 ]; then
    echo "WARNING: Disk usage ${DISK_USAGE}% > 85%"
    exit 1
fi

# Check memory usage
MEM_USAGE=$(free | awk 'NR==2 {printf "%.0f", $3/$2 * 100}')

if [ $MEM_USAGE -gt 95 ]; then
    echo "CRITICAL: Memory usage ${MEM_USAGE}% > 95%"
    exit 2
elif [ $MEM_USAGE -gt 85 ]; then
    echo "WARNING: Memory usage ${MEM_USAGE}% > 85%"
    exit 1
fi

echo "OK: All health checks passed (temp=${TEMP_C}°C, disk=${DISK_USAGE}%, mem=${MEM_USAGE}%)"
exit 0
```

### 5.2 Nagios/Icinga Integration

```ini
# /etc/nagios/nrpe.cfg (on Raspberry Pi)

command[check_mcp_server]=/usr/local/bin/mcp-raspi-healthcheck.sh
command[check_mcp_cpu_temp]=/usr/local/bin/check_cpu_temp.sh
command[check_mcp_disk]=/usr/lib/nagios/plugins/check_disk -w 85% -c 95% -p /
```

### 5.3 Uptime Monitoring

```bash
# cron job for uptime reporting (every 5 minutes)
*/5 * * * * curl -fsS --retry 3 https://hc-ping.com/<your-check-uuid> > /dev/null 2>&1
```

---

## 6. Implementation Checklist

### Phase 1 (Current)
- ✅ systemd service units
- ✅ Basic deployment procedures
- ✅ Operations runbook (common issues)
- ⚠️ **ADD**: Step-by-step Cloudflare Tunnel setup
- ⚠️ **ADD**: Automated backup scripts
- ⚠️ **ADD**: Restore procedures
- ⚠️ **ADD**: Health check scripts

### Phase 2+ (Future)
- ⏭️ Fleet management CLI and dashboard
- ⏭️ Centralized configuration management
- ⏭️ Cloud backup integration (S3, GCS)
- ⏭️ Advanced monitoring integration (Prometheus, Grafana)
- ⏭️ Automated disaster recovery testing
- ⏭️ Multi-region fleet support
- ⏭️ Configuration drift detection
- ⏭️ Automated compliance checking

---

**End of Document**

---

<!-- Merged from 12-addendum-operations-capacity-planning.md -->


## 1. Capacity Planning Guidance

### 1.1 Overview

Proper capacity planning ensures the MCP server operates reliably within the resource constraints of Raspberry Pi devices.

**Planning Dimensions**:
- Storage (SD card, metrics database, logs)
- Network bandwidth (tool requests, updates, log shipping)
- CPU (request processing, metrics collection)
- Memory (application, metrics cache, log buffers)

### 1.2 Storage Capacity Planning

#### SD Card Sizing

**Minimum Recommendations**:
- **Development**: 8GB SD card
- **Production (minimal)**: 16GB SD card
- **Production (recommended)**: 32GB SD card
- **Production (heavy logging/metrics)**: 64GB SD card

#### Storage Breakdown

**Base Installation** (~500MB):
```
/opt/mcp-raspi/
  releases/
    1.0.0/                    ~200 MB
    1.1.0/                    ~200 MB
  keys/                        ~1 MB
  version.json                 ~1 KB
```

**Configuration & State** (~10MB):
```
/etc/mcp-raspi/
  config.yml                   ~10 KB
  alerts.yml                   ~5 KB

/var/lib/mcp-raspi/
  metrics.db                   100-500 MB (depends on retention)
```

**Logs** (highly variable):
```
/var/log/mcp-raspi/
  server.log                   10-100 MB/day
  agent.log                    5-50 MB/day
  audit.log                    1-20 MB/day

With rotation (5 backups):
  Total: 80-850 MB
```

#### Metrics Database Growth

```python
# Estimate metrics database size

METRICS_PER_DEVICE = {
    "cpu.percent": 4,          # Per-core metrics (4 cores)
    "memory.used": 1,
    "memory.cached": 1,
    "disk.usage": 2,           # Root + boot partitions
    "disk.io": 2,              # Read + write
    "network.io": 4,           # eth0/wlan0 × tx/rx
    "temperature": 1,
    # Total: ~15 metrics
}

# Sampling interval
INTERVAL_SECONDS = 60

# Storage per metric per sample
BYTES_PER_SAMPLE = 24  # timestamp (8) + value (8) + overhead (8)

# Daily storage
samples_per_day = 86400 / INTERVAL_SECONDS  # 1440 samples
metrics_count = 15
daily_storage_mb = (samples_per_day * metrics_count * BYTES_PER_SAMPLE) / (1024**2)
# Result: ~0.5 MB/day

# With retention policy
retention_days = 30
total_storage_mb = daily_storage_mb * retention_days
# Result: ~15 MB for 30 days

# With indexing overhead (SQLite)
actual_storage_mb = total_storage_mb * 3  # ~45 MB

# Heavy usage (10s interval, 50 metrics)
heavy_storage_mb = (8640 * 50 * 24) / (1024**2) * 30 * 3
# Result: ~300 MB for 30 days
```

#### Configuration Examples

**Minimal Storage (16GB SD card)**:
```yaml
metrics:
  retention:
    max_age_days: 7            # 1 week retention
    max_size_mb: 50            # 50 MB limit

logging:
  file:
    max_size_mb: 50            # 50 MB per log file
    backup_count: 3            # 3 backups

updates:
  keep_versions: 2             # Current + 1 previous
```

**Standard Storage (32GB SD card)**:
```yaml
metrics:
  retention:
    max_age_days: 30           # 30 day retention
    max_size_mb: 500           # 500 MB limit

logging:
  file:
    max_size_mb: 100
    backup_count: 5

updates:
  keep_versions: 3             # Current + 2 previous
```

**Large Storage (64GB SD card)**:
```yaml
metrics:
  retention:
    max_age_days: 90           # 90 day retention
    max_size_mb: 2000          # 2 GB limit

logging:
  file:
    max_size_mb: 200
    backup_count: 10

updates:
  keep_versions: 5
```

#### Storage Monitoring

```bash
#!/bin/bash
# /usr/local/bin/mcp-raspi-storage-check.sh

# Check root filesystem usage
ROOT_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')

if [ $ROOT_USAGE -gt 90 ]; then
    echo "CRITICAL: Root filesystem $ROOT_USAGE% full"

    # Identify large files
    echo "Top 10 largest files:"
    find /var/log/mcp-raspi /var/lib/mcp-raspi -type f -exec du -h {} + | sort -rh | head -10

    # Suggest cleanup
    echo "Suggested cleanup:"
    echo "  - Reduce metrics retention: MCP_RASPI_METRICS__RETENTION__MAX_AGE_DAYS"
    echo "  - Reduce log retention: edit /etc/logrotate.d/mcp-raspi"
    echo "  - Remove old release versions"

elif [ $ROOT_USAGE -gt 80 ]; then
    echo "WARNING: Root filesystem $ROOT_USAGE% full"
fi

# Check metrics database size
METRICS_DB="/var/lib/mcp-raspi/metrics.db"
if [ -f "$METRICS_DB" ]; then
    DB_SIZE_MB=$(du -m "$METRICS_DB" | awk '{print $1}')
    MAX_SIZE_MB=$(grep "max_size_mb" /etc/mcp-raspi/config.yml | awk '{print $2}')

    echo "Metrics database: ${DB_SIZE_MB}MB / ${MAX_SIZE_MB}MB"

    if [ $DB_SIZE_MB -gt $MAX_SIZE_MB ]; then
        echo "WARNING: Metrics database exceeds configured limit"
    fi
fi
```

### 1.3 Network Capacity Planning

#### Bandwidth Requirements

**MCP Tool Requests**:
- Average request size: 500 bytes (JSON-RPC)
- Average response size: 2 KB
- Per request: ~2.5 KB round-trip

**Metrics Collection** (if using Prometheus export):
- Scrape interval: 60s
- Metrics payload: ~10 KB
- Bandwidth: ~10 KB/min = ~14.4 MB/day

**Log Shipping** (if enabled):
- Typical log rate: 100 KB/day (minimal) to 10 MB/day (heavy)
- With compression: 50 KB/day to 5 MB/day

**Updates**:
- Full package: ~200 MB (occasional)
- Delta update: ~10-50 MB (occasional)

**Monthly Bandwidth Estimate**:
```
Component                  Minimal    Typical    Heavy
MCP Requests (1K/day)      75 MB      75 MB      75 MB
Metrics Export             430 MB     430 MB     430 MB
Log Shipping               1.5 MB     45 MB      150 MB
Updates (monthly)          200 MB     200 MB     200 MB
-------------------------------------------------------
Total                      ~700 MB    ~750 MB    ~855 MB
```

**Recommendations**:
- **Home broadband**: No issues (typical: 100+ Mbps)
- **Cellular (metered)**: Consider disabling metrics export, use delta updates
- **Slow connections (< 1 Mbps)**: Increase update timeouts, reduce metrics collection frequency

#### Configuration for Limited Bandwidth

```yaml
# For cellular/metered connections

metrics:
  collection:
    interval_seconds: 300      # 5 minutes instead of 1 minute

  prometheus:
    enabled: false             # Disable metrics export

logging:
  shipping:
    enabled: false             # Disable log shipping

updates:
  delta_updates:
    enabled: true              # Use delta updates
    bandwidth_threshold_mbps: 5
```

### 1.4 CPU Capacity Planning

#### CPU Usage by Component

**Idle State**:
- MCP Server: 1-3% CPU
- Privileged Agent: 0-1% CPU
- Metrics Collection: 0-2% CPU (per interval)

**Under Load (10 requests/sec)**:
- MCP Server: 15-30% CPU (depends on tool)
- IPC Communication: 2-5% CPU
- Hardware Operations: 1-10% CPU

**CPU Budget by Device**:

| Device | Cores | Recommended Load | Max Sustained |
|--------|-------|------------------|---------------|
| Pi 5 | 4 (Cortex-A76) | < 40% | < 70% |
| Pi 4 | 4 (Cortex-A72) | < 50% | < 80% |
| Pi 3 | 4 (Cortex-A53) | < 60% | < 90% |
| Zero 2W | 4 (Cortex-A53) | < 70% | < 95% |

**CPU-Intensive Operations**:
- Camera capture: 10-30% CPU for 1-2 seconds
- Metrics aggregation: 5-15% CPU
- Log compression: 10-25% CPU
- Update extraction: 20-40% CPU

**Optimization Strategies**:
1. **Reduce metrics collection frequency**: 60s → 300s
2. **Disable unused tools**: Camera, I2C if not needed
3. **Offload log shipping**: Send to remote server
4. **Schedule intensive tasks**: Updates during low-usage periods

### 1.5 Memory Capacity Planning

#### Memory Usage by Component

**Base Memory (Idle)**:
```
Component                  Pi 5/4      Pi 3       Zero 2W
Python runtime             30 MB       30 MB      30 MB
MCP Server                 40 MB       40 MB      35 MB
Privileged Agent           20 MB       20 MB      15 MB
Metrics cache              10 MB       10 MB      5 MB
---------------------------------------------------------
Total (idle)               100 MB      100 MB     85 MB
```

**Memory Under Load**:
```
Component                  Additional Memory
Active requests (×10)      20 MB
Metrics query cache        30 MB
Log buffers                10 MB
---------------------------------------------------------
Total (active)             +60 MB = 160 MB total
```

**Memory by Device**:

| Device | Total RAM | OS Usage | Available | MCP Budget |
|--------|-----------|----------|-----------|------------|
| Pi 5 (8GB) | 8192 MB | 200 MB | 7992 MB | 250 MB (comfortable) |
| Pi 4 (4GB) | 4096 MB | 200 MB | 3896 MB | 250 MB (comfortable) |
| Pi 4 (2GB) | 2048 MB | 200 MB | 1848 MB | 200 MB (tight) |
| Pi 3 (1GB) | 1024 MB | 150 MB | 874 MB | 150 MB (constrained) |
| Zero 2W | 512 MB | 100 MB | 412 MB | 100 MB (minimal) |

**Memory Limits (systemd)**:
```ini
# /etc/systemd/system/mcp-raspi-server.service

[Service]
# Pi 5/4 (4GB+): 250 MB limit
MemoryMax=250M
MemoryHigh=200M

# Pi 3 (1GB): 150 MB limit
# MemoryMax=150M
# MemoryHigh=120M

# Zero 2W (512MB): 100 MB limit
# MemoryMax=100M
# MemoryHigh=80M
```

---

## 2. Upgrade Compatibility Matrix

### 2.1 Version Compatibility Matrix

| From Version | To Version | Compatibility | Notes |
|--------------|------------|---------------|-------|
| 1.0.0 | 1.0.x | ✅ Patch | Fully compatible, no migration |
| 1.0.x | 1.1.0 | ✅ Minor | Config migration needed |
| 1.0.x | 1.2.0 | ✅ Minor | Config + DB migration |
| 1.0.x | 2.0.0 | ⚠️ Major | Breaking changes, see migration guide |
| 1.1.x | 1.2.0 | ✅ Minor | Config migration |
| Any | Latest | ✅ | Multi-step migration supported |

### 2.2 Component Compatibility

#### MCP Server ↔ Privileged Agent

**Same Version Required**: Server and agent must be same version.

| Server | Agent | Compatible | Notes |
|--------|-------|------------|-------|
| 1.0.0 | 1.0.0 | ✅ | Exact match required |
| 1.0.0 | 1.0.1 | ✅ | Patch versions compatible |
| 1.0.x | 1.1.0 | ❌ | Minor version mismatch |
| 1.1.0 | 1.0.0 | ❌ | Downgrade not supported |

**Version Mismatch Handling**:
```python
# src/mcp_raspi/ipc/client.py

async def connect_to_agent(self):
    """Connect to privileged agent with version check."""
    # Send handshake with version
    handshake = {
        "type": "handshake",
        "version": get_version(),
        "protocol_version": "1.0"
    }

    await self.send(handshake)
    response = await self.receive()

    # Check version compatibility
    agent_version = response.get("version")
    if not self._is_compatible(get_version(), agent_version):
        raise IPCVersionMismatchError(
            f"Server version {get_version()} incompatible with "
            f"agent version {agent_version}. "
            f"Please update both components to the same version."
        )
```

#### MCP Server ↔ Clients

**Protocol Versioning**: MCP protocol version negotiation.

| Client Protocol | Server Protocol | Compatible |
|-----------------|-----------------|------------|
| 1.0 | 1.0 | ✅ |
| 1.0 | 1.1 | ✅ (backward compatible) |
| 1.1 | 1.0 | ⚠️ (missing features) |
| 2.0 | 1.x | ❌ |

**Tool Versioning** (Phase 2+):
```json
{
  "method": "system.get_capabilities",
  "params": {}
}
```

Response:
```json
{
  "result": {
    "protocol_version": "1.0",
    "tools": {
      "system.get_info": {"version": "1.0", "deprecated": false},
      "gpio.write_pin": {"version": "1.1", "deprecated": false},
      "gpio.pwm_enable": {"version": "1.2", "experimental": true}
    }
  }
}
```

### 2.3 Configuration Compatibility

#### Breaking Configuration Changes

**Version 1.0.0 → 1.1.0**:
- ✅ No breaking changes
- ➕ Added: `gpio.pwm` section

**Version 1.1.0 → 1.2.0**:
- ⚠️ Renamed: `server.enable_cors` → `server.cors.enabled`
- ⚠️ Moved: `server.cors_origins` → `server.cors.allowed_origins`
- ❌ Removed: `security.jwt_secret` (auto-generated)

**Version 1.2.0 → 2.0.0** (hypothetical future):
- ❌ Removed: `auth_mode: "none"` (development only)
- ⚠️ Changed: Rate limiting defaults (stricter)
- ⚠️ Required: All GPIO whitelisting (no `enabled: false`)

#### Automatic Migration

```bash
# Automatically migrate configuration
mcp-raspi-config migrate apply --to-version 1.2.0

# Dry-run to see changes
mcp-raspi-config migrate plan --to-version 1.2.0
```

### 2.4 Database Schema Compatibility

#### Metrics Database

**Schema Version Tracking**:
```sql
CREATE TABLE schema_version (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Migration Example** (1.0.0 → 1.1.0):
```sql
-- Add new columns for disk I/O metrics
ALTER TABLE metrics ADD COLUMN disk_read_bytes INTEGER;
ALTER TABLE metrics ADD COLUMN disk_write_bytes INTEGER;

-- Create index for new columns
CREATE INDEX idx_metrics_disk_io ON metrics(timestamp, disk_read_bytes, disk_write_bytes);

-- Record migration
INSERT INTO schema_version (version) VALUES ('1.1.0');
```

**Rollback Support**:
- Keep previous database version in `/var/lib/mcp-raspi/metrics.db.backup`
- Restore on rollback

---

## 3. Migration Paths for Experimental Features

### 3.1 Overview

Features progress through maturity stages: Experimental → Beta → Stable.

**Maturity Stages**:
- **Experimental**: Early development, API may change, disabled by default
- **Beta**: Feature-complete, API mostly stable, opt-in
- **Stable**: Production-ready, API stable, enabled by default

### 3.2 Feature Maturity Matrix

| Feature | v1.0 | v1.1 | v1.2 | v2.0 |
|---------|------|------|------|------|
| **GPIO read/write** | Stable | Stable | Stable | Stable |
| **GPIO PWM** | - | Experimental | Beta | Stable |
| **I2C basic** | Stable | Stable | Stable | Stable |
| **Camera capture** | Beta | Beta | Stable | Stable |
| **Video recording** | - | - | Experimental | Beta |
| **SPI** | - | - | Experimental | Beta |
| **UART** | - | - | Experimental | Beta |
| **Metrics export** | - | Experimental | Beta | Stable |
| **Log shipping** | - | - | Experimental | Beta |
| **Delta updates** | - | - | Experimental | Beta |
| **Fleet management** | - | - | - | Experimental |

### 3.3 Enabling Experimental Features

```yaml
# /etc/mcp-raspi/config.yml

# Explicit opt-in required for experimental features
experimental_features:
  enabled: true  # Master switch

  # Individual feature flags
  features:
    - name: "gpio.pwm"
      enabled: true
      acknowledged_risks: true  # User acknowledges API may change

    - name: "camera.video_recording"
      enabled: true
      acknowledged_risks: true

    - name: "updates.delta"
      enabled: true
      acknowledged_risks: true
```

### 3.4 Migration: Experimental → Beta

**Process**:
1. **API Stabilization**: Freeze API design
2. **Documentation**: Complete API documentation
3. **Testing**: Comprehensive test coverage
4. **Deprecation Policy**: Announce any breaking changes
5. **Migration Tools**: Provide migration scripts if needed

**Example**: PWM Feature (v1.1 Experimental → v1.2 Beta)

**API Changes**:
```python
# v1.1 (Experimental)
{
  "method": "gpio.pwm_start",  # Old name
  "params": {
    "pin": 18,
    "frequency": 1000,
    "duty_cycle": 50
  }
}

# v1.2 (Beta) - Renamed for clarity
{
  "method": "gpio.pwm_enable",  # New name
  "params": {
    "pin": 18,
    "frequency_hz": 1000,       # Clarified unit
    "duty_cycle_percent": 50    # Clarified unit
  }
}
```

**Migration Path**:
```yaml
# Configuration update
gpio:
  pwm:
    # v1.1 (Experimental)
    # max_frequency: 10000

    # v1.2 (Beta) - More specific
    max_frequency_hz: 10000
    min_duty_cycle: 0.0
    max_duty_cycle: 100.0
```

**Code Migration**:
```python
# Automatic API aliasing for backward compatibility (v1.2)
@mcp_tool(name="gpio.pwm_start", deprecated=True)
async def gpio_pwm_start_legacy(pin: int, frequency: int, duty_cycle: float):
    """Legacy PWM start (deprecated in v1.2, use gpio.pwm_enable)."""
    logger.warning(
        "gpio.pwm_start is deprecated, use gpio.pwm_enable",
        deprecation_version="1.2.0",
        removal_version="2.0.0"
    )
    # Forward to new implementation
    return await gpio_pwm_enable(
        pin=pin,
        frequency_hz=frequency,
        duty_cycle_percent=duty_cycle
    )
```

### 3.5 Migration: Beta → Stable

**Process**:
1. **Feedback Collection**: Gather user feedback
2. **Bug Fixes**: Address all known issues
3. **Performance Tuning**: Optimize for production
4. **Security Review**: Complete security audit
5. **GA Release**: General availability

**Example**: Camera Capture (v1.1 Beta → v1.2 Stable)

**Changes**:
- Remove `experimental_features.camera.capture` flag requirement
- Enable by default
- Finalize API (no more changes in 1.x)
- Add to standard test suite
- Include in SLO monitoring

**User Impact**: None (already using beta API)

### 3.6 Deprecation Policy

**Deprecation Timeline**:
1. **Announce**: Deprecation notice in release notes
2. **Warning Period**: 2 minor versions (e.g., deprecated in 1.2, removed in 1.4)
3. **Removal**: Remove in next major version (2.0)

**Deprecation Warnings**:
```python
# In tool response
{
  "result": {...},
  "warnings": [
    {
      "type": "deprecation",
      "message": "gpio.pwm_start is deprecated, use gpio.pwm_enable",
      "deprecated_in": "1.2.0",
      "removed_in": "2.0.0",
      "migration_guide": "https://docs.example.com/migration/pwm"
    }
  ]
}
```

**Checking for Deprecated Usage**:
```bash
# Scan audit logs for deprecated tool usage
mcp-raspi-cli audit deprecated-usage --since 30d

# Output:
# Deprecated tool usage (last 30 days):
#   gpio.pwm_start: 150 calls (by user@example.com)
#   service.force_restart: 5 calls (by admin@example.com)
#
# Migration recommended before v2.0 upgrade.
```

---

## 4. Upgrade Testing Checklist

### 4.1 Pre-Upgrade Testing

**Development Environment**:
- [ ] Test upgrade on dev device
- [ ] Verify configuration migration
- [ ] Run full test suite
- [ ] Check for deprecation warnings
- [ ] Validate rollback procedure

**Staging Environment** (if applicable):
- [ ] Upgrade staging device
- [ ] Monitor for 24-48 hours
- [ ] Run smoke tests
- [ ] Check performance metrics
- [ ] Verify all tools functional

### 4.2 Production Upgrade Process

**Preparation**:
- [ ] Review release notes
- [ ] Check compatibility matrix
- [ ] Backup configuration and data
- [ ] Schedule maintenance window
- [ ] Notify users of downtime

**Execution**:
- [ ] Perform upgrade
- [ ] Monitor logs during upgrade
- [ ] Verify version post-upgrade
- [ ] Run health checks
- [ ] Test critical tools

**Validation**:
- [ ] All services running
- [ ] No errors in logs
- [ ] Metrics collection active
- [ ] User authentication working
- [ ] Hardware control functional

**Rollback (if needed)**:
- [ ] Documented rollback procedure ready
- [ ] Rollback tested in staging
- [ ] Time limit for rollback decision (30 min)

---

## 5. Implementation Checklist

### Phase 1 (Current)
- ✅ Basic update mechanism
- ✅ Version tracking
- ✅ Simple rollback
- ⚠️ **ADD**: Storage monitoring
- ⚠️ **ADD**: Version compatibility checks
- ⚠️ **ADD**: Configuration migration tool

### Phase 2+ (Future)
- ⏭️ Capacity planning dashboard
- ⏭️ Automated capacity alerts
- ⏭️ Comprehensive compatibility matrix tool
- ⏭️ Feature flag management UI
- ⏭️ Automated upgrade testing
- ⏭️ Canary upgrade deployments
- ⏭️ Automated rollback on failure

---

**End of Document**
