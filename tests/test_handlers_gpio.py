"""
Tests for GPIO agent handlers.

This test module validates the GPIO handlers in the privileged agent:
- gpio.read: Read digital state from a GPIO pin
- gpio.write: Write digital state to a GPIO pin
- gpio.configure: Configure GPIO pin mode and pull resistor
- gpio.pwm: Set PWM output on a GPIO pin
- gpio.get_all_states: Get state of all configured pins

These tests use mocked gpiozero to avoid hardware dependencies.
"""

from __future__ import annotations

import pytest

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi_ops.handlers.gpio import (
    handle_gpio_configure,
    handle_gpio_get_all_states,
    handle_gpio_pwm,
    handle_gpio_read,
    handle_gpio_write,
    register_gpio_handlers,
)
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_request() -> IPCRequest:
    """Create a basic IPC request."""
    return IPCRequest.create(
        operation="gpio.read",
        params={},
        request_id="test-req-1",
    )


# =============================================================================
# Tests for gpio.read Handler
# =============================================================================


class TestGpioReadHandler:
    """Tests for gpio.read handler."""

    @pytest.mark.asyncio
    async def test_read_valid_pin(self) -> None:
        """Test reading a valid pin."""
        request = IPCRequest.create(
            operation="gpio.read",
            params={"pin": 17},
        )
        result = await handle_gpio_read(request)
        assert result["pin"] == 17
        assert result["value"] in ("high", "low")

    @pytest.mark.asyncio
    async def test_read_invalid_pin_number(self) -> None:
        """Test reading an invalid pin number."""
        request = IPCRequest.create(
            operation="gpio.read",
            params={"pin": 50},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_read(request)
        assert exc_info.value.code == "invalid_argument"
        assert "Pin number must be between 0 and 27" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_read_missing_pin(self) -> None:
        """Test reading without pin parameter."""
        request = IPCRequest.create(
            operation="gpio.read",
            params={},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_read(request)
        assert exc_info.value.code == "invalid_argument"
        assert "pin" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_read_string_pin_converted(self) -> None:
        """Test that string pin numbers are converted."""
        request = IPCRequest.create(
            operation="gpio.read",
            params={"pin": "17"},
        )
        result = await handle_gpio_read(request)
        assert result["pin"] == 17


# =============================================================================
# Tests for gpio.write Handler
# =============================================================================


class TestGpioWriteHandler:
    """Tests for gpio.write handler."""

    @pytest.mark.asyncio
    async def test_write_high(self) -> None:
        """Test writing high value to a pin."""
        request = IPCRequest.create(
            operation="gpio.write",
            params={"pin": 17, "value": "high"},
        )
        result = await handle_gpio_write(request)
        assert result["pin"] == 17
        assert result["value"] == "high"

    @pytest.mark.asyncio
    async def test_write_low(self) -> None:
        """Test writing low value to a pin."""
        request = IPCRequest.create(
            operation="gpio.write",
            params={"pin": 17, "value": "low"},
        )
        result = await handle_gpio_write(request)
        assert result["pin"] == 17
        assert result["value"] == "low"

    @pytest.mark.asyncio
    async def test_write_invalid_value(self) -> None:
        """Test writing invalid value."""
        request = IPCRequest.create(
            operation="gpio.write",
            params={"pin": 17, "value": "invalid"},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_write(request)
        assert exc_info.value.code == "invalid_argument"
        assert "high" in exc_info.value.message.lower()
        assert "low" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_write_with_duration(self) -> None:
        """Test writing with duration parameter."""
        request = IPCRequest.create(
            operation="gpio.write",
            params={"pin": 17, "value": "high", "duration_ms": 100},
        )
        result = await handle_gpio_write(request)
        assert result["duration_ms"] == 100

    @pytest.mark.asyncio
    async def test_write_invalid_pin(self) -> None:
        """Test writing to invalid pin."""
        request = IPCRequest.create(
            operation="gpio.write",
            params={"pin": 100, "value": "high"},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_write(request)
        assert exc_info.value.code == "invalid_argument"


# =============================================================================
# Tests for gpio.configure Handler
# =============================================================================


class TestGpioConfigureHandler:
    """Tests for gpio.configure handler."""

    @pytest.mark.asyncio
    async def test_configure_input(self) -> None:
        """Test configuring pin as input."""
        request = IPCRequest.create(
            operation="gpio.configure",
            params={"pin": 17, "mode": "input"},
        )
        result = await handle_gpio_configure(request)
        assert result["pin"] == 17
        assert result["mode"] == "input"

    @pytest.mark.asyncio
    async def test_configure_output(self) -> None:
        """Test configuring pin as output."""
        request = IPCRequest.create(
            operation="gpio.configure",
            params={"pin": 17, "mode": "output"},
        )
        result = await handle_gpio_configure(request)
        assert result["pin"] == 17
        assert result["mode"] == "output"

    @pytest.mark.asyncio
    async def test_configure_with_pull_up(self) -> None:
        """Test configuring pin with pull-up resistor."""
        request = IPCRequest.create(
            operation="gpio.configure",
            params={"pin": 17, "mode": "input", "pull": "up"},
        )
        result = await handle_gpio_configure(request)
        assert result["pull"] == "up"

    @pytest.mark.asyncio
    async def test_configure_with_pull_down(self) -> None:
        """Test configuring pin with pull-down resistor."""
        request = IPCRequest.create(
            operation="gpio.configure",
            params={"pin": 17, "mode": "input", "pull": "down"},
        )
        result = await handle_gpio_configure(request)
        assert result["pull"] == "down"

    @pytest.mark.asyncio
    async def test_configure_invalid_mode(self) -> None:
        """Test configuring with invalid mode."""
        request = IPCRequest.create(
            operation="gpio.configure",
            params={"pin": 17, "mode": "invalid"},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_configure(request)
        assert exc_info.value.code == "invalid_argument"
        assert "mode" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_configure_invalid_pull(self) -> None:
        """Test configuring with invalid pull setting."""
        request = IPCRequest.create(
            operation="gpio.configure",
            params={"pin": 17, "mode": "input", "pull": "invalid"},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_configure(request)
        assert exc_info.value.code == "invalid_argument"
        assert "pull" in exc_info.value.message.lower()


# =============================================================================
# Tests for gpio.pwm Handler
# =============================================================================


class TestGpioPwmHandler:
    """Tests for gpio.pwm handler."""

    @pytest.mark.asyncio
    async def test_pwm_valid_config(self) -> None:
        """Test valid PWM configuration."""
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": 50},
        )
        result = await handle_gpio_pwm(request)
        assert result["pin"] == 18
        assert result["frequency_hz"] == 1000.0
        assert result["duty_cycle_percent"] == 50.0

    @pytest.mark.asyncio
    async def test_pwm_boundary_frequency(self) -> None:
        """Test PWM with boundary frequencies."""
        # Minimum frequency
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "frequency_hz": 1, "duty_cycle_percent": 50},
        )
        result = await handle_gpio_pwm(request)
        assert result["frequency_hz"] == 1.0

        # Maximum frequency
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "frequency_hz": 10000, "duty_cycle_percent": 50},
        )
        result = await handle_gpio_pwm(request)
        assert result["frequency_hz"] == 10000.0

    @pytest.mark.asyncio
    async def test_pwm_boundary_duty_cycle(self) -> None:
        """Test PWM with boundary duty cycles."""
        # Minimum duty cycle
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": 0},
        )
        result = await handle_gpio_pwm(request)
        assert result["duty_cycle_percent"] == 0.0

        # Maximum duty cycle
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": 100},
        )
        result = await handle_gpio_pwm(request)
        assert result["duty_cycle_percent"] == 100.0

    @pytest.mark.asyncio
    async def test_pwm_frequency_too_high(self) -> None:
        """Test PWM with frequency too high."""
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "frequency_hz": 50000, "duty_cycle_percent": 50},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_pwm(request)
        assert exc_info.value.code == "invalid_argument"
        assert "frequency_hz must be between" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_pwm_duty_cycle_negative(self) -> None:
        """Test PWM with negative duty cycle."""
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "frequency_hz": 1000, "duty_cycle_percent": -10},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_pwm(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_pwm_missing_frequency(self) -> None:
        """Test PWM with missing frequency parameter."""
        request = IPCRequest.create(
            operation="gpio.pwm",
            params={"pin": 18, "duty_cycle_percent": 50},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_gpio_pwm(request)
        assert exc_info.value.code == "invalid_argument"
        assert "frequency_hz" in exc_info.value.message


# =============================================================================
# Tests for gpio.get_all_states Handler
# =============================================================================


class TestGpioGetAllStatesHandler:
    """Tests for gpio.get_all_states handler."""

    @pytest.mark.asyncio
    async def test_get_all_states_empty(self) -> None:
        """Test getting states with empty pin list."""
        request = IPCRequest.create(
            operation="gpio.get_all_states",
            params={"pins": []},
        )
        result = await handle_gpio_get_all_states(request)
        assert result["pins"] == []

    @pytest.mark.asyncio
    async def test_get_all_states_multiple_pins(self) -> None:
        """Test getting states for multiple pins."""
        request = IPCRequest.create(
            operation="gpio.get_all_states",
            params={"pins": [17, 18, 22]},
        )
        result = await handle_gpio_get_all_states(request)
        assert len(result["pins"]) == 3
        pin_numbers = [p["pin"] for p in result["pins"]]
        assert 17 in pin_numbers
        assert 18 in pin_numbers
        assert 22 in pin_numbers

    @pytest.mark.asyncio
    async def test_get_all_states_structure(self) -> None:
        """Test pin state structure in response."""
        request = IPCRequest.create(
            operation="gpio.get_all_states",
            params={"pins": [17]},
        )
        result = await handle_gpio_get_all_states(request)
        pin_info = result["pins"][0]
        assert "pin" in pin_info
        assert "mode" in pin_info
        assert "value" in pin_info
        assert "allowed" in pin_info


# =============================================================================
# Tests for Handler Registration
# =============================================================================


class TestGpioHandlerRegistration:
    """Tests for GPIO handler registration."""

    def test_register_gpio_handlers(self) -> None:
        """Test that GPIO handlers are registered correctly."""
        registry = HandlerRegistry()
        register_gpio_handlers(registry)

        assert registry.has_handler("gpio.read")
        assert registry.has_handler("gpio.write")
        assert registry.has_handler("gpio.configure")
        assert registry.has_handler("gpio.pwm")
        assert registry.has_handler("gpio.get_all_states")

    @pytest.mark.asyncio
    async def test_dispatch_gpio_read(self) -> None:
        """Test dispatching gpio.read through registry."""
        registry = HandlerRegistry()
        register_gpio_handlers(registry)

        request = IPCRequest.create(
            operation="gpio.read",
            params={"pin": 17},
        )
        result = await registry.dispatch(request)
        assert result["pin"] == 17
