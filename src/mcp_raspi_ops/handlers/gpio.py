"""
GPIO device handlers for the Privileged Agent.

This module implements handlers for GPIO operations using gpiozero:
- gpio.read: Read digital state from a GPIO pin
- gpio.write: Write digital state to a GPIO pin
- gpio.configure: Configure GPIO pin mode and pull resistor
- gpio.pwm: Set PWM output on a GPIO pin
- gpio.get_all_states: Get state of all configured pins

These handlers run with elevated privileges and execute actual hardware operations.

Design follows Doc 08 §3 (GPIO & PWM Design).
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

logger = get_logger(__name__)

# Try to import gpiozero for actual hardware access
try:
    from gpiozero import LED, InputDevice, OutputDevice, PWMOutputDevice

    GPIOZERO_AVAILABLE = True
except ImportError:  # pragma: no cover
    GPIOZERO_AVAILABLE = False
    logger.warning("gpiozero not available - GPIO operations will be mocked")


# Global pin tracking for state management
_configured_pins: dict[int, Any] = {}
_pwm_pins: dict[int, Any] = {}


# =============================================================================
# Helper Functions
# =============================================================================


def _validate_pin(pin: Any) -> int:
    """
    Validate and convert pin number.

    Args:
        pin: Raw pin value from request params.

    Returns:
        Validated pin number as integer.

    Raises:
        HandlerError: If pin is invalid.
    """
    if pin is None:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'pin' is required",
            details={"parameter": "pin"},
        )

    if not isinstance(pin, int):
        try:
            pin = int(pin)
        except (ValueError, TypeError) as e:
            raise HandlerError(
                code="invalid_argument",
                message=f"Invalid pin number: {pin}",
                details={"parameter": "pin", "value": pin},
            ) from e

    if pin < 0 or pin > 27:
        raise HandlerError(
            code="invalid_argument",
            message=f"Pin number must be between 0 and 27 (BCM), got {pin}",
            details={"parameter": "pin", "value": pin, "min": 0, "max": 27},
        )

    return pin


def _get_pin_device(pin: int) -> Any | None:
    """Get the device object for a configured pin."""
    return _configured_pins.get(pin)


def _get_pwm_device(pin: int) -> Any | None:
    """Get the PWM device object for a pin."""
    return _pwm_pins.get(pin)


def _cleanup_pin(pin: int) -> None:
    """Clean up and close pin devices."""
    if pin in _pwm_pins:
        try:
            _pwm_pins[pin].close()
        except Exception as e:
            logger.warning(f"Error closing PWM pin {pin}: {e}")
        del _pwm_pins[pin]

    if pin in _configured_pins:
        try:
            _configured_pins[pin].close()
        except Exception as e:
            logger.warning(f"Error closing pin {pin}: {e}")
        del _configured_pins[pin]


# =============================================================================
# gpio.read Handler
# =============================================================================


async def handle_gpio_read(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the gpio.read operation.

    Reads the digital state of a GPIO pin.

    Args:
        request: IPC request with params:
            - pin: BCM pin number to read

    Returns:
        Dict with pin number and value ("high" or "low").

    Raises:
        HandlerError: If pin is invalid or not configured.
    """
    params = request.params
    pin = _validate_pin(params.get("pin"))
    caller = params.get("caller", {})

    logger.debug(
        "GPIO read request",
        extra={
            "request_id": request.id,
            "pin": pin,
            "caller_user_id": caller.get("user_id"),
        },
    )

    if not GPIOZERO_AVAILABLE:
        # Mock mode - return simulated low state
        logger.info(f"GPIO read (mocked): pin={pin}")
        return {
            "pin": pin,
            "value": "low",
            "mocked": True,
        }

    # Get configured device
    device = _get_pin_device(pin)
    if device is None:
        # Not configured - create a temporary input device to read
        try:
            temp_device = InputDevice(pin)
            value = "high" if temp_device.value else "low"
            temp_device.close()
            return {
                "pin": pin,
                "value": value,
            }
        except Exception as e:
            raise HandlerError(
                code="failed_precondition",
                message=f"Failed to read GPIO pin {pin}: {e}",
                details={"pin": pin, "error": str(e)},
            ) from e

    # Read from configured device
    try:
        value = "high" if device.value else "low"
        return {
            "pin": pin,
            "value": value,
        }
    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to read GPIO pin {pin}: {e}",
            details={"pin": pin, "error": str(e)},
        ) from e


