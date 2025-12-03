# 14. Configuration Reference & Examples

## 1. Document Purpose

- Provide a central reference for the main configuration options of the Raspberry Pi MCP Server.
- Define the structure, meaning, and defaults of the `AppConfig` Pydantic model.
- Show how configuration file(s), environment variables, and command‑line arguments combine through a layered override strategy.

This document is tightly linked to:

- 02 – High‑level architecture (config layering and `AppConfig` structure).
- 04 – Security, OAuth integration & access control (`security.*`, tool policies).
- 05 – MCP tools interface (tool naming and enabling).
- 06–09 – Module designs:
  - System/metrics/service/process/device/logging.
- 10 – Self‑update & rollback (`updates.*`).
- 11 – Testing & sandbox strategy (`testing.*`).
- 12 – Deployment & systemd integration (paths and ownership).
- 13 – Python development standards (`AppConfig` conventions and loading).

Field names and YAML structures in this document are intended to map 1:1 to the future `AppConfig` Pydantic model. Any implementation changes must be reflected here.

## 2. Configuration Layers & File Layout

### 2.1 Layers

At runtime, configuration is represented by a single `AppConfig` instance, built from multiple layered sources. Later layers override earlier ones:

1. **Built‑in defaults**
   - Defined as default values in the `AppConfig` Pydantic model.
   - Provide safe initial configuration, for example:
     - Listen on `127.0.0.1:8000`.
     - Enable only read‑only / low‑risk tools by default.
     - Disable remote self‑update and OS updates.
2. **Configuration file (YAML)**
   - Default path: `/etc/mcp-raspi/config.yml`.
   - Overridable via `--config` CLI argument (for example `./dev-config.yml` in development).
3. **Environment variables**
   - Prefix: `MCP_RASPI_`.
   - Nested fields separated by double underscores `__`:
     - `MCP_RASPI_SERVER__LISTEN=0.0.0.0:8000`
     - `MCP_RASPI_SECURITY__MODE=local`
4. **Command‑line arguments**
   - Used sparingly for high‑value overrides, for example:
     - `--config` (config file path).
     - `--log-level` (temporary log level override).
     - `--debug` (turn on debug mode).

Loading order is 1 → 2 → 3 → 4, with each subsequent layer overriding earlier values.

### 2.2 Files & Permissions

- `config.yml`:
  - Default location: `/etc/mcp-raspi/config.yml`.
  - Owner: typically `root:mcp`.
  - Permissions: `640` recommended.
- `secrets.env`:
  - Default: `/etc/mcp-raspi/secrets.env`.
  - Holds sensitive values such as:
    - Cloudflare/OAuth credentials.
    - Private index tokens.
  - Permissions: `600`, readable only by `root` or a dedicated user.
  - Referenced by systemd units via `EnvironmentFile=/etc/mcp-raspi/secrets.env`.

## 3. Top‑Level Structure

Suggested top‑level structure of `config.yml` (extend as needed):

```yaml
server:
  listen: "127.0.0.1:8000"
  log_level: "info"

security:
  mode: "cloudflare"  # or "local"
  roles: { ... }
  role_mappings: { ... }

logging:
  app_log_path: "/var/log/mcp-raspi/app.log"
  audit_log_path: "/var/log/mcp-raspi/audit.log"
  level: "info"
  log_to_stdout: true
  use_journald: false
  debug_mode: false

tools:
  # namespace-level toggles / defaults
  system:
    enabled: true
  metrics:
    enabled: true
  service:
    enabled: true
  process:
    enabled: true
  gpio:
    enabled: true
  i2c:
    enabled: true
  camera:
    enabled: true
  logs:
    enabled: true
  manage:
    enabled: true

gpio:
  allowed_pins: [17, 18, 27]

i2c:
  buses:
    - bus: 1
      mode: "full"   # or "read_only"/"disabled"
      allow_addresses: []
      deny_addresses: []

camera:
  media_root: "/var/lib/mcp-raspi/media"
  max_photos_per_minute: 30

metrics:
  storage_path: "/var/lib/mcp-raspi/metrics/metrics.db"
  sampling_interval_seconds: 30

ipc:
  socket_path: "/run/mcp-raspi/ops-agent.sock"
  request_timeout_seconds: 5

updates:
  backend: "python_package"
  package_name: "mcp-raspi"
  releases_dir: "/opt/mcp-raspi/releases"
  staging_dir: "/opt/mcp-raspi/staging"
  default_channel: "stable"
  enable_remote_server_update: false
  enable_os_update: false
  trusted_origins: []
  require_signature: false

testing:
  sandbox_mode: "partial"  # "full" | "partial" | "disabled"
```

Sections below describe each configuration group in more detail.

## 4. `server` – Server Settings

Source documents: 02 (config layer), 09 (log levels).

Example:

```yaml
server:
  listen: "127.0.0.1:8000"
  log_level: "info"
```

- `listen` (`str`)
  - Listen address and port, for example:
    - `127.0.0.1:8000` (local only).
    - `0.0.0.0:8000` (all interfaces).
  - Default: `"127.0.0.1:8000"`.
- `log_level` (`str`)
  - Initial application log level:
    - `"debug"`, `"info"`, `"warn"`, `"error"`.
  - Default: `"info"`.

Implementation note:

- `server.log_level` typically maps to:
  - The initial `logging.level`, but the `logging` section can refine settings further.

## 5. `security` – Security & Auth

Source documents: 04 (security), 02 §4.5.

Example (simplified):

```yaml
security:
  mode: "cloudflare"  # or "local"
  roles:
    viewer:
      allowed_levels: ["read_only"]
    operator:
      allowed_levels: ["read_only", "safe_control"]
    admin:
      allowed_levels: ["read_only", "safe_control", "admin"]
  role_mappings:
    groups_to_roles:
      "mcp-admins": "admin"
      "iot-ops": "operator"
```

