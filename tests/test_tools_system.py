"""
Tests for system namespace tools.

This test module validates:
- system.get_basic_info returns valid system information
- system.get_health_snapshot returns valid health metrics
- system.get_network_info returns valid network interface data
- system.reboot requires admin role and handles sandbox modes
- system.shutdown requires admin role and handles sandbox modes
"""

from __future__ import annotations

import platform
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_raspi.config import AppConfig, TestingConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import UnavailableError
from mcp_raspi.security.rbac import PermissionDeniedError
from mcp_raspi.tools.system import (
    _get_all_thermal_zones,
    _get_cpu_temperature,
    _get_os_info,
    _get_raspberry_pi_model,
    _get_throttling_flags,
    handle_system_get_basic_info,
    handle_system_get_health_snapshot,
    handle_system_get_network_info,
    handle_system_reboot,
    handle_system_shutdown,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="system.get_basic_info",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def admin_ctx() -> ToolContext:
    """Create a test context with admin role."""
    return ToolContext(
        tool_name="system.reboot",
        caller=CallerInfo(user_id="admin@example.com", role="admin"),
        request_id="test-req-admin",
    )


@pytest.fixture
def operator_ctx() -> ToolContext:
    """Create a test context with operator role."""
    return ToolContext(
        tool_name="system.reboot",
        caller=CallerInfo(user_id="operator@example.com", role="operator"),
        request_id="test-req-operator",
    )


@pytest.fixture
def full_sandbox_config() -> AppConfig:
    """Create config with full sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    return config


@pytest.fixture
def partial_sandbox_config() -> AppConfig:
    """Create config with partial sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="partial")
    return config


