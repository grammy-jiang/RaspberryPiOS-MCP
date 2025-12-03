"""
Tests for the configuration module.

This test module validates:
- Configuration loading from YAML files
- Environment variable overrides
- CLI argument overrides
- Configuration precedence (defaults < YAML < env vars < CLI args)
- Pydantic model validation with invalid inputs
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml

from mcp_raspi.config import (
    AppConfig,
    CameraConfig,
    DeviceConfig,
    GPIOConfig,
    I2CBusConfig,
    I2CConfig,
    MetricsConfig,
    SecurityConfig,
    ServerConfig,
    TestingConfig,
    ToolsConfig,
    UpdatesConfig,
    _deep_merge,
    _load_env_config,
    _load_yaml_config,
    _parse_cli_args,
    _parse_env_value,
    load_config,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create a temporary config file for testing."""
    config_path = tmp_path / "config.yml"
    return config_path


@pytest.fixture
def sample_yaml_config() -> dict[str, Any]:
    """Sample YAML configuration for testing."""
    return {
        "server": {
            "listen": "0.0.0.0:9000",
            "log_level": "debug",
        },
        "security": {
            "mode": "cloudflare",
            "roles": {
                "viewer": {"allowed_levels": ["read_only"]},
                "admin": {"allowed_levels": ["read_only", "safe_control", "admin"]},
            },
        },
        "gpio": {
            "allowed_pins": [17, 18, 27],
        },
        "testing": {
            "sandbox_mode": "full",
        },
    }


# =============================================================================
# Tests for Default Configuration
# =============================================================================


class TestDefaultConfiguration:
    """Tests for default configuration values."""

    def test_app_config_defaults(self) -> None:
        """Test that AppConfig has sensible defaults."""
        config = AppConfig()

        # Server defaults
        assert config.server.listen == "127.0.0.1:8000"
        assert config.server.log_level == "info"

        # Security defaults
        assert config.security.mode == "local"
        assert "viewer" in config.security.roles
        assert "operator" in config.security.roles
        assert "admin" in config.security.roles

        # Logging defaults
        assert config.logging.level == "info"
        assert config.logging.log_to_stdout is True

        # IPC defaults
        assert config.ipc.socket_path == "/run/mcp-raspi/ops-agent.sock"
        assert config.ipc.request_timeout_seconds == 5

        # Testing defaults
        assert config.testing.sandbox_mode == "partial"

    def test_server_config_defaults(self) -> None:
        """Test ServerConfig defaults."""
        config = ServerConfig()
        assert config.listen == "127.0.0.1:8000"
        assert config.log_level == "info"

    def test_security_config_defaults(self) -> None:
        """Test SecurityConfig defaults."""
        config = SecurityConfig()
        assert config.mode == "local"
        assert len(config.roles) == 3
        assert config.roles["viewer"].allowed_levels == ["read_only"]
        assert config.roles["admin"].allowed_levels == [
            "read_only",
            "safe_control",
            "admin",
        ]

    def test_gpio_config_defaults(self) -> None:
        """Test GPIOConfig defaults."""
        config = GPIOConfig()
        assert config.allowed_pins == []
        assert config.default_mode == "input"
        assert config.default_pull == "none"

    def test_i2c_config_defaults(self) -> None:
        """Test I2CConfig defaults."""
        config = I2CConfig()
        assert config.buses == []

    def test_camera_config_defaults(self) -> None:
        """Test CameraConfig defaults."""
        config = CameraConfig()
        assert config.enabled is True
        assert config.media_root == "/var/lib/mcp-raspi/media"
        assert config.max_photos_per_minute == 30

    def test_tools_config_defaults(self) -> None:
        """Test ToolsConfig defaults."""
        config = ToolsConfig()
        assert config.system.enabled is True
        assert config.gpio.enabled is True
        assert config.manage.enabled is True


# =============================================================================
# Tests for Configuration Validation
# =============================================================================


class TestConfigurationValidation:
    """Tests for configuration validation."""

    def test_log_level_validation_valid(self) -> None:
        """Test valid log levels are accepted."""
        for level in ["debug", "info", "warn", "warning", "error", "DEBUG", "INFO"]:
            config = ServerConfig(log_level=level)
            # 'warn' should be normalized to 'warning'
            if level.lower() == "warn":
                assert config.log_level == "warning"
            else:
                assert config.log_level == level.lower()

    def test_log_level_validation_invalid(self) -> None:
        """Test invalid log levels are rejected."""
        with pytest.raises(ValueError, match="Invalid log level"):
            ServerConfig(log_level="invalid")

    def test_security_mode_validation_valid(self) -> None:
        """Test valid security modes are accepted."""
        for mode in ["cloudflare", "local", "CLOUDFLARE", "LOCAL"]:
            config = SecurityConfig(mode=mode)
            assert config.mode == mode.lower()

    def test_security_mode_validation_invalid(self) -> None:
        """Test invalid security modes are rejected."""
        with pytest.raises(ValueError, match="Invalid security mode"):
            SecurityConfig(mode="invalid")

    def test_sandbox_mode_validation_valid(self) -> None:
        """Test valid sandbox modes are accepted."""
        for mode in ["full", "partial", "disabled", "FULL"]:
            config = TestingConfig(sandbox_mode=mode)
            assert config.sandbox_mode == mode.lower()

    def test_sandbox_mode_validation_invalid(self) -> None:
        """Test invalid sandbox modes are rejected."""
        with pytest.raises(ValueError, match="Invalid sandbox mode"):
            TestingConfig(sandbox_mode="invalid")