- `mode` (`str`)
  - `"cloudflare"`:
    - Use Cloudflare Access/OAuth for authentication/authorization.
  - `"local"`:
    - Local mode (e.g. LAN‑only, static tokens, mTLS).
  - Default:
    - `"cloudflare"` for production, `"local"` for development/test.
- `roles` (`dict[str, RoleConfig]`)
  - Defines internal roles and allowed safety levels:
    - `read_only`, `safe_control`, `admin`.
- `role_mappings` (`dict`)
  - Maps external identity (e.g. JWT group claims) to internal roles:

    ```yaml
    role_mappings:
      groups_to_roles:
        "mcp-admins": "admin"
        "iot-ops": "operator"
    ```

Sensitive values:

- OAuth client IDs/secrets, Cloudflare Access tokens, and similar:
  - Should be stored in `secrets.env` or environment variables.
  - Should not be embedded directly in `config.yml`.

## 6. `logging` – Logging & Audit

Source documents: 09 (logging, observability & diagnostics).

Example:

```yaml
logging:
  app_log_path: "/var/log/mcp-raspi/app.log"
  audit_log_path: "/var/log/mcp-raspi/audit.log"
  level: "info"
  log_to_stdout: true
  use_journald: false
  debug_mode: false
  max_bytes: null
  backup_count: null
  retention_days: null
```

- `app_log_path` (`str`)
  - Application log file path.
- `audit_log_path` (`str`)
  - Audit log file path.
- `level` (`str`)
  - Log level (`"debug"`, `"info"`, `"warn"`, `"error"`).
  - Default: `"info"`.
- `log_to_stdout` (`bool`)
  - Whether to also log to stdout:
    - Useful for development and container deployments.
- `use_journald` (`bool`)
  - If true, use journald instead of writing directly to files (production option).
- `debug_mode` (`bool`)
  - Enable extra diagnostic logging:
    - Not recommended permanently in production.
- `max_bytes`, `backup_count`, `retention_days`
  - Optional rotation/retention settings:
    - Apply when using built‑in rotation.

## 7. `tools` – Tool Namespace & Policy

Source documents: 04 (authorization & tool policy), 05 (tool list), 02 §8.5.

Structure:

- Namespace level:
  - `tools.system.enabled`, `tools.metrics.enabled`, etc.
  - Control whether a given namespace is enabled.
- Tool level (optional):
  - Per‑tool policy overrides (for example rate limits for `system.reboot`).

Basic example:

```yaml
tools:
  system:
    enabled: true
  logs:
    enabled: true
  manage:
    enabled: true
```

More granular example (Phase 2+):

```yaml
tools:
  system:
    enabled: true
    tool_policies:
      system.reboot:
        required_role: "admin"
        safety_level: "admin"
        rate_limit:
          max_calls: 1
          per_seconds: 3600
```

Implementation:

- Map tool policies into a `ToolPolicyEnforcer` or similar component:
  - See document 04 for policy enforcement design.

## 8. `gpio`, `i2c`, `camera`, `power` – Device Control

Source documents: 08 (device control & safeguards), 05 (tool schemas).

### 8.1 `gpio`

```yaml
gpio:
  allowed_pins: [17, 18, 27]
  default_mode: "input"   # or "output"
  default_pull: "none"    # "none" | "up" | "down"
```

- `allowed_pins` (`list[int]`)
  - List of BCM pins that MCP is allowed to control.
  - Non‑listed pins:
    - Typically read‑only or fully blocked for writes/configuration.
- `default_mode` (`str`)
  - Default mode for unmanaged pins at startup:
    - `"input"` or `"output"`.
- `default_pull` (`str`)
  - Default pull configuration:
    - `"none"`, `"up"`, `"down"`.

### 8.2 `i2c`

```yaml
i2c:
  buses:
    - bus: 1
      mode: "full"          # "full" | "read_only" | "disabled"
      allow_addresses: []   # if empty, allow all except deny list
      deny_addresses: [0x50]  # example: EEPROM or sensitive device
```

- `buses`:
  - Per‑bus configuration:
    - `bus` (`int`):
      - Bus number (e.g. `1` → `/dev/i2c-1`).
    - `mode` (`str`):
      - Access mode: `"full"`, `"read_only"`, or `"disabled"`.
    - `allow_addresses` (`list[int]`):
      - Explicitly allowed device addresses.
    - `deny_addresses` (`list[int]`):
      - Blacklist addresses (e.g. EEPROMs).

### 8.3 `camera`

```yaml
camera:
  media_root: "/var/lib/mcp-raspi/media"
  max_photos_per_minute: 30
  enabled: true
```

- `media_root` (`str`)
  - Root directory for captured media.
  - `camera.take_photo` outputs must reside under this directory.
- `max_photos_per_minute` (`int`)
  - Simple rate limit for capture operations.
- `enabled` (`bool`)
  - Whether camera tools are enabled.

### 8.4 `power`

Optional extra guardrails for power operations:

```yaml
power:
  allow_reboot: true
  allow_shutdown: false
  min_reboot_interval_seconds: 3600
```

- `allow_reboot` / `allow_shutdown` (`bool`)
  - Additional safety toggles beyond role and tool policies:
    - Can be used to completely disable certain operations at runtime.
- `min_reboot_interval_seconds` (`int`)
  - Minimum interval between reboots:
    - Used for rate limiting power operations.

## 9. `metrics` – Metrics Storage & Sampling

Source documents: 06 (system information & metrics), 09 (metrics/logging).