# =============================================================================
# gpio.write Handler
# =============================================================================


async def handle_gpio_write(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the gpio.write operation.

    Writes a digital value to a GPIO pin.

    Args:
        request: IPC request with params:
            - pin: BCM pin number to write
            - value: Value to write ("high" or "low")
            - duration_ms: Optional duration to hold value before reverting

    Returns:
        Dict with pin number and written value.

    Raises:
        HandlerError: If parameters are invalid or operation fails.
    """
    params = request.params
    pin = _validate_pin(params.get("pin"))
    value = params.get("value", "").lower()
    duration_ms = params.get("duration_ms")
    caller = params.get("caller", {})

    if value not in ("high", "low"):
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid value: {value}. Must be 'high' or 'low'",
            details={"parameter": "value", "value": value},
        )

    logger.info(
        "GPIO write request",
        extra={
            "request_id": request.id,
            "pin": pin,
            "value": value,
            "duration_ms": duration_ms,
            "caller_user_id": caller.get("user_id"),
        },
    )

    if not GPIOZERO_AVAILABLE:
        # Mock mode
        logger.info(f"GPIO write (mocked): pin={pin}, value={value}")
        return {
            "pin": pin,
            "value": value,
            "duration_ms": duration_ms,
            "mocked": True,
        }

    # Get or create output device
    device = _get_pin_device(pin)
    if device is None or not isinstance(device, (LED, OutputDevice)):
        # Clean up any existing pin configuration
        _cleanup_pin(pin)
        try:
            device = OutputDevice(pin)
            _configured_pins[pin] = device
        except Exception as e:
            raise HandlerError(
                code="failed_precondition",
                message=f"Failed to configure GPIO pin {pin} for output: {e}",
                details={"pin": pin, "error": str(e)},
            ) from e

    # Write value
    try:
        if value == "high":
            device.on()
        else:
            device.off()

        # Handle duration (auto-revert)
        if duration_ms is not None and duration_ms > 0:
            async def revert_after_delay() -> None:
                await asyncio.sleep(duration_ms / 1000.0)
                try:
                    if value == "high":
                        device.off()
                    else:
                        device.on()
                    logger.debug(f"GPIO pin {pin} reverted after {duration_ms}ms")
                except Exception as e:
                    logger.warning(f"Failed to revert GPIO pin {pin}: {e}")

            # Schedule revert task (fire and forget)
            asyncio.create_task(revert_after_delay())

        return {
            "pin": pin,
            "value": value,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to write GPIO pin {pin}: {e}",
            details={"pin": pin, "value": value, "error": str(e)},
        ) from e


# =============================================================================
# gpio.configure Handler
# =============================================================================


async def handle_gpio_configure(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the gpio.configure operation.

    Configures GPIO pin mode (input/output) and pull resistor.

    Args:
        request: IPC request with params:
            - pin: BCM pin number to configure
            - mode: Pin mode ("input" or "output")
            - pull: Pull resistor setting ("none", "up", "down")

    Returns:
        Dict with configured pin state.

    Raises:
        HandlerError: If parameters are invalid or operation fails.
    """
    params = request.params
    pin = _validate_pin(params.get("pin"))
    mode = params.get("mode", "").lower()
    pull = params.get("pull", "none").lower()
    caller = params.get("caller", {})

    if mode not in ("input", "output"):
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid mode: {mode}. Must be 'input' or 'output'",
            details={"parameter": "mode", "value": mode},
        )

    if pull not in ("none", "up", "down"):
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid pull: {pull}. Must be 'none', 'up', or 'down'",
            details={"parameter": "pull", "value": pull},
        )

    logger.info(
        "GPIO configure request",
        extra={
            "request_id": request.id,
            "pin": pin,
            "mode": mode,
            "pull": pull,
            "caller_user_id": caller.get("user_id"),
        },
    )

    if not GPIOZERO_AVAILABLE:
        # Mock mode
        logger.info(f"GPIO configure (mocked): pin={pin}, mode={mode}, pull={pull}")
        return {
            "pin": pin,
            "mode": mode,
            "pull": pull,
            "value": "low" if mode == "output" else None,
            "mocked": True,
        }

    # Clean up existing configuration
    _cleanup_pin(pin)

    try:
        if mode == "input":
            # Map pull setting
            pull_up = pull == "up"
            pull_down = pull == "down"

            if pull_up:
                device = InputDevice(pin, pull_up=True)
            elif pull_down:
                # gpiozero doesn't directly support pull_down for InputDevice
                # Use active_state to handle inverted logic
                device = InputDevice(pin, pull_up=False)
            else:
                device = InputDevice(pin, pull_up=None)

            _configured_pins[pin] = device
            current_value = "high" if device.value else "low"

        else:  # output
            device = OutputDevice(pin, initial_value=False)
            _configured_pins[pin] = device
            current_value = "low"

        return {
            "pin": pin,
            "mode": mode,
            "pull": pull,
            "value": current_value,
        }

    except Exception as e:
        raise HandlerError(
            code="failed_precondition",
            message=f"Failed to configure GPIO pin {pin}: {e}",
            details={"pin": pin, "mode": mode, "pull": pull, "error": str(e)},
        ) from e