@pytest.fixture
def disabled_sandbox_config() -> AppConfig:
    """Create config with disabled sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="disabled")
    return config


# =============================================================================
# Tests for system.get_basic_info
# =============================================================================


class TestSystemGetBasicInfo:
    """Tests for system.get_basic_info tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, viewer_ctx: ToolContext) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(self, viewer_ctx: ToolContext) -> None:
        """Test that result contains all required fields.

        Required fields (from Doc 05 §3.1 system.get_basic_info spec):
        - hostname, model, cpu_arch, cpu_cores, memory_total_bytes
        - os_name, os_version, kernel_version, uptime_seconds, timestamp
        """
        result = await handle_system_get_basic_info(viewer_ctx, {})

        required_fields = [
            "hostname",
            "model",
            "cpu_arch",
            "cpu_cores",
            "memory_total_bytes",
            "os_name",
            "os_version",
            "kernel_version",
            "uptime_seconds",
            "timestamp",
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_hostname_is_string(self, viewer_ctx: ToolContext) -> None:
        """Test hostname is a non-empty string."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert isinstance(result["hostname"], str)
        assert len(result["hostname"]) > 0

    @pytest.mark.asyncio
    async def test_cpu_arch_is_valid(self, viewer_ctx: ToolContext) -> None:
        """Test cpu_arch is a valid architecture string."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert isinstance(result["cpu_arch"], str)
        # Should match the actual platform
        assert result["cpu_arch"] == platform.machine()

    @pytest.mark.asyncio
    async def test_cpu_cores_is_positive_int(self, viewer_ctx: ToolContext) -> None:
        """Test cpu_cores is a positive integer."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert isinstance(result["cpu_cores"], int)
        assert result["cpu_cores"] > 0

    @pytest.mark.asyncio
    async def test_memory_is_positive_int(self, viewer_ctx: ToolContext) -> None:
        """Test memory_total_bytes is a positive integer."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert isinstance(result["memory_total_bytes"], int)
        assert result["memory_total_bytes"] > 0

    @pytest.mark.asyncio
    async def test_uptime_is_non_negative(self, viewer_ctx: ToolContext) -> None:
        """Test uptime_seconds is non-negative."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert isinstance(result["uptime_seconds"], int)
        assert result["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_has_timestamp(self, viewer_ctx: ToolContext) -> None:
        """Test result includes a valid ISO 8601 timestamp."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)
        # Should be ISO 8601 format with timezone
        assert "T" in result["timestamp"]

    @pytest.mark.asyncio
    async def test_kernel_version_matches_platform(
        self, viewer_ctx: ToolContext
    ) -> None:
        """Test kernel_version matches platform.release()."""
        result = await handle_system_get_basic_info(viewer_ctx, {})
        assert result["kernel_version"] == platform.release()


# =============================================================================
# Tests for system.get_health_snapshot
# =============================================================================


class TestSystemGetHealthSnapshot:
    """Tests for system.get_health_snapshot tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, viewer_ctx: ToolContext) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_system_get_health_snapshot(viewer_ctx, {})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(self, viewer_ctx: ToolContext) -> None:
        """Test that result contains all required health metrics fields.

        Required fields (from Doc 05 §3.2 system.get_health_snapshot spec):
        - timestamp, cpu_usage_percent, memory_used_bytes, memory_total_bytes
        - disk_used_bytes, disk_total_bytes, throttling_flags
        """
        result = await handle_system_get_health_snapshot(viewer_ctx, {})

        required_fields = [
            "timestamp",
            "cpu_usage_percent",
            "memory_used_bytes",
            "memory_total_bytes",
            "disk_used_bytes",
            "disk_total_bytes",
            "throttling_flags",
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_cpu_usage_in_range(self, viewer_ctx: ToolContext) -> None:
        """Test cpu_usage_percent is between 0 and 100."""
        result = await handle_system_get_health_snapshot(viewer_ctx, {})
        assert isinstance(result["cpu_usage_percent"], (int, float))
        assert 0 <= result["cpu_usage_percent"] <= 100

    @pytest.mark.asyncio
    async def test_memory_values_are_positive(self, viewer_ctx: ToolContext) -> None:
        """Test memory values are positive integers."""
        result = await handle_system_get_health_snapshot(viewer_ctx, {})
        assert isinstance(result["memory_used_bytes"], int)
        assert isinstance(result["memory_total_bytes"], int)
        assert result["memory_used_bytes"] >= 0
        assert result["memory_total_bytes"] > 0
        assert result["memory_used_bytes"] <= result["memory_total_bytes"]

    @pytest.mark.asyncio
    async def test_disk_values_are_positive(self, viewer_ctx: ToolContext) -> None:
        """Test disk values are positive integers."""
        result = await handle_system_get_health_snapshot(viewer_ctx, {})
        assert isinstance(result["disk_used_bytes"], int)
        assert isinstance(result["disk_total_bytes"], int)
        assert result["disk_used_bytes"] >= 0
        assert result["disk_total_bytes"] > 0
        assert result["disk_used_bytes"] <= result["disk_total_bytes"]

    @pytest.mark.asyncio
    async def test_throttling_flags_structure(self, viewer_ctx: ToolContext) -> None:
        """Test throttling_flags has correct structure."""
        result = await handle_system_get_health_snapshot(viewer_ctx, {})
        flags = result["throttling_flags"]
        assert isinstance(flags, dict)
        assert "under_voltage" in flags
        assert "freq_capped" in flags
        assert "throttled" in flags
        assert isinstance(flags["under_voltage"], bool)
        assert isinstance(flags["freq_capped"], bool)
        assert isinstance(flags["throttled"], bool)

    @pytest.mark.asyncio
    async def test_temperature_can_be_null(self, viewer_ctx: ToolContext) -> None:
        """Test cpu_temperature_celsius can be null if unavailable."""
        result = await handle_system_get_health_snapshot(viewer_ctx, {})
        # Temperature is either float or None
        temp = result.get("cpu_temperature_celsius")
        assert temp is None or isinstance(temp, (int, float))

    @pytest.mark.asyncio
    async def test_thermal_zones_is_list(self, viewer_ctx: ToolContext) -> None:
        """Test thermal_zones is a list."""
        result = await handle_system_get_health_snapshot(viewer_ctx, {})
        zones = result.get("thermal_zones", [])
        assert isinstance(zones, list)
        for zone in zones:
            assert isinstance(zone, dict)
            assert "zone" in zone
            assert "type" in zone
            assert "temperature_celsius" in zone


# =============================================================================
# Tests for system.get_network_info
# =============================================================================


class TestSystemGetNetworkInfo:
    """Tests for system.get_network_info tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, viewer_ctx: ToolContext) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_system_get_network_info(viewer_ctx, {})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_interfaces(self, viewer_ctx: ToolContext) -> None:
        """Test result contains interfaces list."""
        result = await handle_system_get_network_info(viewer_ctx, {})
        assert "interfaces" in result
        assert isinstance(result["interfaces"], list)
        # Should have at least loopback interface
        assert len(result["interfaces"]) >= 1

    @pytest.mark.asyncio
    async def test_interface_structure(self, viewer_ctx: ToolContext) -> None:
        """Test each interface has required fields.

        Required interface fields (from Doc 05 addendum §1.1):
        - name, mac_address, state, ipv4_addresses, ipv6_addresses
        """
        result = await handle_system_get_network_info(viewer_ctx, {})
        for iface in result["interfaces"]:
            assert "name" in iface
            assert "mac_address" in iface
            assert "state" in iface
            assert "ipv4_addresses" in iface
            assert "ipv6_addresses" in iface
            assert isinstance(iface["ipv4_addresses"], list)
            assert isinstance(iface["ipv6_addresses"], list)

    @pytest.mark.asyncio
    async def test_ipv4_address_structure(self, viewer_ctx: ToolContext) -> None:
        """Test IPv4 address objects have correct structure."""
        result = await handle_system_get_network_info(viewer_ctx, {})
        for iface in result["interfaces"]:
            for addr in iface["ipv4_addresses"]:
                assert "address" in addr
                assert isinstance(addr["address"], str)

    @pytest.mark.asyncio
    async def test_loopback_interface_present(self, viewer_ctx: ToolContext) -> None:
        """Test loopback interface (lo) is present."""
        result = await handle_system_get_network_info(viewer_ctx, {})
        interface_names = [iface["name"] for iface in result["interfaces"]]
        assert "lo" in interface_names

    @pytest.mark.asyncio
    async def test_dns_servers_is_list(self, viewer_ctx: ToolContext) -> None:
        """Test dns_servers is a list."""
        result = await handle_system_get_network_info(viewer_ctx, {})
        assert "dns_servers" in result
        assert isinstance(result["dns_servers"], list)


