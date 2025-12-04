"""
Tests for I2C namespace tools.

This test module validates:
- i2c.scan_bus detects devices on I2C bus
- i2c.read reads bytes from I2C device with address whitelist
- i2c.write writes bytes to I2C device with address whitelist
- Address whitelist/blacklist enforcement
- Reserved address protection
- Operator role is required for all I2C operations
- Sandbox mode handling (full=mocked, partial=logged, disabled=real)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_raspi.config import AppConfig, I2CBusConfig, I2CConfig, TestingConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import (
    FailedPreconditionError,
    InvalidArgumentError,
    UnavailableError,
)
from mcp_raspi.security.rbac import PermissionDeniedError
from mcp_raspi.tools.i2c import (
    handle_i2c_read,
    handle_i2c_scan_bus,
    handle_i2c_write,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="i2c.scan_bus",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def operator_ctx() -> ToolContext:
    """Create a test context with operator role."""
    return ToolContext(
        tool_name="i2c.scan_bus",
        caller=CallerInfo(user_id="operator@example.com", role="operator"),
        request_id="test-req-operator",
    )


@pytest.fixture
def admin_ctx() -> ToolContext:
    """Create a test context with admin role."""
    return ToolContext(
        tool_name="i2c.scan_bus",
        caller=CallerInfo(user_id="admin@example.com", role="admin"),
        request_id="test-req-admin",
    )


@pytest.fixture
def full_sandbox_config() -> AppConfig:
    """Create config with full sandbox mode and I2C configuration."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.i2c = I2CConfig(
        buses=[
            I2CBusConfig(
                bus=1,
                mode="full",
                allow_addresses=[0x76, 0x77],  # BME280, BMP280
                deny_addresses=[],
            ),
        ]
    )
    return config


@pytest.fixture
def partial_sandbox_config() -> AppConfig:
    """Create config with partial sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="partial")
    config.i2c = I2CConfig(
        buses=[
            I2CBusConfig(
                bus=1,
                mode="full",
                allow_addresses=[0x76, 0x77],
                deny_addresses=[],
            ),
        ]
    )
    return config


@pytest.fixture
def disabled_sandbox_config() -> AppConfig:
    """Create config with disabled sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="disabled")
    config.i2c = I2CConfig(
        buses=[
            I2CBusConfig(
                bus=1,
                mode="full",
                allow_addresses=[0x76, 0x77],
                deny_addresses=[],
            ),
        ]
    )
    return config


@pytest.fixture
def read_only_config() -> AppConfig:
    """Create config with read-only I2C bus."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.i2c = I2CConfig(
        buses=[
            I2CBusConfig(
                bus=1,
                mode="read_only",
                allow_addresses=[0x76, 0x77],
                deny_addresses=[],
            ),
        ]
    )
    return config


@pytest.fixture
def disabled_bus_config() -> AppConfig:
    """Create config with disabled I2C bus."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.i2c = I2CConfig(
        buses=[
            I2CBusConfig(
                bus=1,
                mode="disabled",
                allow_addresses=[],
                deny_addresses=[],
            ),
        ]
    )
    return config


# =============================================================================
# Tests for i2c.scan_bus
# =============================================================================


