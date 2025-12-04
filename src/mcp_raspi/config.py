"""
Configuration management for the Raspberry Pi MCP Server.

This module implements the AppConfig Pydantic model and configuration loading
following the design specifications in docs 02, 13, and 14.

Configuration is loaded from multiple sources with layered precedence:
1. Built-in defaults (Pydantic model defaults)
2. YAML config file (/etc/mcp-raspi/config.yml or --config path)
3. Environment variables (MCP_RASPI_* prefix, __ for nesting)
4. Command-line arguments (highest precedence)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Server Configuration
# =============================================================================


class ServerConfig(BaseModel):
    """Server settings configuration.

    Attributes:
        listen: Listen address and port (e.g., "127.0.0.1:8000").
        log_level: Initial application log level.
    """

    listen: str = Field(
        default="127.0.0.1:8000",
        description="Listen address and port (e.g., '127.0.0.1:8000' or '0.0.0.0:8000')",
    )
    log_level: str = Field(
        default="info",
        description="Log level: debug, info, warn, error",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize log level."""
        valid_levels = {"debug", "info", "warn", "warning", "error", "critical"}
        v_lower = v.lower()
        if v_lower not in valid_levels:
            raise ValueError(
                f"Invalid log level: {v}. Must be one of: {', '.join(sorted(valid_levels))}"
            )
        # Normalize 'warn' to 'warning'
        if v_lower == "warn":
            return "warning"
        return v_lower


# =============================================================================
# Security Configuration
# =============================================================================


class RoleConfig(BaseModel):
    """Configuration for a single role.

    Attributes:
        allowed_levels: Safety levels allowed for this role.
    """

    allowed_levels: list[str] = Field(
        default_factory=lambda: ["read_only"],
        description="Safety levels allowed for this role",
    )


class RoleMappingsConfig(BaseModel):
    """Role mapping configuration.

    Attributes:
        groups_to_roles: Mapping from external groups to internal roles.
    """

    groups_to_roles: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from external groups (e.g., JWT claims) to internal roles",
    )


class LocalAuthConfig(BaseModel):
    """Local authentication configuration for dev/testing.

    Attributes:
        static_token: Optional static token for local authentication.
        permissive_mode: If True, allows all requests without authentication.
        default_role: Default role assigned in permissive mode.
    """

    static_token: str | None = Field(
        default=None,
        description="Static token for local authentication (dev/testing only)",
    )
    permissive_mode: bool = Field(
        default=False,
        description="Allow all requests without authentication (dev only)",
    )
    default_role: str = Field(
        default="admin",
        description="Default role assigned in permissive mode",
    )
    default_user_id: str = Field(
        default="local-dev-user",
        description="Default user ID in permissive mode",
    )


class CloudflareAuthConfig(BaseModel):
    """Cloudflare Access authentication configuration.

    Attributes:
        jwks_url: URL to fetch Cloudflare Access JWKS.
        audience: Expected audience claim in the JWT.
        issuer: Expected issuer claim in the JWT (Cloudflare team domain).
        jwks_cache_ttl_seconds: How long to cache JWKS before refresh.
    """

    jwks_url: str = Field(
        default="",
        description="URL to fetch Cloudflare Access JWKS public keys",
    )
    audience: str = Field(
        default="",
        description="Expected audience (aud) claim in JWT",
    )
    issuer: str = Field(
        default="",
        description="Expected issuer (iss) claim in JWT (e.g., https://<team>.cloudflareaccess.com)",
    )
    jwks_cache_ttl_seconds: int = Field(
        default=3600,
        description="JWKS cache TTL in seconds",
        ge=60,
        le=86400,
    )