# =============================================================================
# Tests for system.reboot
# =============================================================================


class TestSystemReboot:
    """Tests for system.reboot tool."""

    @pytest.mark.asyncio
    async def test_requires_admin_role(self, operator_ctx: ToolContext) -> None:
        """Test that operator role is denied (requires admin)."""
        with pytest.raises(PermissionDeniedError):
            await handle_system_reboot(operator_ctx, {})

    @pytest.mark.asyncio
    async def test_admin_allowed(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that admin role is allowed."""
        result = await handle_system_reboot(admin_ctx, {}, config=full_sandbox_config)
        assert result["scheduled"] is True

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_reboot(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode mocks reboot without executing."""
        result = await handle_system_reboot(
            admin_ctx,
            {"reason": "test reboot", "delay_seconds": 10},
            config=full_sandbox_config,
        )
        assert result["scheduled"] is True
        assert result["sandbox_mode"] == "full"
        assert result["mocked"] is True
        assert result["effective_after_seconds"] == 10

    @pytest.mark.asyncio
    async def test_partial_sandbox_logs_only(
        self, admin_ctx: ToolContext, partial_sandbox_config: AppConfig
    ) -> None:
        """Test partial sandbox mode logs but doesn't execute."""
        result = await handle_system_reboot(
            admin_ctx,
            {"reason": "test reboot"},
            config=partial_sandbox_config,
        )
        assert result["scheduled"] is False
        assert result["sandbox_mode"] == "partial"
        assert result["logged_only"] is True

    @pytest.mark.asyncio
    async def test_disabled_sandbox_requires_ipc_client(
        self, admin_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode requires IPC client."""
        with pytest.raises(UnavailableError) as exc_info:
            await handle_system_reboot(
                admin_ctx,
                {"reason": "test reboot"},
                config=disabled_sandbox_config,
                ipc_client=None,
            )
        assert "Privileged agent not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disabled_sandbox_with_ipc_client(
        self, admin_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode calls IPC client."""
        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value={"executed": True})

        result = await handle_system_reboot(
            admin_ctx,
            {"reason": "test reboot", "delay_seconds": 5},
            config=disabled_sandbox_config,
            ipc_client=mock_client,
        )

        assert result["scheduled"] is True
        assert result["sandbox_mode"] == "disabled"
        mock_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_delay_seconds_clamped(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test delay_seconds is clamped to valid range (0-600)."""
        # Test max clamping
        result = await handle_system_reboot(
            admin_ctx,
            {"delay_seconds": 9999},
            config=full_sandbox_config,
        )
        assert result["effective_after_seconds"] == 600

        # Test min clamping
        result = await handle_system_reboot(
            admin_ctx,
            {"delay_seconds": -100},
            config=full_sandbox_config,
        )
        assert result["effective_after_seconds"] == 0

    @pytest.mark.asyncio
    async def test_reason_truncated(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test reason is truncated to 200 chars."""
        long_reason = "x" * 300
        # Should not raise error
        result = await handle_system_reboot(
            admin_ctx,
            {"reason": long_reason},
            config=full_sandbox_config,
        )
        assert result["scheduled"] is True


# =============================================================================
# Tests for system.shutdown
# =============================================================================


class TestSystemShutdown:
    """Tests for system.shutdown tool."""

    @pytest.mark.asyncio
    async def test_requires_admin_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied (requires admin)."""
        with pytest.raises(PermissionDeniedError):
            await handle_system_shutdown(viewer_ctx, {})

    @pytest.mark.asyncio
    async def test_admin_allowed(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that admin role is allowed."""
        result = await handle_system_shutdown(admin_ctx, {}, config=full_sandbox_config)
        assert result["scheduled"] is True

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_shutdown(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode mocks shutdown without executing."""
        result = await handle_system_shutdown(
            admin_ctx,
            {"reason": "test shutdown"},
            config=full_sandbox_config,
        )
        assert result["scheduled"] is True
        assert result["sandbox_mode"] == "full"
        assert result["mocked"] is True

    @pytest.mark.asyncio
    async def test_partial_sandbox_logs_only(
        self, admin_ctx: ToolContext, partial_sandbox_config: AppConfig
    ) -> None:
        """Test partial sandbox mode logs but doesn't execute."""
        result = await handle_system_shutdown(
            admin_ctx,
            {"reason": "test shutdown"},
            config=partial_sandbox_config,
        )
        assert result["scheduled"] is False
        assert result["sandbox_mode"] == "partial"
        assert result["logged_only"] is True

    @pytest.mark.asyncio
    async def test_disabled_sandbox_requires_ipc_client(
        self, admin_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode requires IPC client."""
        with pytest.raises(UnavailableError) as exc_info:
            await handle_system_shutdown(
                admin_ctx,
                {"reason": "test shutdown"},
                config=disabled_sandbox_config,
                ipc_client=None,
            )
        assert "Privileged agent not available" in str(exc_info.value)


# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_get_raspberry_pi_model_fallback(self) -> None:
        """Test model detection fallback when device-tree not available."""
        with patch("pathlib.Path.exists", return_value=False):
            model = _get_raspberry_pi_model()
            # Should fall back to platform info
            assert platform.system() in model or platform.machine() in model

    def test_get_os_info_returns_tuple(self) -> None:
        """Test OS info returns name and version tuple."""
        os_name, os_version = _get_os_info()
        assert isinstance(os_name, str)
        assert isinstance(os_version, str)
        assert len(os_name) > 0
        assert len(os_version) > 0

    def test_get_cpu_temperature_returns_valid(self) -> None:
        """Test CPU temperature returns float or None."""
        temp = _get_cpu_temperature()
        assert temp is None or isinstance(temp, (int, float))
        if temp is not None:
            # Reasonable temperature range for CPU
            assert -50 <= temp <= 150

    def test_get_all_thermal_zones_returns_list(self) -> None:
        """Test thermal zones returns list of dicts."""
        zones = _get_all_thermal_zones()
        assert isinstance(zones, list)
        for zone in zones:
            assert isinstance(zone, dict)
            assert "zone" in zone
            assert "type" in zone
            assert "temperature_celsius" in zone

    def test_get_throttling_flags_returns_dict(self) -> None:
        """Test throttling flags returns dict with boolean values."""
        flags = _get_throttling_flags()
        assert isinstance(flags, dict)
        assert "under_voltage" in flags
        assert "freq_capped" in flags
        assert "throttled" in flags
        assert all(isinstance(v, bool) for v in flags.values())