class TestI2cScanBus:
    """Tests for i2c.scan_bus tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied (requires operator)."""
        with pytest.raises(PermissionDeniedError):
            await handle_i2c_scan_bus(viewer_ctx, {"bus": 1})

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that operator role is allowed."""
        result = await handle_i2c_scan_bus(
            operator_ctx, {"bus": 1}, config=full_sandbox_config
        )
        assert "bus" in result
        assert "addresses" in result

    @pytest.mark.asyncio
    async def test_admin_allowed(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that admin role is allowed."""
        result = await handle_i2c_scan_bus(
            admin_ctx, {"bus": 1}, config=full_sandbox_config
        )
        assert result["bus"] == 1

    @pytest.mark.asyncio
    async def test_invalid_bus_number(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that invalid bus numbers are rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_scan_bus(
                operator_ctx, {"bus": 99}, config=full_sandbox_config
            )
        assert "Bus number must be between 0 and 10" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_bus_parameter(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that missing bus parameter is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_scan_bus(operator_ctx, {}, config=full_sandbox_config)
        assert "bus" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_disabled_bus_rejected(
        self, operator_ctx: ToolContext, disabled_bus_config: AppConfig
    ) -> None:
        """Test that disabled bus is rejected."""
        with pytest.raises(FailedPreconditionError) as exc_info:
            await handle_i2c_scan_bus(
                operator_ctx, {"bus": 1}, config=disabled_bus_config
            )
        assert "disabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_scan(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode returns mocked devices."""
        result = await handle_i2c_scan_bus(
            operator_ctx, {"bus": 1}, config=full_sandbox_config
        )
        assert result["bus"] == 1
        assert result["mocked"] is True
        # Should return mock addresses for bus 1
        assert 0x76 in result["addresses"]
        assert 0x77 in result["addresses"]

    @pytest.mark.asyncio
    async def test_partial_sandbox_logs_only(
        self, operator_ctx: ToolContext, partial_sandbox_config: AppConfig
    ) -> None:
        """Test partial sandbox mode logs but doesn't execute."""
        result = await handle_i2c_scan_bus(
            operator_ctx, {"bus": 1}, config=partial_sandbox_config
        )
        assert result["bus"] == 1
        assert result["addresses"] == []
        assert result["logged_only"] is True

    @pytest.mark.asyncio
    async def test_disabled_sandbox_requires_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode requires IPC client."""
        with pytest.raises(UnavailableError) as exc_info:
            await handle_i2c_scan_bus(
                operator_ctx, {"bus": 1}, config=disabled_sandbox_config
            )
        assert "Privileged agent not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disabled_sandbox_with_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode calls IPC client."""
        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value={"addresses": [0x76]})

        result = await handle_i2c_scan_bus(
            operator_ctx,
            {"bus": 1},
            config=disabled_sandbox_config,
            ipc_client=mock_client,
        )

        assert result["bus"] == 1
        assert 0x76 in result["addresses"]
        mock_client.call.assert_called_once()


# =============================================================================
# Tests for i2c.read
# =============================================================================


class TestI2cRead:
    """Tests for i2c.read tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied."""
        with pytest.raises(PermissionDeniedError):
            await handle_i2c_read(
                viewer_ctx, {"bus": 1, "address": 0x76, "length": 1}
            )

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that operator role is allowed."""
        result = await handle_i2c_read(
            operator_ctx,
            {"bus": 1, "address": 0x76, "length": 4},
            config=full_sandbox_config,
        )
        assert result["bus"] == 1
        assert result["address"] == 0x76

    @pytest.mark.asyncio
    async def test_whitelist_enforcement(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that non-whitelisted addresses are rejected."""
        # Address 0x50 is not in the allow list [0x76, 0x77]
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_i2c_read(
                operator_ctx,
                {"bus": 1, "address": 0x50, "length": 1},
                config=full_sandbox_config,
            )
        assert "not in the allow list" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reserved_address_blocked(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that reserved addresses are blocked."""
        # Address 0x00 is reserved
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_i2c_read(
                operator_ctx,
                {"bus": 1, "address": 0x00, "length": 1},
                config=full_sandbox_config,
            )
        assert "reserved" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_address(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that invalid addresses are rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_read(
                operator_ctx,
                {"bus": 1, "address": 0x100, "length": 1},
                config=full_sandbox_config,
            )
        assert "address" in str(exc_info.value).lower()
        assert "between" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_hex_string_address(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that hex string addresses are accepted."""
        result = await handle_i2c_read(
            operator_ctx,
            {"bus": 1, "address": "0x76", "length": 1},
            config=full_sandbox_config,
        )
        assert result["address"] == 0x76

    @pytest.mark.asyncio
    async def test_length_validation(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test data length validation."""
        # Length too large
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_read(
                operator_ctx,
                {"bus": 1, "address": 0x76, "length": 100},
                config=full_sandbox_config,
            )
        assert "Length must be between 1 and 32" in str(exc_info.value)

        # Length zero
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_read(
                operator_ctx,
                {"bus": 1, "address": 0x76, "length": 0},
                config=full_sandbox_config,
            )
        assert "Length must be between 1 and 32" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_register_parameter(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test optional register parameter."""
        result = await handle_i2c_read(
            operator_ctx,
            {"bus": 1, "address": 0x76, "register": 0x00, "length": 4},
            config=full_sandbox_config,
        )
        assert result["register"] == 0x00

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_read(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode returns mocked data."""
        result = await handle_i2c_read(
            operator_ctx,
            {"bus": 1, "address": 0x76, "length": 4},
            config=full_sandbox_config,
        )
        assert result["mocked"] is True
        assert result["data"] == [0x00, 0x00, 0x00, 0x00]


# =============================================================================
# Tests for i2c.write
# =============================================================================


class TestI2cWrite:
    """Tests for i2c.write tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied."""
        with pytest.raises(PermissionDeniedError):
            await handle_i2c_write(
                viewer_ctx, {"bus": 1, "address": 0x76, "data": [0x01]}
            )

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that operator role is allowed."""
        result = await handle_i2c_write(
            operator_ctx,
            {"bus": 1, "address": 0x76, "data": [0x01, 0x02]},
            config=full_sandbox_config,
        )
        assert result["bus"] == 1
        assert result["address"] == 0x76

    @pytest.mark.asyncio
    async def test_whitelist_enforcement(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that non-whitelisted addresses are rejected for writes."""
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_i2c_write(
                operator_ctx,
                {"bus": 1, "address": 0x50, "data": [0x01]},
                config=full_sandbox_config,
            )
        assert "not allowed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_only_bus_blocks_write(
        self, operator_ctx: ToolContext, read_only_config: AppConfig
    ) -> None:
        """Test that read-only bus blocks write operations."""
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_i2c_write(
                operator_ctx,
                {"bus": 1, "address": 0x76, "data": [0x01]},
                config=read_only_config,
            )
        assert "read-only" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_data_validation(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test data bytes validation."""
        # Empty data
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_write(
                operator_ctx,
                {"bus": 1, "address": 0x76, "data": []},
                config=full_sandbox_config,
            )
        assert "Data length must be between" in str(exc_info.value)

        # Data too long
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_write(
                operator_ctx,
                {"bus": 1, "address": 0x76, "data": [0x00] * 100},
                config=full_sandbox_config,
            )
        assert "Data length must be between" in str(exc_info.value)

        # Invalid byte value
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_i2c_write(
                operator_ctx,
                {"bus": 1, "address": 0x76, "data": [256]},
                config=full_sandbox_config,
            )
        assert "must be between 0 and 255" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_register_parameter(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test optional register parameter."""
        result = await handle_i2c_write(
            operator_ctx,
            {"bus": 1, "address": 0x76, "register": 0xF4, "data": [0x2E]},
            config=full_sandbox_config,
        )
        assert result["register"] == 0xF4

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_write(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode mocks write."""
        result = await handle_i2c_write(
            operator_ctx,
            {"bus": 1, "address": 0x76, "data": [0x01, 0x02]},
            config=full_sandbox_config,
        )
        assert result["mocked"] is True
        assert result["bytes_written"] == 2

    @pytest.mark.asyncio
    async def test_partial_sandbox_logs_only(
        self, operator_ctx: ToolContext, partial_sandbox_config: AppConfig
    ) -> None:
        """Test partial sandbox mode logs but doesn't execute."""
        result = await handle_i2c_write(
            operator_ctx,
            {"bus": 1, "address": 0x76, "data": [0x01]},
            config=partial_sandbox_config,
        )
        assert result["logged_only"] is True
        assert result["bytes_written"] == 0

    @pytest.mark.asyncio
    async def test_disabled_sandbox_requires_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode requires IPC client."""
        with pytest.raises(UnavailableError):
            await handle_i2c_write(
                operator_ctx,
                {"bus": 1, "address": 0x76, "data": [0x01]},
                config=disabled_sandbox_config,
            )

    @pytest.mark.asyncio
    async def test_disabled_sandbox_with_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode calls IPC client."""
        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value={"bytes_written": 1})

        result = await handle_i2c_write(
            operator_ctx,
            {"bus": 1, "address": 0x76, "data": [0x01]},
            config=disabled_sandbox_config,
            ipc_client=mock_client,
        )

        assert result["bytes_written"] == 1
        mock_client.call.assert_called_once()