# =============================================================================
# Tests for YAML Configuration Loading
# =============================================================================


class TestYAMLConfigLoading:
    """Tests for YAML configuration file loading."""

    def test_load_yaml_config_success(
        self, temp_config_file: Path, sample_yaml_config: dict[str, Any]
    ) -> None:
        """Test successful YAML config loading."""
        with open(temp_config_file, "w") as f:
            yaml.dump(sample_yaml_config, f)

        config_dict = _load_yaml_config(temp_config_file)

        assert config_dict["server"]["listen"] == "0.0.0.0:9000"
        assert config_dict["server"]["log_level"] == "debug"
        assert config_dict["security"]["mode"] == "cloudflare"

    def test_load_yaml_config_file_not_found(self) -> None:
        """Test that missing config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            _load_yaml_config(Path("/nonexistent/config.yml"))

    def test_load_yaml_config_empty_file(self, temp_config_file: Path) -> None:
        """Test loading empty YAML file returns empty dict."""
        temp_config_file.write_text("")
        config_dict = _load_yaml_config(temp_config_file)
        assert config_dict == {}

    def test_load_config_with_yaml_file(
        self, temp_config_file: Path, sample_yaml_config: dict[str, Any]
    ) -> None:
        """Test load_config with YAML file."""
        with open(temp_config_file, "w") as f:
            yaml.dump(sample_yaml_config, f)

        config = load_config(config_path=temp_config_file, cli_args=[])

        assert config.server.listen == "0.0.0.0:9000"
        assert config.server.log_level == "debug"
        assert config.security.mode == "cloudflare"
        assert config.gpio.allowed_pins == [17, 18, 27]
        assert config.testing.sandbox_mode == "full"


# =============================================================================
# Tests for Environment Variable Loading
# =============================================================================


class TestEnvironmentVariableLoading:
    """Tests for environment variable configuration loading."""

    def test_parse_env_value_boolean_true(self) -> None:
        """Test parsing boolean true values."""
        for value in ["true", "True", "TRUE", "yes", "YES", "1", "on", "ON"]:
            assert _parse_env_value(value) is True

    def test_parse_env_value_boolean_false(self) -> None:
        """Test parsing boolean false values."""
        for value in ["false", "False", "FALSE", "no", "NO", "0", "off", "OFF"]:
            assert _parse_env_value(value) is False

    def test_parse_env_value_integer(self) -> None:
        """Test parsing integer values."""
        assert _parse_env_value("42") == 42
        assert _parse_env_value("-10") == -10
        assert _parse_env_value("0") is False  # 0 is parsed as boolean false

    def test_parse_env_value_float(self) -> None:
        """Test parsing float values."""
        assert _parse_env_value("3.14") == 3.14
        assert _parse_env_value("-2.5") == -2.5

    def test_parse_env_value_list(self) -> None:
        """Test parsing comma-separated list values."""
        result = _parse_env_value("17,18,27")
        assert result == [17, 18, 27]

        result = _parse_env_value("a, b, c")
        assert result == ["a", "b", "c"]

    def test_parse_env_value_string(self) -> None:
        """Test parsing string values."""
        assert _parse_env_value("hello") == "hello"
        assert _parse_env_value("127.0.0.1:8000") == "127.0.0.1:8000"

    def test_load_env_config_simple(self) -> None:
        """Test loading simple environment variables."""
        env_vars = {
            "MCP_RASPI_SERVER__LISTEN": "0.0.0.0:9000",
            "MCP_RASPI_SERVER__LOG_LEVEL": "debug",
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            config_dict = _load_env_config()

        assert config_dict["server"]["listen"] == "0.0.0.0:9000"
        assert config_dict["server"]["log_level"] == "debug"

    def test_load_env_config_nested(self) -> None:
        """Test loading nested environment variables."""
        env_vars = {
            "MCP_RASPI_SECURITY__MODE": "cloudflare",
            "MCP_RASPI_LOGGING__DEBUG_MODE": "true",
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            config_dict = _load_env_config()

        assert config_dict["security"]["mode"] == "cloudflare"
        assert config_dict["logging"]["debug_mode"] is True

    def test_load_config_with_env_vars(self, temp_config_file: Path) -> None:
        """Test load_config with environment variable overrides."""
        # Create YAML config
        yaml_config = {"server": {"listen": "127.0.0.1:8000", "log_level": "info"}}
        with open(temp_config_file, "w") as f:
            yaml.dump(yaml_config, f)

        # Environment variable should override YAML
        env_vars = {"MCP_RASPI_SERVER__LOG_LEVEL": "debug"}

        with mock.patch.dict(os.environ, env_vars, clear=False):
            config = load_config(config_path=temp_config_file, cli_args=[])

        assert config.server.listen == "127.0.0.1:8000"  # From YAML
        assert config.server.log_level == "debug"  # From env var (overrides YAML)


# =============================================================================
# Tests for CLI Argument Parsing
# =============================================================================


class TestCLIArgumentParsing:
    """Tests for command-line argument parsing."""

    def test_parse_cli_args_config_path(self) -> None:
        """Test parsing --config argument."""
        result = _parse_cli_args(["--config", "/path/to/config.yml"])
        assert result["_config_path"] == "/path/to/config.yml"

    def test_parse_cli_args_log_level(self) -> None:
        """Test parsing --log-level argument."""
        result = _parse_cli_args(["--log-level", "debug"])
        assert result["server"]["log_level"] == "debug"

    def test_parse_cli_args_debug(self) -> None:
        """Test parsing --debug argument."""
        result = _parse_cli_args(["--debug"])
        assert result["logging"]["debug_mode"] is True
        assert result["server"]["log_level"] == "debug"

    def test_parse_cli_args_empty(self) -> None:
        """Test parsing empty arguments."""
        result = _parse_cli_args([])
        assert result == {}

    def test_load_config_with_cli_args(self, temp_config_file: Path) -> None:
        """Test load_config with CLI argument overrides."""
        # Create YAML config
        yaml_config = {"server": {"listen": "127.0.0.1:8000", "log_level": "info"}}
        with open(temp_config_file, "w") as f:
            yaml.dump(yaml_config, f)

        # CLI should override YAML
        config = load_config(
            config_path=temp_config_file, cli_args=["--log-level", "error"]
        )

        assert config.server.log_level == "error"


# =============================================================================
# Tests for Configuration Precedence
# =============================================================================


class TestConfigurationPrecedence:
    """Tests for configuration layering precedence."""

    def test_precedence_yaml_overrides_defaults(self, temp_config_file: Path) -> None:
        """Test that YAML config overrides defaults."""
        yaml_config = {"server": {"listen": "0.0.0.0:9000"}}
        with open(temp_config_file, "w") as f:
            yaml.dump(yaml_config, f)

        config = load_config(config_path=temp_config_file, cli_args=[])

        # YAML overrides default
        assert config.server.listen == "0.0.0.0:9000"
        # Default is preserved for non-overridden values
        assert config.server.log_level == "info"

    def test_precedence_env_overrides_yaml(self, temp_config_file: Path) -> None:
        """Test that env vars override YAML config."""
        yaml_config = {"server": {"listen": "0.0.0.0:9000", "log_level": "info"}}
        with open(temp_config_file, "w") as f:
            yaml.dump(yaml_config, f)

        env_vars = {"MCP_RASPI_SERVER__LOG_LEVEL": "warning"}

        with mock.patch.dict(os.environ, env_vars, clear=False):
            config = load_config(config_path=temp_config_file, cli_args=[])

        assert config.server.listen == "0.0.0.0:9000"  # From YAML
        assert config.server.log_level == "warning"  # From env var

    def test_precedence_cli_overrides_env(self, temp_config_file: Path) -> None:
        """Test that CLI args override env vars."""
        yaml_config = {"server": {"listen": "0.0.0.0:9000", "log_level": "info"}}
        with open(temp_config_file, "w") as f:
            yaml.dump(yaml_config, f)

        env_vars = {"MCP_RASPI_SERVER__LOG_LEVEL": "warning"}

        with mock.patch.dict(os.environ, env_vars, clear=False):
            config = load_config(
                config_path=temp_config_file, cli_args=["--log-level", "error"]
            )

        assert config.server.log_level == "error"  # CLI overrides env var

    def test_full_precedence_chain(self, temp_config_file: Path) -> None:
        """Test full precedence: defaults < YAML < env vars < CLI args."""
        # YAML config
        yaml_config = {
            "server": {"listen": "0.0.0.0:9000", "log_level": "info"},
            "security": {"mode": "cloudflare"},
            "testing": {"sandbox_mode": "partial"},
        }
        with open(temp_config_file, "w") as f:
            yaml.dump(yaml_config, f)

        # Environment variables
        env_vars = {
            "MCP_RASPI_SECURITY__MODE": "local",
            "MCP_RASPI_SERVER__LOG_LEVEL": "warning",
        }

        # CLI args
        cli_args = ["--log-level", "debug"]

        with mock.patch.dict(os.environ, env_vars, clear=False):
            config = load_config(config_path=temp_config_file, cli_args=cli_args)

        # CLI overrides env var which would have overridden YAML
        assert config.server.log_level == "debug"
        # Env var overrides YAML
        assert config.security.mode == "local"
        # YAML value preserved
        assert config.server.listen == "0.0.0.0:9000"
        # YAML value preserved
        assert config.testing.sandbox_mode == "partial"
        # Default value preserved (not in YAML or env)
        assert config.ipc.request_timeout_seconds == 5


# =============================================================================
# Tests for Deep Merge
# =============================================================================


class TestDeepMerge:
    """Tests for deep merge functionality."""

    def test_deep_merge_simple(self) -> None:
        """Test simple value override."""
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_deep_merge_nested(self) -> None:
        """Test nested dictionary merge."""
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"c": 3, "d": 4}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": 1, "c": 3, "d": 4}}

    def test_deep_merge_does_not_modify_original(self) -> None:
        """Test that deep merge does not modify original dicts."""
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}

        result = _deep_merge(base, override)

        assert result == {"a": {"b": 1, "c": 2}}
        assert base == {"a": {"b": 1}}  # Original unchanged
        assert override == {"a": {"c": 2}}  # Original unchanged


# =============================================================================
# Tests for Device Configuration
# =============================================================================


class TestDeviceConfiguration:
    """Tests for device-specific configuration."""

    def test_i2c_bus_config(self) -> None:
        """Test I2C bus configuration."""
        config = I2CBusConfig(
            bus=1,
            mode="full",
            allow_addresses=[0x48, 0x68],
            deny_addresses=[0x50],
        )
        assert config.bus == 1
        assert config.mode == "full"
        assert config.allow_addresses == [0x48, 0x68]
        assert config.deny_addresses == [0x50]

    def test_device_config_aggregation(self) -> None:
        """Test DeviceConfig aggregates all device configs."""
        config = DeviceConfig(
            gpio=GPIOConfig(allowed_pins=[17, 18]),
            i2c=I2CConfig(buses=[I2CBusConfig(bus=1)]),
            camera=CameraConfig(enabled=False),
        )
        assert config.gpio.allowed_pins == [17, 18]
        assert len(config.i2c.buses) == 1
        assert config.camera.enabled is False


# =============================================================================
# Tests for Updates and Metrics Configuration
# =============================================================================


class TestUpdatesConfiguration:
    """Tests for updates configuration."""

    def test_updates_config_defaults(self) -> None:
        """Test UpdatesConfig defaults."""
        config = UpdatesConfig()
        assert config.backend == "python_package"
        assert config.package_name == "mcp-raspi"
        assert config.enable_remote_server_update is False
        assert config.enable_os_update is False

    def test_updates_config_custom(self) -> None:
        """Test UpdatesConfig with custom values."""
        config = UpdatesConfig(
            backend="apt",
            enable_remote_server_update=True,
            trusted_origins=["https://example.com"],
        )
        assert config.backend == "apt"
        assert config.enable_remote_server_update is True
        assert config.trusted_origins == ["https://example.com"]


class TestMetricsConfiguration:
    """Tests for metrics configuration."""

    def test_metrics_config_defaults(self) -> None:
        """Test MetricsConfig defaults."""
        config = MetricsConfig()
        assert config.storage_path == "/var/lib/mcp-raspi/metrics/metrics.db"
        assert config.sampling_interval_seconds == 30
        assert config.max_retention_days == 7


# =============================================================================
# Tests for Loading Without Config File
# =============================================================================


class TestLoadingWithoutConfigFile:
    """Tests for loading configuration without a config file."""

    def test_load_config_defaults_only(self) -> None:
        """Test loading config with only defaults."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Clear all MCP_RASPI_ env vars
            env_to_clear = {k: "" for k in os.environ if k.startswith("MCP_RASPI_")}
            with mock.patch.dict(os.environ, env_to_clear):
                config = load_config(config_path=None, cli_args=[])

        # All defaults should be applied
        assert config.server.listen == "127.0.0.1:8000"
        assert config.security.mode == "local"

    def test_load_config_env_only(self) -> None:
        """Test loading config with only env vars."""
        env_vars = {
            "MCP_RASPI_SERVER__LISTEN": "0.0.0.0:8080",
            "MCP_RASPI_SECURITY__MODE": "cloudflare",
        }

        with mock.patch.dict(os.environ, env_vars, clear=False):
            config = load_config(config_path=None, cli_args=[])

        assert config.server.listen == "0.0.0.0:8080"
        assert config.security.mode == "cloudflare"
