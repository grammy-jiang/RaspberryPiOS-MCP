"""
Tests for GPIO namespace tools.

This test module validates:
- gpio.read_pin reads digital state with whitelist enforcement
- gpio.write_pin writes digital state with whitelist enforcement
- gpio.configure_pin configures pin mode and pull resistor
- gpio.set_pwm sets PWM output with frequency/duty cycle validation
- gpio.get_all_states returns state of all configured pins
- Operator role is required for all GPIO operations
- Sandbox mode handling (full=mocked, partial=logged, disabled=real)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_raspi.config import AppConfig, GPIOConfig, TestingConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import InvalidArgumentError, UnavailableError
from mcp_raspi.security.rbac import PermissionDeniedError
from mcp_raspi.tools.gpio import (
    handle_gpio_configure_pin,
    handle_gpio_get_all_states,
    handle_gpio_read_pin,
    handle_gpio_set_pwm,
    handle_gpio_write_pin,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="gpio.read_pin",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def operator_ctx() -> ToolContext:
    """Create a test context with operator role."""
    return ToolContext(
        tool_name="gpio.read_pin",
        caller=CallerInfo(user_id="operator@example.com", role="operator"),
        request_id="test-req-operator",
    )


@pytest.fixture
def admin_ctx() -> ToolContext:
    """Create a test context with admin role."""
    return ToolContext(
        tool_name="gpio.read_pin",
        caller=CallerInfo(user_id="admin@example.com", role="admin"),
        request_id="test-req-admin",
    )


@pytest.fixture
def full_sandbox_config() -> AppConfig:
    """Create config with full sandbox mode and GPIO whitelist."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.gpio = GPIOConfig(allowed_pins=[17, 18, 22, 23, 24, 25])
    return config


@pytest.fixture
def partial_sandbox_config() -> AppConfig:
    """Create config with partial sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="partial")
    config.gpio = GPIOConfig(allowed_pins=[17, 18, 22, 23, 24, 25])
    return config


@pytest.fixture
def disabled_sandbox_config() -> AppConfig:
    """Create config with disabled sandbox mode."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="disabled")
    config.gpio = GPIOConfig(allowed_pins=[17, 18, 22, 23, 24, 25])
    return config


# =============================================================================
# Tests for gpio.read_pin
# =============================================================================