```yaml
metrics:
  storage_path: "/var/lib/mcp-raspi/metrics/metrics.db"
  sampling_interval_seconds: 30
  max_retention_days: 7
```

- `storage_path` (`str`)
  - Path to metrics storage:
    - SQLite database or equivalent.
- `sampling_interval_seconds` (`int`)
  - Default interval for periodic metrics sampling jobs.
- `max_retention_days` (`int`)
  - Retention time for stored samples:
    - Data older than this may be pruned.

## 10. `ipc` – Privileged Agent IPC

Source documents: 02 §6, 08 §7.

```yaml
ipc:
  socket_path: "/run/mcp-raspi/ops-agent.sock"
  request_timeout_seconds: 5
```

- `socket_path` (`str`)
  - Unix domain socket path used by `OpsAgentClient` and `raspi-ops-agent`.
- `request_timeout_seconds` (`int`)
  - Default timeout for IPC requests.
  - Specific operations may override this with longer timeouts (e.g. reboot).

## 11. `updates` – Self‑Update & OS Update

Source documents: 10 (self‑update & rollback), 05 §8 (manage namespace).

```yaml
updates:
  backend: "python_package"   # "python_package" | "git" | "archive" | "apt"
  package_name: "mcp-raspi"
  releases_dir: "/opt/mcp-raspi/releases"
  staging_dir: "/opt/mcp-raspi/staging"
  default_channel: "stable"
  enable_remote_server_update: false
  enable_os_update: false
```

- `backend` (`str`)
  - Self‑update backend type:
    - Phase 1 recommended: `"python_package"`.
- `package_name` (`str`)
  - Python package name, default `"mcp-raspi"`.
- `releases_dir` / `staging_dir` (`str`)
  - Release and staging directory paths (see document 10).
- `default_channel` (`str`)
  - Default channel when `channel` is not set in `manage.update_server`.
- `enable_remote_server_update` (`bool`)
  - Allow remote self‑update via MCP tools.
  - Defaults to `false`, must be explicitly enabled.
- `enable_os_update` (`bool`)
  - Enable OS update tools (Phase 2+).
  - Defaults to `false`.
- `trusted_origins` (`list[str]`, optional)
  - Optional list of trusted update source base URLs (for example release servers or package indices).
  - Used by security logic (document 04) to validate update sources.
- `require_signature` (`bool`, optional)
  - If `true`, self‑update backends must enforce signature or hash verification of artifacts.
  - Defaults to `false` in Phase 1; may be set to `true` in hardened deployments.

## 12. `testing` – Sandbox & Test Settings

Source document: 11 (testing & sandbox strategy).

```yaml
testing:
  sandbox_mode: "partial"  # "full" | "partial" | "disabled"
```

- `sandbox_mode` (`str`)
  - `"full"`:
    - All high‑risk operations are simulated or no‑ops:
      - Only logs are written; no real power/OS changes.
  - `"partial"`:
    - Allow some operations (service/device control).
    - Block:
      - Shutdown.
      - OS updates.
      - Self‑updates (or treat them as dry‑run).
  - `"disabled"`:
    - Disable sandbox:
      - All operations behave as configured (subject to roles and policies).

Sandbox mode affects:

- Privileged agent handlers (documents 08, 10, 11).
- MCP server tool handlers for high‑risk tools.

## 13. Example Minimal Config

Below is an example configuration suitable for local development or tightly controlled testing:

```yaml
server:
  listen: "127.0.0.1:8000"
  log_level: "debug"

security:
  mode: "local"
  roles:
    viewer:
      allowed_levels: ["read_only"]
    admin:
      allowed_levels: ["read_only", "safe_control", "admin"]
  role_mappings:
    groups_to_roles: {}

logging:
  app_log_path: "./logs/app.log"
  audit_log_path: "./logs/audit.log"
  level: "debug"
  log_to_stdout: true
  use_journald: false
  debug_mode: true

tools:
  system:
    enabled: true
  metrics:
    enabled: true
  gpio:
    enabled: false   # device control disabled by default in local dev
  manage:
    enabled: true

ipc:
  socket_path: "/tmp/mcp-raspi-ops.sock"
  request_timeout_seconds: 5

updates:
  backend: "python_package"
  package_name: "mcp-raspi"
  releases_dir: "./releases"
  staging_dir: "./releases/staging"
  default_channel: "stable"
  enable_remote_server_update: false
  enable_os_update: false

testing:
  sandbox_mode: "full"
```

Implementation guidance:

- Use this document as the basis for implementing the `AppConfig` Pydantic model.
- Add unit tests to verify:
  - File loading.
  - Environment variable overrides.
  - CLI overrides.
  - That resulting behavior matches the expectations in this reference.

---

<!-- Merged from 14-addendum-configuration-enhancements.md -->


## 1. Environment Variable Examples

### 1.1 Overview

All configuration options can be overridden with environment variables using the `MCP_RASPI_` prefix.

**Naming Convention**:
- Prefix: `MCP_RASPI_`
- Nested sections: Double underscore `__`
- List items: Index suffix `_0`, `_1`, etc.
- Example: `config.security.auth_mode` → `MCP_RASPI_SECURITY__AUTH_MODE`

### 1.2 Common Environment Variable Examples

#### Server Configuration

```bash
# Server listen address and port
# Note: In YAML, these are combined as `server.listen: "127.0.0.1:8000"`
# Environment variables allow separate address and port for flexibility
export MCP_RASPI_SERVER__LISTEN_ADDRESS="127.0.0.1"
export MCP_RASPI_SERVER__LISTEN_PORT=8000

# Logging level
export MCP_RASPI_SERVER__LOG_LEVEL="DEBUG"

# Debug mode
export MCP_RASPI_SERVER__DEBUG=true
```