class SecurityConfig(BaseModel):
    """Security and authentication configuration.

    Attributes:
        mode: Authentication mode ('cloudflare' or 'local').
        roles: Role definitions with allowed safety levels.
        role_mappings: Mapping from external identity to internal roles.
        local_auth: Local authentication settings.
        cloudflare_auth: Cloudflare Access authentication settings.
    """

    mode: str = Field(
        default="local",
        description="Authentication mode: 'cloudflare' or 'local'",
    )
    roles: dict[str, RoleConfig] = Field(
        default_factory=lambda: {
            "viewer": RoleConfig(allowed_levels=["read_only"]),
            "operator": RoleConfig(allowed_levels=["read_only", "safe_control"]),
            "admin": RoleConfig(allowed_levels=["read_only", "safe_control", "admin"]),
        },
        description="Role definitions",
    )
    role_mappings: RoleMappingsConfig = Field(
        default_factory=RoleMappingsConfig,
        description="External identity to role mappings",
    )
    local_auth: LocalAuthConfig = Field(
        default_factory=LocalAuthConfig,
        description="Local authentication settings for dev/testing",
    )
    cloudflare_auth: CloudflareAuthConfig = Field(
        default_factory=CloudflareAuthConfig,
        description="Cloudflare Access authentication settings",
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate authentication mode."""
        valid_modes = {"cloudflare", "local"}
        v_lower = v.lower()
        if v_lower not in valid_modes:
            raise ValueError(
                f"Invalid security mode: {v}. Must be one of: {', '.join(sorted(valid_modes))}"
            )
        return v_lower


# =============================================================================
# Logging Configuration
# =============================================================================


class LoggingConfig(BaseModel):
    """Logging and audit configuration.

    Attributes:
        app_log_path: Application log file path.
        audit_log_path: Audit log file path.
        level: Log level.
        log_to_stdout: Whether to log to stdout.
        use_journald: Whether to use journald.
        debug_mode: Enable extra diagnostic logging.
        max_bytes: Optional max log file size.
        backup_count: Optional number of backup files.
        retention_days: Optional log retention days.
    """

    app_log_path: str = Field(
        default="/var/log/mcp-raspi/app.log",
        description="Application log file path",
    )
    audit_log_path: str = Field(
        default="/var/log/mcp-raspi/audit.log",
        description="Audit log file path",
    )
    level: str = Field(
        default="info",
        description="Log level",
    )
    log_to_stdout: bool = Field(
        default=True,
        description="Whether to log to stdout",
    )
    use_journald: bool = Field(
        default=False,
        description="Whether to use journald instead of file logging",
    )
    debug_mode: bool = Field(
        default=False,
        description="Enable extra diagnostic logging",
    )
    max_bytes: int | None = Field(
        default=None,
        description="Maximum log file size in bytes",
    )
    backup_count: int | None = Field(
        default=None,
        description="Number of backup log files to keep",
    )
    retention_days: int | None = Field(
        default=None,
        description="Log retention period in days",
    )


# =============================================================================
# Tools Configuration
# =============================================================================


class ToolNamespaceConfig(BaseModel):
    """Configuration for a tool namespace.

    Attributes:
        enabled: Whether the namespace is enabled.
    """

    enabled: bool = Field(
        default=True,
        description="Whether this tool namespace is enabled",
    )


class ServiceToolsConfig(ToolNamespaceConfig):
    """Configuration for service tools namespace.

    Attributes:
        enabled: Whether the namespace is enabled.
        allowed_services: List of service names/patterns allowed for management.
    """

    allowed_services: list[str] = Field(
        default_factory=list,
        description="List of service names or patterns allowed for management (e.g., 'nginx', 'mcp-raspi-*')",
    )


def _default_deny_pids() -> list[int]:
    """Return default list of protected PIDs (PID 1 / systemd)."""
    return [1]


class ProcessToolsConfig(ToolNamespaceConfig):
    """Configuration for process tools namespace.

    Attributes:
        enabled: Whether the namespace is enabled.
        allowed_users: List of users whose processes can be managed.
        deny_pids: List of PIDs that are always protected.
    """

    allowed_users: list[str] = Field(
        default_factory=list,
        description="List of users whose processes can be managed",
    )
    deny_pids: list[int] = Field(
        default_factory=_default_deny_pids,
        description="List of PIDs that are always protected from management",
    )


class ToolsConfig(BaseModel):
    """Tool namespace configuration.

    Attributes:
        system: System tools configuration.
        metrics: Metrics tools configuration.
        service: Service tools configuration.
        process: Process tools configuration.
        gpio: GPIO tools configuration.
        i2c: I2C tools configuration.
        camera: Camera tools configuration.
        logs: Logs tools configuration.
        manage: Management tools configuration.
    """

    system: ToolNamespaceConfig = Field(
        default_factory=ToolNamespaceConfig,
        description="System tools configuration",
    )
    metrics: ToolNamespaceConfig = Field(
        default_factory=ToolNamespaceConfig,
        description="Metrics tools configuration",
    )
    service: ServiceToolsConfig = Field(
        default_factory=ServiceToolsConfig,
        description="Service tools configuration",
    )
    process: ProcessToolsConfig = Field(
        default_factory=ProcessToolsConfig,
        description="Process tools configuration",
    )
    gpio: ToolNamespaceConfig = Field(
        default_factory=ToolNamespaceConfig,
        description="GPIO tools configuration",
    )
    i2c: ToolNamespaceConfig = Field(
        default_factory=ToolNamespaceConfig,
        description="I2C tools configuration",
    )
    camera: ToolNamespaceConfig = Field(
        default_factory=ToolNamespaceConfig,
        description="Camera tools configuration",
    )
    logs: ToolNamespaceConfig = Field(
        default_factory=ToolNamespaceConfig,
        description="Logs tools configuration",
    )
    manage: ToolNamespaceConfig = Field(
        default_factory=ToolNamespaceConfig,
        description="Management tools configuration",
    )


# =============================================================================
# Device Configuration (GPIO, I2C, Camera)
# =============================================================================


class GPIOConfig(BaseModel):
    """GPIO device control configuration.

    Attributes:
        allowed_pins: List of BCM pins allowed for MCP control.
        default_mode: Default mode for unmanaged pins ('input' or 'output').
        default_pull: Default pull configuration ('none', 'up', 'down').
    """

    allowed_pins: list[int] = Field(
        default_factory=list,
        description="List of BCM pins allowed for MCP control",
    )
    default_mode: str = Field(
        default="input",
        description="Default mode for unmanaged pins",
    )
    default_pull: str = Field(
        default="none",
        description="Default pull configuration: 'none', 'up', 'down'",
    )


class I2CBusConfig(BaseModel):
    """Configuration for a single I2C bus.

    Attributes:
        bus: Bus number (e.g., 1 for /dev/i2c-1).
        mode: Access mode ('full', 'read_only', 'disabled').
        allow_addresses: Explicitly allowed device addresses.
        deny_addresses: Blacklisted addresses.
    """

    bus: int = Field(
        default=1,
        description="I2C bus number",
    )
    mode: str = Field(
        default="full",
        description="Access mode: 'full', 'read_only', 'disabled'",
    )
    allow_addresses: list[int] = Field(
        default_factory=list,
        description="Explicitly allowed I2C addresses",
    )
    deny_addresses: list[int] = Field(
        default_factory=list,
        description="Blacklisted I2C addresses",
    )


class I2CConfig(BaseModel):
    """I2C device control configuration.

    Attributes:
        buses: List of I2C bus configurations.
    """

    buses: list[I2CBusConfig] = Field(
        default_factory=list,
        description="I2C bus configurations",
    )


class CameraConfig(BaseModel):
    """Camera device control configuration.

    Attributes:
        enabled: Whether camera tools are enabled.
        media_root: Root directory for captured media.
        max_photos_per_minute: Rate limit for capture operations.
    """

    enabled: bool = Field(
        default=True,
        description="Whether camera tools are enabled",
    )
    media_root: str = Field(
        default="/var/lib/mcp-raspi/media",
        description="Root directory for captured media",
    )
    max_photos_per_minute: int = Field(
        default=30,
        description="Maximum photos per minute rate limit",
    )


class DeviceConfig(BaseModel):
    """Aggregated device control configuration.

    Attributes:
        gpio: GPIO configuration.
        i2c: I2C configuration.
        camera: Camera configuration.
    """

    gpio: GPIOConfig = Field(
        default_factory=GPIOConfig,
        description="GPIO configuration",
    )
    i2c: I2CConfig = Field(
        default_factory=I2CConfig,
        description="I2C configuration",
    )
    camera: CameraConfig = Field(
        default_factory=CameraConfig,
        description="Camera configuration",
    )


# =============================================================================
# Metrics Configuration
# =============================================================================


class MetricsConfig(BaseModel):
    """Metrics storage and sampling configuration.

    Attributes:
        storage_path: Path to metrics storage (SQLite database).
        sampling_interval_seconds: Default interval for metric sampling.
        max_retention_days: Retention time for stored samples.
    """

    storage_path: str = Field(
        default="/var/lib/mcp-raspi/metrics/metrics.db",
        description="Path to metrics storage",
    )
    sampling_interval_seconds: int = Field(
        default=30,
        description="Default metric sampling interval in seconds",
    )
    max_retention_days: int = Field(
        default=7,
        description="Maximum retention days for metrics data",
    )


# =============================================================================
# IPC Configuration
# =============================================================================


class IPCConfig(BaseModel):
    """Privileged agent IPC configuration.

    Attributes:
        socket_path: Unix domain socket path.
        request_timeout_seconds: Default timeout for IPC requests.
    """

    socket_path: str = Field(
        default="/run/mcp-raspi/ops-agent.sock",
        description="Unix domain socket path for IPC",
    )
    request_timeout_seconds: int = Field(
        default=5,
        description="Default IPC request timeout in seconds",
    )


# =============================================================================
# Updates Configuration
# =============================================================================


class UpdatesConfig(BaseModel):
    """Self-update and OS update configuration.

    Attributes:
        backend: Update backend type.
        package_name: Python package name.
        releases_dir: Release directory path.
        staging_dir: Staging directory path.
        default_channel: Default update channel.
        enable_remote_server_update: Allow remote self-update via MCP.
        enable_os_update: Enable OS update tools.
        trusted_origins: Trusted update source URLs.
        require_signature: Require signature verification.
    """

    backend: str = Field(
        default="python_package",
        description="Update backend: 'python_package', 'git', 'archive', 'apt'",
    )
    package_name: str = Field(
        default="mcp-raspi",
        description="Python package name",
    )
    releases_dir: str = Field(
        default="/opt/mcp-raspi/releases",
        description="Release directory path",
    )
    staging_dir: str = Field(
        default="/opt/mcp-raspi/staging",
        description="Staging directory path",
    )
    default_channel: str = Field(
        default="stable",
        description="Default update channel",
    )
    enable_remote_server_update: bool = Field(
        default=False,
        description="Allow remote self-update via MCP tools",
    )
    enable_os_update: bool = Field(
        default=False,
        description="Enable OS update tools",
    )
    trusted_origins: list[str] = Field(
        default_factory=list,
        description="Trusted update source URLs",
    )
    require_signature: bool = Field(
        default=False,
        description="Require signature verification for updates",
    )


# =============================================================================
# Testing Configuration
# =============================================================================


class TestingConfig(BaseModel):
    """Sandbox and test settings configuration.

    Attributes:
        sandbox_mode: Sandbox mode ('full', 'partial', 'disabled').
    """

    sandbox_mode: str = Field(
        default="partial",
        description="Sandbox mode: 'full', 'partial', 'disabled'",
    )

    @field_validator("sandbox_mode")
    @classmethod
    def validate_sandbox_mode(cls, v: str) -> str:
        """Validate sandbox mode."""
        valid_modes = {"full", "partial", "disabled"}
        v_lower = v.lower()
        if v_lower not in valid_modes:
            raise ValueError(
                f"Invalid sandbox mode: {v}. Must be one of: {', '.join(sorted(valid_modes))}"
            )
        return v_lower


# =============================================================================
# Main Application Configuration
# =============================================================================


class AppConfig(BaseModel):
    """
    Main application configuration model.

    This is the central configuration model that contains all configuration
    sections. It is built from multiple layers following the precedence rules:
    1. Built-in defaults (defined in this model)
    2. YAML config file
    3. Environment variables (MCP_RASPI_* prefix)
    4. Command-line arguments

    Attributes:
        server: Server settings.
        security: Security and authentication settings.
        logging: Logging configuration.
        tools: Tool namespace configuration.
        gpio: GPIO device configuration (top-level for backward compatibility).
        i2c: I2C device configuration.
        camera: Camera device configuration.
        metrics: Metrics storage configuration.
        ipc: IPC configuration.
        updates: Update configuration.
        testing: Testing/sandbox configuration.
    """

    server: ServerConfig = Field(
        default_factory=ServerConfig,
        description="Server settings",
    )
    security: SecurityConfig = Field(
        default_factory=SecurityConfig,
        description="Security and authentication settings",
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration",
    )
    tools: ToolsConfig = Field(
        default_factory=ToolsConfig,
        description="Tool namespace configuration",
    )
    gpio: GPIOConfig = Field(
        default_factory=GPIOConfig,
        description="GPIO device configuration",
    )
    i2c: I2CConfig = Field(
        default_factory=I2CConfig,
        description="I2C device configuration",
    )
    camera: CameraConfig = Field(
        default_factory=CameraConfig,
        description="Camera device configuration",
    )
    metrics: MetricsConfig = Field(
        default_factory=MetricsConfig,
        description="Metrics storage configuration",
    )
    ipc: IPCConfig = Field(
        default_factory=IPCConfig,
        description="IPC configuration",
    )
    updates: UpdatesConfig = Field(
        default_factory=UpdatesConfig,
        description="Update configuration",
    )
    testing: TestingConfig = Field(
        default_factory=TestingConfig,
        description="Testing/sandbox configuration",
    )


# =============================================================================
# Configuration Loading Functions
# =============================================================================


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge two dictionaries.

    Args:
        base: The base dictionary.
        override: The dictionary with values to override.

    Returns:
        A new dictionary with merged values.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    """
    Load configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Dictionary with configuration values.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        yaml.YAMLError: If the YAML is invalid.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def _parse_env_value(value: str) -> Any:
    """
    Parse an environment variable value to appropriate Python type.

    Args:
        value: String value from environment variable.

    Returns:
        Parsed value (bool, int, float, list, or string).
    """
    # Handle boolean values
    if value.lower() in ("true", "yes", "1", "on"):
        return True
    if value.lower() in ("false", "no", "0", "off"):
        return False

    # Handle integer values
    try:
        return int(value)
    except ValueError:
        pass

    # Handle float values
    try:
        return float(value)
    except ValueError:
        pass

    # Handle comma-separated lists
    if "," in value:
        items = [item.strip() for item in value.split(",")]
        # Try to parse each item
        return [_parse_env_value(item) for item in items]

    return value


def _load_env_config(prefix: str = "MCP_RASPI_") -> dict[str, Any]:
    """
    Load configuration from environment variables.

    Environment variables are parsed with the following rules:
    - Prefix: MCP_RASPI_ (configurable)
    - Nested keys: Double underscore (__) separator
    - Example: MCP_RASPI_SERVER__LISTEN=0.0.0.0:8000

    Args:
        prefix: Environment variable prefix.

    Returns:
        Dictionary with configuration values.
    """
    result: dict[str, Any] = {}

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        # Remove prefix and convert to lowercase
        config_key = key[len(prefix) :].lower()

        # Split by double underscore for nesting
        parts = config_key.split("__")

        # Build nested dictionary
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Set the value
        current[parts[-1]] = _parse_env_value(value)

    return result


def _parse_cli_args(args: list[str] | None = None) -> dict[str, Any]:
    """
    Parse command-line arguments.

    Args:
        args: Command-line arguments. If None, uses sys.argv.

    Returns:
        Dictionary with parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Raspberry Pi MCP Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to configuration file",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["debug", "info", "warning", "error"],
        help="Override log level",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    parsed = parser.parse_args(args)

    result: dict[str, Any] = {}

    if parsed.config:
        result["_config_path"] = parsed.config

    if parsed.log_level:
        result["server"] = {"log_level": parsed.log_level}

    if parsed.debug:
        if "logging" not in result:
            result["logging"] = {}
        result["logging"]["debug_mode"] = True
        if "server" not in result:
            result["server"] = {}
        result["server"]["log_level"] = "debug"

    return result


def load_config(
    config_path: Path | str | None = None,
    env_prefix: str = "MCP_RASPI_",
    cli_args: list[str] | None = None,
) -> AppConfig:
    """
    Load configuration from all sources with layered precedence.

    Configuration is loaded from multiple sources in order:
    1. Built-in defaults (from AppConfig model)
    2. YAML config file (if specified or default exists)
    3. Environment variables (MCP_RASPI_* prefix)
    4. Command-line arguments

    Later sources override earlier ones.

    Args:
        config_path: Path to YAML configuration file. If None, uses default
            path or CLI --config argument.
        env_prefix: Prefix for environment variables.
        cli_args: Command-line arguments. If None, uses sys.argv.

    Returns:
        Fully configured AppConfig instance.

    Raises:
        FileNotFoundError: If specified config file doesn't exist.
        ValidationError: If configuration is invalid.

    Example:
        >>> config = load_config()
        >>> print(config.server.listen)
        '127.0.0.1:8000'

        >>> config = load_config(config_path="/etc/mcp-raspi/config.yml")
        >>> print(config.security.mode)
        'cloudflare'
    """
    # Start with empty config dict (defaults come from Pydantic model)
    config_dict: dict[str, Any] = {}

    # Parse CLI args first to get config path
    cli_config = _parse_cli_args(cli_args)

    # Determine config file path
    if config_path is None:
        if "_config_path" in cli_config:
            config_path = Path(cli_config.pop("_config_path"))
        else:
            # Check default path
            default_path = Path("/etc/mcp-raspi/config.yml")
            if default_path.exists():
                config_path = default_path
    elif isinstance(config_path, str):
        config_path = Path(config_path)

    # Load YAML config if available
    if config_path is not None:
        yaml_config = _load_yaml_config(config_path)
        config_dict = _deep_merge(config_dict, yaml_config)

    # Load environment variables
    env_config = _load_env_config(env_prefix)
    config_dict = _deep_merge(config_dict, env_config)

    # Apply CLI overrides
    config_dict = _deep_merge(config_dict, cli_config)

    # Create and validate the AppConfig
    return AppConfig(**config_dict)