class TestGpioReadPin:
    """Tests for gpio.read_pin tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied (requires operator)."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_read_pin(viewer_ctx, {"pin": 17})

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that operator role is allowed."""
        result = await handle_gpio_read_pin(
            operator_ctx, {"pin": 17}, config=full_sandbox_config
        )
        assert "pin" in result
        assert "value" in result

    @pytest.mark.asyncio
    async def test_admin_allowed(
        self, admin_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that admin role is allowed."""
        result = await handle_gpio_read_pin(
            admin_ctx, {"pin": 17}, config=full_sandbox_config
        )
        assert result["pin"] == 17

    @pytest.mark.asyncio
    async def test_whitelist_enforcement(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that non-whitelisted pins are rejected."""
        # Pin 5 is not in the whitelist [17, 18, 22, 23, 24, 25]
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_gpio_read_pin(
                operator_ctx, {"pin": 5}, config=full_sandbox_config
            )
        assert "not in the allowed GPIO pin whitelist" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_pin_number(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that invalid pin numbers are rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_read_pin(
                operator_ctx, {"pin": 50}, config=full_sandbox_config
            )
        assert "Pin number must be between 0 and 27" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_pin_parameter(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that missing pin parameter is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_read_pin(operator_ctx, {}, config=full_sandbox_config)
        assert "pin" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_read(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode returns mocked value."""
        result = await handle_gpio_read_pin(
            operator_ctx, {"pin": 17}, config=full_sandbox_config
        )
        assert result["pin"] == 17
        assert result["value"] == "low"
        assert result["mocked"] is True
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_partial_sandbox_logs_only(
        self, operator_ctx: ToolContext, partial_sandbox_config: AppConfig
    ) -> None:
        """Test partial sandbox mode logs but doesn't execute."""
        result = await handle_gpio_read_pin(
            operator_ctx, {"pin": 17}, config=partial_sandbox_config
        )
        assert result["pin"] == 17
        assert result["value"] == "unknown"
        assert result["logged_only"] is True

    @pytest.mark.asyncio
    async def test_disabled_sandbox_requires_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode requires IPC client."""
        with pytest.raises(UnavailableError) as exc_info:
            await handle_gpio_read_pin(
                operator_ctx, {"pin": 17}, config=disabled_sandbox_config
            )
        assert "Privileged agent not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disabled_sandbox_with_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode calls IPC client."""
        mock_client = MagicMock()
        mock_client.call = AsyncMock(return_value={"value": "high"})

        result = await handle_gpio_read_pin(
            operator_ctx,
            {"pin": 17},
            config=disabled_sandbox_config,
            ipc_client=mock_client,
        )

        assert result["pin"] == 17
        assert result["value"] == "high"
        mock_client.call.assert_called_once()


# =============================================================================
# Tests for gpio.write_pin
# =============================================================================


class TestGpioWritePin:
    """Tests for gpio.write_pin tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_write_pin(viewer_ctx, {"pin": 17, "value": "high"})

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that operator role is allowed."""
        result = await handle_gpio_write_pin(
            operator_ctx, {"pin": 17, "value": "high"}, config=full_sandbox_config
        )
        assert result["pin"] == 17
        assert result["value"] == "high"

    @pytest.mark.asyncio
    async def test_whitelist_enforcement(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that non-whitelisted pins are rejected."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_write_pin(
                operator_ctx, {"pin": 5, "value": "high"}, config=full_sandbox_config
            )

    @pytest.mark.asyncio
    async def test_invalid_value(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that invalid values are rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_write_pin(
                operator_ctx,
                {"pin": 17, "value": "invalid"},
                config=full_sandbox_config,
            )
        assert "high" in str(exc_info.value).lower()
        assert "low" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_duration_ms_validation(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test duration_ms parameter validation."""
        # Valid duration
        result = await handle_gpio_write_pin(
            operator_ctx,
            {"pin": 17, "value": "high", "duration_ms": 1000},
            config=full_sandbox_config,
        )
        assert result["duration_ms"] == 1000

        # Invalid duration (too large)
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_write_pin(
                operator_ctx,
                {"pin": 17, "value": "high", "duration_ms": 999999999},
                config=full_sandbox_config,
            )
        assert "duration_ms must be between" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_write(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode mocks write."""
        result = await handle_gpio_write_pin(
            operator_ctx,
            {"pin": 17, "value": "high"},
            config=full_sandbox_config,
        )
        assert result["mocked"] is True
        assert result["value"] == "high"


# =============================================================================
# Tests for gpio.configure_pin
# =============================================================================


class TestGpioConfigurePin:
    """Tests for gpio.configure_pin tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_configure_pin(viewer_ctx, {"pin": 17, "mode": "input"})

    @pytest.mark.asyncio
    async def test_valid_configuration(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test valid pin configuration."""
        result = await handle_gpio_configure_pin(
            operator_ctx,
            {"pin": 17, "mode": "input", "pull": "up"},
            config=full_sandbox_config,
        )
        assert result["pin"] == 17
        assert result["mode"] == "input"
        assert result["pull"] == "up"

    @pytest.mark.asyncio
    async def test_invalid_mode(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test invalid mode is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_configure_pin(
                operator_ctx,
                {"pin": 17, "mode": "invalid"},
                config=full_sandbox_config,
            )
        assert "input" in str(exc_info.value).lower()
        assert "output" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_pull(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test invalid pull mode is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_configure_pin(
                operator_ctx,
                {"pin": 17, "mode": "input", "pull": "invalid"},
                config=full_sandbox_config,
            )
        assert "none" in str(exc_info.value).lower()
        assert "up" in str(exc_info.value).lower()
        assert "down" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_default_pull_mode(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test default pull mode when not specified."""
        result = await handle_gpio_configure_pin(
            operator_ctx,
            {"pin": 17, "mode": "input"},
            config=full_sandbox_config,
        )
        assert result["pull"] == "none"

    @pytest.mark.asyncio
    async def test_whitelist_enforcement(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that non-whitelisted pins are rejected."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_configure_pin(
                operator_ctx,
                {"pin": 5, "mode": "input"},
                config=full_sandbox_config,
            )


# =============================================================================
# Tests for gpio.set_pwm
# =============================================================================


class TestGpioSetPwm:
    """Tests for gpio.set_pwm tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_set_pwm(
                viewer_ctx,
                {"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": 50},
            )

    @pytest.mark.asyncio
    async def test_valid_pwm_config(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test valid PWM configuration."""
        result = await handle_gpio_set_pwm(
            operator_ctx,
            {"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": 50},
            config=full_sandbox_config,
        )
        assert result["pin"] == 18
        assert result["frequency_hz"] == 1000.0
        assert result["duty_cycle_percent"] == 50.0

    @pytest.mark.asyncio
    async def test_frequency_validation(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test PWM frequency validation."""
        # Frequency too high
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_set_pwm(
                operator_ctx,
                {"pin": 18, "frequency_hz": 50000, "duty_cycle_percent": 50},
                config=full_sandbox_config,
            )
        assert "frequency_hz must be between 1 and 10000" in str(exc_info.value)

        # Frequency too low
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_set_pwm(
                operator_ctx,
                {"pin": 18, "frequency_hz": 0, "duty_cycle_percent": 50},
                config=full_sandbox_config,
            )
        assert "frequency_hz must be between 1 and 10000" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_duty_cycle_validation(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test PWM duty cycle validation."""
        # Duty cycle too high
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_set_pwm(
                operator_ctx,
                {"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": 150},
                config=full_sandbox_config,
            )
        assert "duty_cycle_percent" in str(exc_info.value)

        # Duty cycle negative
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_gpio_set_pwm(
                operator_ctx,
                {"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": -10},
                config=full_sandbox_config,
            )
        assert "duty_cycle_percent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_whitelist_enforcement(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that non-whitelisted pins are rejected."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_set_pwm(
                operator_ctx,
                {"pin": 5, "frequency_hz": 1000, "duty_cycle_percent": 50},
                config=full_sandbox_config,
            )


# =============================================================================
# Tests for gpio.get_all_states
# =============================================================================


class TestGpioGetAllStates:
    """Tests for gpio.get_all_states tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(self, viewer_ctx: ToolContext) -> None:
        """Test that viewer role is denied."""
        with pytest.raises(PermissionDeniedError):
            await handle_gpio_get_all_states(viewer_ctx, {})

    @pytest.mark.asyncio
    async def test_returns_all_pin_states(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that all configured pins are returned."""
        result = await handle_gpio_get_all_states(
            operator_ctx, {}, config=full_sandbox_config
        )
        assert "pins" in result
        assert isinstance(result["pins"], list)
        # Should have 6 pins from the whitelist
        assert len(result["pins"]) == 6

    @pytest.mark.asyncio
    async def test_pin_state_structure(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test pin state structure in response."""
        result = await handle_gpio_get_all_states(
            operator_ctx, {}, config=full_sandbox_config
        )
        for pin_info in result["pins"]:
            assert "pin" in pin_info
            assert "mode" in pin_info
            assert "value" in pin_info
            assert "allowed" in pin_info

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks_states(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode returns mocked states."""
        result = await handle_gpio_get_all_states(
            operator_ctx, {}, config=full_sandbox_config
        )
        assert result["mocked"] is True
        for pin_info in result["pins"]:
            assert pin_info["value"] == "low"
            assert pin_info["mode"] == "input"

    @pytest.mark.asyncio
    async def test_disabled_sandbox_requires_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode requires IPC client."""
        with pytest.raises(UnavailableError):
            await handle_gpio_get_all_states(
                operator_ctx, {}, config=disabled_sandbox_config
            )