#### Security Configuration

```bash
# Authentication mode
export MCP_RASPI_SECURITY__AUTH_MODE="cloudflare_access"

# Cloudflare Access settings
export MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__ENABLED=true
export MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__TEAM_DOMAIN="myteam.cloudflareaccess.com"
export MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__AUDIENCE_TAG="abc123def456"

# Rate limiting
export MCP_RASPI_SECURITY__RATE_LIMITING__ENABLED=true
export MCP_RASPI_SECURITY__RATE_LIMITING__DEFAULT_RPM=60
```

#### GPIO Configuration

```bash
# GPIO whitelisting
export MCP_RASPI_GPIO__WHITELIST__PINS="17,27,22,23,24"
export MCP_RASPI_GPIO__WHITELIST__STRICT_MODE=true

# PWM settings
export MCP_RASPI_GPIO__PWM__MAX_FREQUENCY_HZ=10000
export MCP_RASPI_GPIO__PWM__MIN_DUTY_CYCLE=0.0
export MCP_RASPI_GPIO__PWM__MAX_DUTY_CYCLE=100.0
```

#### I2C Configuration

```bash
# I2C whitelisting
export MCP_RASPI_I2C__WHITELIST__ADDRESSES="0x48,0x68,0x76"
export MCP_RASPI_I2C__WHITELIST__BUSES="1"
export MCP_RASPI_I2C__WHITELIST__STRICT_MODE=true

# I2C rate limiting
export MCP_RASPI_I2C__RATE_LIMITING__MAX_OPERATIONS_PER_MINUTE=120
```

#### Service Management Configuration

```bash
# Service whitelisting (comma-separated)
export MCP_RASPI_SERVICE__WHITELIST__SERVICES="nginx,postgresql,redis-server"
export MCP_RASPI_SERVICE__WHITELIST__STRICT_MODE=true

# Restart safety
export MCP_RASPI_SERVICE__SAFETY__REQUIRE_CONFIRMATION=true
export MCP_RASPI_SERVICE__SAFETY__RESTART_COOLDOWN_SECONDS=60
```

#### Metrics Configuration

```bash
# Metrics collection
export MCP_RASPI_METRICS__COLLECTION__ENABLED=true
export MCP_RASPI_METRICS__COLLECTION__INTERVAL_SECONDS=60

# Metrics retention
export MCP_RASPI_METRICS__RETENTION__MAX_AGE_DAYS=30
export MCP_RASPI_METRICS__RETENTION__MAX_SIZE_MB=500
```

#### Logging Configuration

```bash
# Log levels
export MCP_RASPI_LOGGING__LEVEL="INFO"
export MCP_RASPI_LOGGING__AUDIT__LEVEL="INFO"

# Log files
export MCP_RASPI_LOGGING__FILE__PATH="/var/log/mcp-raspi/server.log"
export MCP_RASPI_LOGGING__FILE__MAX_SIZE_MB=100
export MCP_RASPI_LOGGING__FILE__BACKUP_COUNT=5

# Audit logging
export MCP_RASPI_LOGGING__AUDIT__ENABLED=true
export MCP_RASPI_LOGGING__AUDIT__FILE="/var/log/mcp-raspi/audit.log"
```

#### Update Configuration

```bash
# Update settings
export MCP_RASPI_UPDATES__AUTO_CHECK=true
export MCP_RASPI_UPDATES__AUTO_INSTALL=false
export MCP_RASPI_UPDATES__CHECK_INTERVAL_HOURS=24

# Update backend
export MCP_RASPI_UPDATES__BACKEND__TYPE="github"
export MCP_RASPI_UPDATES__BACKEND__GITHUB__REPO="myorg/mcp-raspi-server"
export MCP_RASPI_UPDATES__BACKEND__GITHUB__TOKEN="${GITHUB_TOKEN}"

# Signature verification
export MCP_RASPI_UPDATES__SIGNATURE_VERIFICATION__ENABLED=true
export MCP_RASPI_UPDATES__SIGNATURE_VERIFICATION__KEYS_PATH="/opt/mcp-raspi/keys"
```

#### Camera Configuration

```bash
# Camera settings
export MCP_RASPI_CAMERA__ENABLED=true
export MCP_RASPI_CAMERA__DEFAULT_RESOLUTION="1080p"
export MCP_RASPI_CAMERA__DEFAULT_FORMAT="jpeg"
export MCP_RASPI_CAMERA__JPEG_QUALITY=85

# Camera rate limiting
export MCP_RASPI_CAMERA__RATE_LIMITING__MAX_CAPTURES_PER_HOUR=60
export MCP_RASPI_CAMERA__RATE_LIMITING__MIN_INTERVAL_SECONDS=10
```

### 1.3 Docker/Container Environment File