# =============================================================================
# gpio.pwm Handler
# =============================================================================


async def handle_gpio_pwm(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the gpio.pwm operation.

    Sets PWM output on a GPIO pin.

    Args:
        request: IPC request with params:
            - pin: BCM pin number for PWM
            - frequency_hz: PWM frequency (1-10000 Hz)
            - duty_cycle_percent: Duty cycle (0-100%)

    Returns:
        Dict with PWM configuration.

    Raises:
        HandlerError: If parameters are invalid or operation fails.
    """
    params = request.params
    pin = _validate_pin(params.get("pin"))
    frequency_hz = params.get("frequency_hz")
    duty_cycle_percent = params.get("duty_cycle_percent")
    caller = params.get("caller", {})

    # Validate frequency
    if frequency_hz is None:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'frequency_hz' is required",
            details={"parameter": "frequency_hz"},
        )

    try:
        frequency_hz = float(frequency_hz)
    except (ValueError, TypeError) as e:
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid frequency_hz: {frequency_hz}",
            details={"parameter": "frequency_hz", "value": frequency_hz},
        ) from e

    if frequency_hz < 1 or frequency_hz > 10000:
        raise HandlerError(
            code="invalid_argument",
            message=f"frequency_hz must be between 1 and 10000, got {frequency_hz}",
            details={
                "parameter": "frequency_hz",
                "value": frequency_hz,
                "min": 1,
                "max": 10000,
            },
        )

    # Validate duty cycle
    if duty_cycle_percent is None:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'duty_cycle_percent' is required",
            details={"parameter": "duty_cycle_percent"},
        )

    try:
        duty_cycle_percent = float(duty_cycle_percent)
    except (ValueError, TypeError) as e:
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid duty_cycle_percent: {duty_cycle_percent}",
            details={"parameter": "duty_cycle_percent", "value": duty_cycle_percent},
        ) from e

    if duty_cycle_percent < 0 or duty_cycle_percent > 100:
        raise HandlerError(
            code="invalid_argument",
            message=f"duty_cycle_percent must be between 0 and 100, got {duty_cycle_percent}",
            details={
                "parameter": "duty_cycle_percent",
                "value": duty_cycle_percent,
                "min": 0,
                "max": 100,
            },
        )

    logger.info(
        "GPIO PWM request",
        extra={
            "request_id": request.id,
            "pin": pin,
            "frequency_hz": frequency_hz,
            "duty_cycle_percent": duty_cycle_percent,
            "caller_user_id": caller.get("user_id"),
        },
    )

    if not GPIOZERO_AVAILABLE:
        # Mock mode
        logger.info(
            f"GPIO PWM (mocked): pin={pin}, freq={frequency_hz}Hz, duty={duty_cycle_percent}%"
        )
        return {
            "pin": pin,
            "frequency_hz": frequency_hz,
            "duty_cycle_percent": duty_cycle_percent,
            "mocked": True,
        }

    # Clean up any existing non-PWM configuration
    if pin in _configured_pins:
        _cleanup_pin(pin)

    try:
        # Get or create PWM device
        pwm_device = _get_pwm_device(pin)
        if pwm_device is None:
            pwm_device = PWMOutputDevice(
                pin,
                frequency=int(frequency_hz),
                initial_value=duty_cycle_percent / 100.0,
            )
            _pwm_pins[pin] = pwm_device
        else:
            # Update existing PWM device
            pwm_device.frequency = int(frequency_hz)
            pwm_device.value = duty_cycle_percent / 100.0

        return {
            "pin": pin,
            "frequency_hz": frequency_hz,
            "duty_cycle_percent": duty_cycle_percent,
        }

    except Exception as e:
        raise HandlerError(
            code="failed_precondition",
            message=f"Failed to set PWM on GPIO pin {pin}: {e}",
            details={
                "pin": pin,
                "frequency_hz": frequency_hz,
                "duty_cycle_percent": duty_cycle_percent,
                "error": str(e),
            },
        ) from e


# =============================================================================
# gpio.get_all_states Handler
# =============================================================================


async def handle_gpio_get_all_states(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the gpio.get_all_states operation.

    Gets the state of all configured GPIO pins.

    Args:
        request: IPC request with params:
            - pins: List of BCM pin numbers to query

    Returns:
        Dict with list of pin states.

    Raises:
        HandlerError: If operation fails.
    """
    params = request.params
    pins = params.get("pins", [])
    caller = params.get("caller", {})

    logger.debug(
        "GPIO get_all_states request",
        extra={
            "request_id": request.id,
            "pins": pins,
            "caller_user_id": caller.get("user_id"),
        },
    )

    pin_states = []

    if not GPIOZERO_AVAILABLE:
        # Mock mode
        logger.info(f"GPIO get_all_states (mocked): pins={pins}")
        for pin in pins:
            pin_states.append({
                "pin": pin,
                "mode": "input",
                "value": "low",
                "allowed": True,
                "mocked": True,
            })
        return {"pins": pin_states}

    for pin in pins:
        try:
            pin = int(pin)
            device = _get_pin_device(pin)
            pwm_device = _get_pwm_device(pin)

            if pwm_device is not None:
                # PWM configured
                pin_states.append({
                    "pin": pin,
                    "mode": "pwm",
                    "value": None,
                    "frequency_hz": pwm_device.frequency,
                    "duty_cycle_percent": pwm_device.value * 100,
                    "allowed": True,
                })
            elif device is not None:
                # Regular GPIO configured
                mode = "output" if isinstance(device, (LED, OutputDevice)) else "input"
                value = "high" if device.value else "low"
                pin_states.append({
                    "pin": pin,
                    "mode": mode,
                    "value": value,
                    "allowed": True,
                })
            else:
                # Not configured - try to read current state
                try:
                    temp_device = InputDevice(pin)
                    value = "high" if temp_device.value else "low"
                    temp_device.close()
                    pin_states.append({
                        "pin": pin,
                        "mode": "unknown",
                        "value": value,
                        "allowed": True,
                    })
                except Exception:
                    pin_states.append({
                        "pin": pin,
                        "mode": "unknown",
                        "value": "unknown",
                        "allowed": True,
                    })

        except Exception as e:
            logger.warning(f"Failed to get state for pin {pin}: {e}")
            pin_states.append({
                "pin": pin,
                "mode": "error",
                "value": None,
                "error": str(e),
                "allowed": True,
            })

    return {"pins": pin_states}


# =============================================================================
# Handler Registration
# =============================================================================


def register_gpio_handlers(registry: HandlerRegistry) -> None:
    """
    Register GPIO handlers with the handler registry.

    Args:
        registry: The handler registry to register with.
    """
    registry.register("gpio.read", handle_gpio_read)
    registry.register("gpio.write", handle_gpio_write)
    registry.register("gpio.configure", handle_gpio_configure)
    registry.register("gpio.pwm", handle_gpio_pwm)
    registry.register("gpio.get_all_states", handle_gpio_get_all_states)
    logger.debug("Registered GPIO handlers")