```bash
# .env file for Docker/container deployment

# === Server ===
MCP_RASPI_SERVER__LISTEN_ADDRESS=0.0.0.0
MCP_RASPI_SERVER__LISTEN_PORT=8000
MCP_RASPI_SERVER__LOG_LEVEL=INFO

# === Security ===
MCP_RASPI_SECURITY__AUTH_MODE=cloudflare_access
MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__ENABLED=true
MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__TEAM_DOMAIN=${CF_TEAM_DOMAIN}
MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__AUDIENCE_TAG=${CF_AUDIENCE_TAG}

# === GPIO ===
MCP_RASPI_GPIO__WHITELIST__PINS=17,27,22,23,24,25,5,6,13,19
MCP_RASPI_GPIO__WHITELIST__STRICT_MODE=true

# === I2C ===
MCP_RASPI_I2C__WHITELIST__ADDRESSES=0x48,0x68,0x76
MCP_RASPI_I2C__WHITELIST__BUSES=1

# === Services ===
MCP_RASPI_SERVICE__WHITELIST__SERVICES=nginx,postgresql,redis-server
MCP_RASPI_SERVICE__WHITELIST__STRICT_MODE=true

# === Metrics ===
MCP_RASPI_METRICS__COLLECTION__ENABLED=true
MCP_RASPI_METRICS__COLLECTION__INTERVAL_SECONDS=60
MCP_RASPI_METRICS__RETENTION__MAX_AGE_DAYS=30

# === Logging ===
MCP_RASPI_LOGGING__LEVEL=INFO
MCP_RASPI_LOGGING__AUDIT__ENABLED=true
MCP_RASPI_LOGGING__FILE__PATH=/var/log/mcp-raspi/server.log

# === Updates ===
MCP_RASPI_UPDATES__AUTO_CHECK=true
MCP_RASPI_UPDATES__AUTO_INSTALL=false
MCP_RASPI_UPDATES__BACKEND__TYPE=github
MCP_RASPI_UPDATES__BACKEND__GITHUB__REPO=myorg/mcp-raspi-server
MCP_RASPI_UPDATES__BACKEND__GITHUB__TOKEN=${GITHUB_TOKEN}

# === Testing/Sandbox ===
MCP_RASPI_TESTING__SANDBOX_MODE=false
```

### 1.4 Systemd Environment File

```bash
# /etc/mcp-raspi/environment
# Environment file for systemd service

# Server
MCP_RASPI_SERVER__LOG_LEVEL=INFO

# Security
MCP_RASPI_SECURITY__AUTH_MODE=cloudflare_access

# GPIO (device-specific)
MCP_RASPI_GPIO__WHITELIST__PINS=17,27,22

# Logging
MCP_RASPI_LOGGING__LEVEL=INFO

# Device metadata (for fleet management)
MCP_RASPI_DEVICE__ID=pi-living-room
MCP_RASPI_DEVICE__LOCATION=Living Room
MCP_RASPI_DEVICE__TAGS=indoor,temperature,motion
```

Update systemd service to use environment file:

```ini
# /etc/systemd/system/mcp-raspi-server.service

[Service]
EnvironmentFile=/etc/mcp-raspi/environment
ExecStart=/opt/mcp-raspi/current/bin/mcp-raspi-server --config /etc/mcp-raspi/config.yml
```

---

## 2. Configuration Validation CLI

### 2.1 Overview

The `mcp-raspi-config` CLI tool validates configuration files, checks for errors, and provides migration assistance.

### 2.2 Validation Commands

```bash
# Validate current configuration
mcp-raspi-config validate

# Validate specific file
mcp-raspi-config validate --file /etc/mcp-raspi/config.yml

# Validate with environment variables
mcp-raspi-config validate --with-env

# Show merged configuration (all layers)
mcp-raspi-config show

# Show effective configuration as JSON
mcp-raspi-config show --format json

# Check for deprecated options
mcp-raspi-config check-deprecated
```

### 2.3 Implementation

```python
# src/mcp_raspi/cli/config.py

import click
import yaml
import json
from pathlib import Path
from typing import Optional
from pydantic import ValidationError

from mcp_raspi.config import AppConfig, load_config
from mcp_raspi.config.validator import ConfigValidator

@click.group()
def config_cli():
    """Configuration management commands."""
    pass

@config_cli.command()
@click.option('--file', '-f', type=click.Path(exists=True), help='Config file to validate')
@click.option('--with-env', is_flag=True, help='Include environment variables')
def validate(file: Optional[str], with_env: bool):
    """Validate configuration file."""
    try:
        if file:
            config_path = Path(file)
        else:
            config_path = Path('/etc/mcp-raspi/config.yml')

        click.echo(f"Validating configuration: {config_path}")

        # Load configuration
        if with_env:
            config = load_config(config_path)
        else:
            # Load only from file (no env vars)
            with open(config_path, 'r') as f:
                config_dict = yaml.safe_load(f)
            config = AppConfig(**config_dict)

        # Run additional validation
        validator = ConfigValidator(config)
        issues = validator.validate_all()

        if not issues:
            click.secho("✓ Configuration is valid", fg='green')
            return 0
        else:
            click.secho(f"✗ Found {len(issues)} issue(s):", fg='red')
            for issue in issues:
                click.echo(f"  [{issue.severity}] {issue.path}: {issue.message}")
            return 1

    except ValidationError as e:
        click.secho("✗ Configuration validation failed:", fg='red')
        for error in e.errors():
            loc = " → ".join(str(l) for l in error['loc'])
            click.echo(f"  {loc}: {error['msg']}")
        return 1

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg='red')
        return 1

@config_cli.command()
@click.option('--file', '-f', type=click.Path(exists=True), help='Config file')
@click.option('--format', type=click.Choice(['yaml', 'json']), default='yaml')
@click.option('--with-env', is_flag=True, help='Include environment variables')
def show(file: Optional[str], format: str, with_env: bool):
    """Show effective configuration."""
    try:
        if file:
            config_path = Path(file)
        else:
            config_path = Path('/etc/mcp-raspi/config.yml')

        # Load configuration (with or without env)
        config = load_config(config_path) if with_env else AppConfig()

        # Convert to dict
        config_dict = config.model_dump()

        # Output in requested format
        if format == 'json':
            click.echo(json.dumps(config_dict, indent=2))
        else:
            click.echo(yaml.dump(config_dict, default_flow_style=False))

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg='red')
        return 1

@config_cli.command()
@click.option('--file', '-f', type=click.Path(exists=True), help='Config file')
def check_deprecated(file: Optional[str]):
    """Check for deprecated configuration options."""
    try:
        if file:
            config_path = Path(file)
        else:
            config_path = Path('/etc/mcp-raspi/config.yml')

        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f)

        # Check for deprecated options
        deprecated = find_deprecated_options(config_dict)

        if not deprecated:
            click.secho("✓ No deprecated options found", fg='green')
            return 0
        else:
            click.secho(f"⚠ Found {len(deprecated)} deprecated option(s):", fg='yellow')
            for dep in deprecated:
                click.echo(f"  {dep['path']}: {dep['message']}")
                if dep['replacement']:
                    click.echo(f"    → Use: {dep['replacement']}")
            return 0

    except Exception as e:
        click.secho(f"✗ Error: {e}", fg='red')
        return 1

def find_deprecated_options(config: dict) -> list:
    """Find deprecated configuration options."""
    deprecated = []

    # Example deprecated options (update as needed)
    deprecations = {
        'server.enable_cors': {
            'message': 'Deprecated in v1.2.0',
            'replacement': 'server.cors.enabled'
        },
        'security.jwt_secret': {
            'message': 'Deprecated in v1.1.0 - JWT secrets now auto-generated',
            'replacement': None
        },
    }

    def check_path(obj, path=""):
        """Recursively check for deprecated paths."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if current_path in deprecations:
                    deprecated.append({
                        'path': current_path,
                        'message': deprecations[current_path]['message'],
                        'replacement': deprecations[current_path]['replacement']
                    })
                check_path(value, current_path)

    check_path(config)
    return deprecated

class ConfigValidator:
    """Advanced configuration validator."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.issues = []

    def validate_all(self) -> list:
        """Run all validation checks."""
        self.validate_gpio_pins()
        self.validate_i2c_addresses()
        self.validate_services()
        self.validate_security()
        self.validate_resources()
        return self.issues

    def validate_gpio_pins(self):
        """Validate GPIO pin configuration."""
        if not self.config.gpio.whitelist.enabled:
            return

        valid_pins = set(range(2, 28))  # BCM GPIO pins
        for pin in self.config.gpio.whitelist.pins:
            if pin not in valid_pins:
                self.issues.append(ValidationIssue(
                    severity="error",
                    path="gpio.whitelist.pins",
                    message=f"Invalid GPIO pin: {pin} (valid: 2-27)"
                ))

    def validate_i2c_addresses(self):
        """Validate I2C addresses."""
        if not self.config.i2c.whitelist.enabled:
            return

        for addr in self.config.i2c.whitelist.addresses:
            if not (0x00 <= addr <= 0x7F):
                self.issues.append(ValidationIssue(
                    severity="error",
                    path="i2c.whitelist.addresses",
                    message=f"Invalid I2C address: 0x{addr:02X} (valid: 0x00-0x7F)"
                ))

    def validate_services(self):
        """Validate service configuration."""
        if not self.config.service.whitelist.enabled:
            return

        # Check for commonly misspelled service names
        common_services = {
            'nginx': 'nginx',
            'postgres': 'postgresql',
            'redis': 'redis-server',
        }

        for service in self.config.service.whitelist.services:
            if service in common_services and service != common_services[service]:
                self.issues.append(ValidationIssue(
                    severity="warning",
                    path="service.whitelist.services",
                    message=f"Service '{service}' should be '{common_services[service]}'"
                ))

    def validate_security(self):
        """Validate security configuration."""
        if self.config.security.auth_mode == "cloudflare_access":
            if not self.config.security.cloudflare_access.enabled:
                self.issues.append(ValidationIssue(
                    severity="error",
                    path="security",
                    message="auth_mode is 'cloudflare_access' but cloudflare_access.enabled is false"
                ))

            if not self.config.security.cloudflare_access.team_domain:
                self.issues.append(ValidationIssue(
                    severity="error",
                    path="security.cloudflare_access",
                    message="team_domain is required when using cloudflare_access"
                ))

    def validate_resources(self):
        """Validate resource limits."""
        # Check metrics retention
        if self.config.metrics.retention.max_size_mb > 1000:
            self.issues.append(ValidationIssue(
                severity="warning",
                path="metrics.retention.max_size_mb",
                message=f"Large metrics database ({self.config.metrics.retention.max_size_mb}MB) may impact SD card lifespan"
            ))

        # Check log file sizes
        if self.config.logging.file.max_size_mb > 200:
            self.issues.append(ValidationIssue(
                severity="warning",
                path="logging.file.max_size_mb",
                message=f"Large log files ({self.config.logging.file.max_size_mb}MB) may consume excessive disk space"
            ))

@dataclass
class ValidationIssue:
    """Configuration validation issue."""
    severity: str  # error, warning, info
    path: str
    message: str
```

---

## 3. Configuration Migration Tool

### 3.1 Overview

The migration tool helps upgrade configuration files between versions, handling breaking changes and deprecated options.

### 3.2 Migration Commands

```bash
# Check if migration is needed
mcp-raspi-config migrate check

# Migrate configuration to current version
mcp-raspi-config migrate apply

# Migrate with backup
mcp-raspi-config migrate apply --backup

# Migrate specific file
mcp-raspi-config migrate apply --file /etc/mcp-raspi/config.yml --to-version 1.2.0

# Show migration plan (dry-run)
mcp-raspi-config migrate plan
```

### 3.3 Implementation

```python
# src/mcp_raspi/cli/migrate.py

from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import yaml
import shutil
from datetime import datetime

@dataclass
class Migration:
    """Configuration migration."""
    from_version: str
    to_version: str
    description: str
    changes: List[Dict[str, Any]]

class ConfigMigrator:
    """Migrates configuration between versions."""

    # Define migrations
    MIGRATIONS = [
        Migration(
            from_version="1.0.0",
            to_version="1.1.0",
            description="Add GPIO PWM settings",
            changes=[
                {
                    'type': 'add',
                    'path': 'gpio.pwm',
                    'value': {
                        'max_frequency_hz': 10000,
                        'min_duty_cycle': 0.0,
                        'max_duty_cycle': 100.0
                    }
                }
            ]
        ),
        Migration(
            from_version="1.1.0",
            to_version="1.2.0",
            description="Restructure CORS settings",
            changes=[
                {
                    'type': 'move',
                    'from_path': 'server.enable_cors',
                    'to_path': 'server.cors.enabled'
                },
                {
                    'type': 'move',
                    'from_path': 'server.cors_origins',
                    'to_path': 'server.cors.allowed_origins'
                },
                {
                    'type': 'delete',
                    'path': 'security.jwt_secret',
                    'reason': 'Auto-generated now'
                }
            ]
        ),
    ]

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def detect_version(self) -> str:
        """Detect configuration version."""
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Check for version marker
        if 'version' in config:
            return config['version']

        # Infer from presence of features
        if 'gpio' in config and 'pwm' in config['gpio']:
            return "1.1.0"
        else:
            return "1.0.0"

    def needs_migration(self, target_version: str) -> bool:
        """Check if migration is needed."""
        current_version = self.detect_version()
        return current_version != target_version

    def plan_migration(self, target_version: str) -> List[Migration]:
        """Plan migration path to target version."""
        current_version = self.detect_version()
        migrations_needed = []

        for migration in self.MIGRATIONS:
            # Check if this migration is in the upgrade path
            if self._version_in_range(current_version, migration.from_version, target_version):
                migrations_needed.append(migration)

        return migrations_needed

    def apply_migrations(self, target_version: str, backup: bool = True) -> None:
        """Apply migrations to reach target version."""
        if backup:
            backup_path = self._create_backup()
            click.echo(f"Created backup: {backup_path}")

        migrations = self.plan_migration(target_version)

        if not migrations:
            click.echo("No migrations needed")
            return

        # Load config
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Apply each migration
        for migration in migrations:
            click.echo(f"Applying migration: {migration.description}")
            config = self._apply_migration(config, migration)

        # Add version marker
        config['version'] = target_version

        # Write updated config
        with open(self.config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        click.secho(f"✓ Migrated to version {target_version}", fg='green')

    def _apply_migration(self, config: dict, migration: Migration) -> dict:
        """Apply a single migration."""
        for change in migration.changes:
            if change['type'] == 'add':
                self._set_nested(config, change['path'], change['value'])

            elif change['type'] == 'move':
                value = self._get_nested(config, change['from_path'])
                if value is not None:
                    self._set_nested(config, change['to_path'], value)
                    self._delete_nested(config, change['from_path'])

            elif change['type'] == 'delete':
                self._delete_nested(config, change['path'])

            elif change['type'] == 'rename':
                # Rename a key at specific path
                parent_path = '.'.join(change['path'].split('.')[:-1])
                old_key = change['path'].split('.')[-1]
                new_key = change['new_name']

                parent = self._get_nested(config, parent_path) if parent_path else config
                if old_key in parent:
                    parent[new_key] = parent.pop(old_key)

        return config

    def _create_backup(self) -> Path:
        """Create backup of config file."""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_path = self.config_path.with_suffix(f'.{timestamp}.backup')
        shutil.copy2(self.config_path, backup_path)
        return backup_path

    def _get_nested(self, obj: dict, path: str) -> Any:
        """Get nested value by dot-separated path."""
        keys = path.split('.')
        for key in keys:
            if isinstance(obj, dict) and key in obj:
                obj = obj[key]
            else:
                return None
        return obj

    def _set_nested(self, obj: dict, path: str, value: Any) -> None:
        """Set nested value by dot-separated path."""
        keys = path.split('.')
        for key in keys[:-1]:
            if key not in obj:
                obj[key] = {}
            obj = obj[key]
        obj[keys[-1]] = value

    def _delete_nested(self, obj: dict, path: str) -> None:
        """Delete nested value by dot-separated path."""
        keys = path.split('.')
        for key in keys[:-1]:
            if key not in obj:
                return
            obj = obj[key]
        obj.pop(keys[-1], None)

    def _version_in_range(self, current: str, from_ver: str, to_ver: str) -> bool:
        """Check if version is in migration range."""
        from packaging import version
        return version.parse(from_ver) <= version.parse(current) < version.parse(to_ver)

# CLI commands
@config_cli.group()
def migrate():
    """Configuration migration commands."""
    pass

@migrate.command()
@click.option('--file', '-f', type=click.Path(exists=True), help='Config file')
def check(file: Optional[str]):
    """Check if migration is needed."""
    config_path = Path(file) if file else Path('/etc/mcp-raspi/config.yml')
    migrator = ConfigMigrator(config_path)

    current_version = migrator.detect_version()
    target_version = "1.2.0"  # Latest version

    click.echo(f"Current version: {current_version}")
    click.echo(f"Target version: {target_version}")

    if migrator.needs_migration(target_version):
        click.secho("⚠ Migration needed", fg='yellow')
        return 1
    else:
        click.secho("✓ Configuration is up-to-date", fg='green')
        return 0

@migrate.command()
@click.option('--file', '-f', type=click.Path(exists=True), help='Config file')
@click.option('--to-version', default='1.2.0', help='Target version')
@click.option('--backup/--no-backup', default=True, help='Create backup')
def apply(file: Optional[str], to_version: str, backup: bool):
    """Apply configuration migration."""
    config_path = Path(file) if file else Path('/etc/mcp-raspi/config.yml')
    migrator = ConfigMigrator(config_path)

    try:
        migrator.apply_migrations(to_version, backup=backup)
    except Exception as e:
        click.secho(f"✗ Migration failed: {e}", fg='red')
        return 1

@migrate.command()
@click.option('--file', '-f', type=click.Path(exists=True), help='Config file')
@click.option('--to-version', default='1.2.0', help='Target version')
def plan(file: Optional[str], to_version: str):
    """Show migration plan."""
    config_path = Path(file) if file else Path('/etc/mcp-raspi/config.yml')
    migrator = ConfigMigrator(config_path)

    current_version = migrator.detect_version()
    migrations = migrator.plan_migration(to_version)

    click.echo(f"Current version: {current_version}")
    click.echo(f"Target version: {to_version}")
    click.echo(f"\nMigration plan ({len(migrations)} step(s)):\n")

    for i, migration in enumerate(migrations, 1):
        click.echo(f"{i}. {migration.from_version} → {migration.to_version}")
        click.echo(f"   {migration.description}")
        click.echo(f"   Changes:")
        for change in migration.changes:
            if change['type'] == 'add':
                click.echo(f"     + Add {change['path']}")
            elif change['type'] == 'move':
                click.echo(f"     → Move {change['from_path']} to {change['to_path']}")
            elif change['type'] == 'delete':
                click.echo(f"     - Delete {change['path']} ({change.get('reason', 'deprecated')})")
        click.echo()
```

---

## 4. Configuration Templates & Presets

### 4.1 Development Configuration

```yaml
# config-dev.yml - Development/testing configuration

version: "1.2.0"

server:
  listen_address: "127.0.0.1"
  listen_port: 8000
  log_level: "DEBUG"
  debug: true

security:
  auth_mode: "none"  # No auth for local dev
  rate_limiting:
    enabled: false

testing:
  sandbox_mode: true  # Safe testing mode

gpio:
  whitelist:
    enabled: false  # Allow all pins in dev

i2c:
  whitelist:
    enabled: false

service:
  whitelist:
    enabled: false

logging:
  level: "DEBUG"
  file:
    path: "./dev-logs/server.log"

metrics:
  collection:
    interval_seconds: 10  # Faster for testing

updates:
  auto_check: false
```

### 4.2 Production Configuration

```yaml
# config-production.yml - Production configuration

version: "1.2.0"

server:
  listen_address: "127.0.0.1"
  listen_port: 8000
  log_level: "INFO"
  debug: false

security:
  auth_mode: "cloudflare_access"
  cloudflare_access:
    enabled: true
    team_domain: "${CF_TEAM_DOMAIN}"
    audience_tag: "${CF_AUDIENCE_TAG}"

  rate_limiting:
    enabled: true
    default_rpm: 60

gpio:
  whitelist:
    enabled: true
    pins: [17, 27, 22]
    strict_mode: true

i2c:
  whitelist:
    enabled: true
    addresses: [0x48, 0x68]
    buses: [1]
    strict_mode: true

service:
  whitelist:
    enabled: true
    services: ["nginx", "postgresql"]
    strict_mode: true

  safety:
    require_confirmation: true
    restart_cooldown_seconds: 60

logging:
  level: "INFO"
  audit:
    enabled: true

  shipping:
    enabled: true
    backend: "fluent-bit"

metrics:
  collection:
    enabled: true
    interval_seconds: 60

  retention:
    max_age_days: 30
    max_size_mb: 500

updates:
  auto_check: true
  auto_install: false

  signature_verification:
    enabled: true

  schedule:
    enabled: true
    mode: "maintenance_window"
```

### 4.3 High-Security Configuration

```yaml
# config-high-security.yml - Maximum security configuration

version: "1.2.0"

server:
  listen_address: "127.0.0.1"  # Localhost only
  listen_port: 8000
  log_level: "INFO"

security:
  auth_mode: "cloudflare_access"
  cloudflare_access:
    enabled: true
    team_domain: "${CF_TEAM_DOMAIN}"
    audience_tag: "${CF_AUDIENCE_TAG}"

  rate_limiting:
    enabled: true
    default_rpm: 30  # Strict rate limit

  role_mappings:
    # Very restrictive role mapping
    - jwt_claim: "email"
      pattern: "admin@example.com"
      role: "admin"
    # No default operator/viewer roles

gpio:
  whitelist:
    enabled: true
    pins: []  # No GPIO access by default
    strict_mode: true

i2c:
  whitelist:
    enabled: true
    addresses: []  # No I2C access by default
    strict_mode: true

camera:
  enabled: false  # No camera access

service:
  whitelist:
    enabled: true
    services: []  # No service management
    strict_mode: true

logging:
  level: "INFO"
  audit:
    enabled: true
    immutable: true  # Phase 2+: Immutable audit logs

  shipping:
    enabled: true  # Ship logs to SIEM

updates:
  auto_check: true
  auto_install: false  # Manual updates only

  signature_verification:
    enabled: true
    allow_expired_keys: false
```

---

## 5. Implementation Checklist

### Phase 1 (Current)
- ✅ AppConfig Pydantic model
- ✅ YAML configuration loading
- ✅ Environment variable overrides
- ⚠️ **ADD**: Configuration validation CLI
- ⚠️ **ADD**: Comprehensive env var documentation
- ⚠️ **ADD**: Configuration templates (dev/prod/high-security)

### Phase 2+ (Future)
- ⏭️ Configuration migration tool
- ⏭️ Hot-reload configuration changes
- ⏭️ Configuration versioning and history
- ⏭️ Web UI for configuration management
- ⏭️ Configuration diff tool
- ⏭️ Secrets management integration (Vault, AWS Secrets Manager)
- ⏭️ Configuration validation in CI/CD
- ⏭️ Fleet-wide configuration management

---

**End of Document**
