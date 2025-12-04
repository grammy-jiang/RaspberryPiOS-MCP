"""
GPIO namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `gpio.*` namespace:
- gpio.read_pin: Read digital state from a GPIO pin
- gpio.write_pin: Write digital state with whitelist enforcement
- gpio.configure_pin: Set pin mode (in/out), pull-up/down
- gpio.set_pwm: Basic PWM output
- gpio.get_all_states: Bulk read all configured pins

Design follows Doc 05 §5 (gpio namespace specification) and Doc 08 §3 (GPIO design).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import (
    InvalidArgumentError,
    UnavailableError,
)
from mcp_raspi.logging import get_logger
from mcp_raspi.security.audit_logger import get_audit_logger
from mcp_raspi.security.rbac import require_role

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Valid GPIO pin modes
VALID_PIN_MODES = {"input", "output"}

# Valid pull resistor configurations
VALID_PULL_MODES = {"none", "up", "down"}

# Valid pin values for read/write
VALID_PIN_VALUES = {"high", "low"}

# PWM frequency constraints (Phase 1: conservative limits)
MIN_PWM_FREQUENCY_HZ = 1
MAX_PWM_FREQUENCY_HZ = 10000  # 10 kHz max for Phase 1

# PWM duty cycle constraints
MIN_DUTY_CYCLE_PERCENT = 0.0
MAX_DUTY_CYCLE_PERCENT = 100.0

# Duration constraints for write_pin with auto-revert
MIN_DURATION_MS = 1
MAX_DURATION_MS = 600000  # 10 minutes max


# =============================================================================
# Validation Helpers
# =============================================================================


def _validate_pin_in_whitelist(
    pin: int, allowed_pins: list[int], operation: str
) -> None:
    """
    Validate that a pin is in the allowed whitelist.

    Args:
        pin: BCM pin number.
        allowed_pins: List of allowed BCM pin numbers.
        operation: Name of the operation for error messages.

    Raises:
        PermissionDeniedError: If pin is not in whitelist.
    """
    if pin not in allowed_pins:
        from mcp_raspi.security.rbac import PermissionDeniedError

        raise PermissionDeniedError(
            f"Pin {pin} is not in the allowed GPIO pin whitelist",
            details={
                "pin": pin,
                "operation": operation,
                "allowed_pins": allowed_pins,
            },
        )


def _validate_pin_number(pin: Any) -> int:
    """
    Validate and convert pin number.

    Args:
        pin: Raw pin value from params.

    Returns:
        Validated pin number as integer.

    Raises:
        InvalidArgumentError: If pin is invalid.
    """
    if pin is None:
        raise InvalidArgumentError(
            "Parameter 'pin' is required",
            details={"parameter": "pin"},
        )

    if not isinstance(pin, int):
        try:
            pin = int(pin)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid pin number: {pin}",
                details={"parameter": "pin", "value": pin},
            ) from e

    # BCM numbering: valid range is 0-27 for most Raspberry Pi models
    if pin < 0 or pin > 27:
        raise InvalidArgumentError(
            f"Pin number must be between 0 and 27 (BCM numbering), got {pin}",
            details={"parameter": "pin", "value": pin, "min": 0, "max": 27},
        )

    return pin


def _validate_pin_mode(mode: Any) -> str:
    """
    Validate pin mode.

    Args:
        mode: Raw mode value from params.

    Returns:
        Validated mode string.

    Raises:
        InvalidArgumentError: If mode is invalid.
    """
    if mode is None:
        raise InvalidArgumentError(
            "Parameter 'mode' is required",
            details={"parameter": "mode"},
        )

    mode_str = str(mode).lower()
    if mode_str not in VALID_PIN_MODES:
        raise InvalidArgumentError(
            f"Invalid pin mode: {mode}. Must be one of: {', '.join(VALID_PIN_MODES)}",
            details={
                "parameter": "mode",
                "value": mode,
                "valid_values": list(VALID_PIN_MODES),
            },
        )
    return mode_str


def _validate_pull_mode(pull: Any) -> str:
    """
    Validate pull resistor mode.

    Args:
        pull: Raw pull value from params.

    Returns:
        Validated pull string.

    Raises:
        InvalidArgumentError: If pull mode is invalid.
    """
    if pull is None:
        return "none"

    pull_str = str(pull).lower()
    if pull_str not in VALID_PULL_MODES:
        raise InvalidArgumentError(
            f"Invalid pull mode: {pull}. Must be one of: {', '.join(VALID_PULL_MODES)}",
            details={
                "parameter": "pull",
                "value": pull,
                "valid_values": list(VALID_PULL_MODES),
            },
        )
    return pull_str


def _validate_pin_value(value: Any) -> str:
    """
    Validate pin value (high/low).

    Args:
        value: Raw value from params.

    Returns:
        Validated value string.

    Raises:
        InvalidArgumentError: If value is invalid.
    """
    if value is None:
        raise InvalidArgumentError(
            "Parameter 'value' is required",
            details={"parameter": "value"},
        )

    value_str = str(value).lower()
    if value_str not in VALID_PIN_VALUES:
        raise InvalidArgumentError(
            f"Invalid pin value: {value}. Must be one of: {', '.join(VALID_PIN_VALUES)}",
            details={
                "parameter": "value",
                "value": value,
                "valid_values": list(VALID_PIN_VALUES),
            },
        )
    return value_str


def _validate_duration_ms(duration_ms: Any) -> int | None:
    """
    Validate optional duration parameter.

    Args:
        duration_ms: Raw duration value from params.

    Returns:
        Validated duration in milliseconds, or None if not provided.

    Raises:
        InvalidArgumentError: If duration is invalid.
    """
    if duration_ms is None:
        return None

    if not isinstance(duration_ms, int):
        try:
            duration_ms = int(duration_ms)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid duration_ms: {duration_ms}",
                details={"parameter": "duration_ms", "value": duration_ms},
            ) from e

    if duration_ms < MIN_DURATION_MS or duration_ms > MAX_DURATION_MS:
        raise InvalidArgumentError(
            f"duration_ms must be between {MIN_DURATION_MS} and {MAX_DURATION_MS}",
            details={
                "parameter": "duration_ms",
                "value": duration_ms,
                "min": MIN_DURATION_MS,
                "max": MAX_DURATION_MS,
            },
        )

    return duration_ms


def _validate_pwm_frequency(frequency_hz: Any) -> float:
    """
    Validate PWM frequency.

    Args:
        frequency_hz: Raw frequency value from params.

    Returns:
        Validated frequency in Hz.

    Raises:
        InvalidArgumentError: If frequency is invalid.
    """
    if frequency_hz is None:
        raise InvalidArgumentError(
            "Parameter 'frequency_hz' is required",
            details={"parameter": "frequency_hz"},
        )

    if not isinstance(frequency_hz, (int, float)):
        try:
            frequency_hz = float(frequency_hz)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid frequency_hz: {frequency_hz}",
                details={"parameter": "frequency_hz", "value": frequency_hz},
            ) from e

    if frequency_hz < MIN_PWM_FREQUENCY_HZ or frequency_hz > MAX_PWM_FREQUENCY_HZ:
        raise InvalidArgumentError(
            f"frequency_hz must be between {MIN_PWM_FREQUENCY_HZ} and {MAX_PWM_FREQUENCY_HZ}",
            details={
                "parameter": "frequency_hz",
                "value": frequency_hz,
                "min": MIN_PWM_FREQUENCY_HZ,
                "max": MAX_PWM_FREQUENCY_HZ,
            },
        )

    return float(frequency_hz)


def _validate_duty_cycle(duty_cycle_percent: Any) -> float:
    """
    Validate PWM duty cycle.

    Args:
        duty_cycle_percent: Raw duty cycle value from params.

    Returns:
        Validated duty cycle as percentage.

    Raises:
        InvalidArgumentError: If duty cycle is invalid.
    """
    if duty_cycle_percent is None:
        raise InvalidArgumentError(
            "Parameter 'duty_cycle_percent' is required",
            details={"parameter": "duty_cycle_percent"},
        )

    if not isinstance(duty_cycle_percent, (int, float)):
        try:
            duty_cycle_percent = float(duty_cycle_percent)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid duty_cycle_percent: {duty_cycle_percent}",
                details={
                    "parameter": "duty_cycle_percent",
                    "value": duty_cycle_percent,
                },
            ) from e

    if (
        duty_cycle_percent < MIN_DUTY_CYCLE_PERCENT
        or duty_cycle_percent > MAX_DUTY_CYCLE_PERCENT
    ):
        raise InvalidArgumentError(
            f"duty_cycle_percent must be between {MIN_DUTY_CYCLE_PERCENT} and {MAX_DUTY_CYCLE_PERCENT}",
            details={
                "parameter": "duty_cycle_percent",
                "value": duty_cycle_percent,
                "min": MIN_DUTY_CYCLE_PERCENT,
                "max": MAX_DUTY_CYCLE_PERCENT,
            },
        )

    return float(duty_cycle_percent)


def _get_allowed_pins(config: AppConfig | None) -> list[int]:
    """
    Get the list of allowed GPIO pins from configuration.

    Args:
        config: Optional AppConfig instance.

    Returns:
        List of allowed BCM pin numbers.
    """
    if config is None:
        return []
    return config.gpio.allowed_pins


def _get_sandbox_mode(config: AppConfig | None) -> str:
    """
    Get sandbox mode from configuration.

    Args:
        config: Optional AppConfig instance.

    Returns:
        Sandbox mode string.
    """
    if config is None:
        return "partial"
    return config.testing.sandbox_mode


# =============================================================================
# gpio.read_pin
# =============================================================================


@require_role("operator")
async def handle_gpio_read_pin(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the gpio.read_pin tool call.

    Reads the digital state of a GPIO pin.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - pin: BCM pin number to read
        config: Optional AppConfig for whitelist and sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - pin: The pin number read
        - value: Pin state ("high" or "low")
        - timestamp: ISO 8601 timestamp

    Raises:
        PermissionDeniedError: If caller lacks operator role or pin not whitelisted.
        InvalidArgumentError: If pin number is invalid.
        UnavailableError: If privileged agent is unavailable.
    """
    pin = _validate_pin_number(params.get("pin"))
    allowed_pins = _get_allowed_pins(config)
    sandbox_mode = _get_sandbox_mode(config)

    # Check whitelist
    _validate_pin_in_whitelist(pin, allowed_pins, "gpio.read_pin")

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"pin": pin},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "GPIO read_pin requested",
        extra={
            "user": ctx.caller.user_id,
            "pin": pin,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking GPIO read")
        return {
            "pin": pin,
            "value": "low",  # Mock value
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging GPIO read (not executing)")
        return {
            "pin": pin,
            "value": "unknown",
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for GPIO read operation",
                details={"operation": "gpio.read_pin", "pin": pin},
            )

        try:
            result = await ipc_client.call(
                "gpio.read",
                {"pin": pin, "caller": ctx.caller.to_dict()},
            )
            return {
                "pin": pin,
                "value": result.get("value", "unknown"),
                "timestamp": datetime.now(UTC).isoformat(),
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to read GPIO pin via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"pin": pin},
            )
            raise UnavailableError(
                f"Failed to read GPIO pin: {e}",
                details={"operation": "gpio.read_pin", "pin": pin},
            ) from e


# =============================================================================
# gpio.write_pin
# =============================================================================


@require_role("operator")
async def handle_gpio_write_pin(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the gpio.write_pin tool call.

    Writes a digital state to a GPIO pin with whitelist enforcement.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - pin: BCM pin number to write
            - value: Value to write ("high" or "low")
            - duration_ms: Optional duration to maintain the value before reverting
        config: Optional AppConfig for whitelist and sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - pin: The pin number written
        - value: Value written
        - duration_ms: Duration if specified
        - timestamp: ISO 8601 timestamp

    Raises:
        PermissionDeniedError: If caller lacks operator role or pin not whitelisted.
        InvalidArgumentError: If parameters are invalid.
        UnavailableError: If privileged agent is unavailable.
    """
    pin = _validate_pin_number(params.get("pin"))
    value = _validate_pin_value(params.get("value"))
    duration_ms = _validate_duration_ms(params.get("duration_ms"))
    allowed_pins = _get_allowed_pins(config)
    sandbox_mode = _get_sandbox_mode(config)

    # Check whitelist
    _validate_pin_in_whitelist(pin, allowed_pins, "gpio.write_pin")

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"pin": pin, "value": value, "duration_ms": duration_ms},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "GPIO write_pin requested",
        extra={
            "user": ctx.caller.user_id,
            "pin": pin,
            "value": value,
            "duration_ms": duration_ms,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking GPIO write")
        return {
            "pin": pin,
            "value": value,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging GPIO write (not executing)")
        return {
            "pin": pin,
            "value": value,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for GPIO write operation",
                details={"operation": "gpio.write_pin", "pin": pin},
            )

        try:
            result = await ipc_client.call(
                "gpio.write",
                {
                    "pin": pin,
                    "value": value,
                    "duration_ms": duration_ms,
                    "caller": ctx.caller.to_dict(),
                },
            )
            return {
                "pin": pin,
                "value": value,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(UTC).isoformat(),
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to write GPIO pin via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"pin": pin, "value": value},
            )
            raise UnavailableError(
                f"Failed to write GPIO pin: {e}",
                details={"operation": "gpio.write_pin", "pin": pin},
            ) from e


# =============================================================================
# gpio.configure_pin
# =============================================================================


@require_role("operator")
async def handle_gpio_configure_pin(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the gpio.configure_pin tool call.

    Configures a GPIO pin mode and pull resistor.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - pin: BCM pin number to configure
            - mode: Pin mode ("input" or "output")
            - pull: Pull resistor ("none", "up", or "down")
        config: Optional AppConfig for whitelist and sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with configured pin state.

    Raises:
        PermissionDeniedError: If caller lacks operator role or pin not whitelisted.
        InvalidArgumentError: If parameters are invalid.
        UnavailableError: If privileged agent is unavailable.
    """
    pin = _validate_pin_number(params.get("pin"))
    mode = _validate_pin_mode(params.get("mode"))
    pull = _validate_pull_mode(params.get("pull"))
    allowed_pins = _get_allowed_pins(config)
    sandbox_mode = _get_sandbox_mode(config)

    # Check whitelist
    _validate_pin_in_whitelist(pin, allowed_pins, "gpio.configure_pin")

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"pin": pin, "mode": mode, "pull": pull},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "GPIO configure_pin requested",
        extra={
            "user": ctx.caller.user_id,
            "pin": pin,
            "mode": mode,
            "pull": pull,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking GPIO configure")
        return {
            "pin": pin,
            "mode": mode,
            "pull": pull,
            "value": "low" if mode == "output" else None,
            "allowed": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging GPIO configure (not executing)")
        return {
            "pin": pin,
            "mode": mode,
            "pull": pull,
            "value": None,
            "allowed": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for GPIO configure operation",
                details={"operation": "gpio.configure_pin", "pin": pin},
            )

        try:
            result = await ipc_client.call(
                "gpio.configure",
                {
                    "pin": pin,
                    "mode": mode,
                    "pull": pull,
                    "caller": ctx.caller.to_dict(),
                },
            )
            return {
                "pin": pin,
                "mode": mode,
                "pull": pull,
                "allowed": True,
                "timestamp": datetime.now(UTC).isoformat(),
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to configure GPIO pin via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"pin": pin, "mode": mode, "pull": pull},
            )
            raise UnavailableError(
                f"Failed to configure GPIO pin: {e}",
                details={"operation": "gpio.configure_pin", "pin": pin},
            ) from e


# =============================================================================
# gpio.set_pwm
# =============================================================================


@require_role("operator")
async def handle_gpio_set_pwm(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the gpio.set_pwm tool call.

    Sets PWM output on a GPIO pin with specified frequency and duty cycle.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - pin: BCM pin number for PWM output
            - frequency_hz: PWM frequency (1-10000 Hz)
            - duty_cycle_percent: Duty cycle (0-100%)
        config: Optional AppConfig for whitelist and sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with PWM configuration state.

    Raises:
        PermissionDeniedError: If caller lacks operator role or pin not whitelisted.
        InvalidArgumentError: If parameters are invalid.
        UnavailableError: If privileged agent is unavailable.
    """
    pin = _validate_pin_number(params.get("pin"))
    frequency_hz = _validate_pwm_frequency(params.get("frequency_hz"))
    duty_cycle_percent = _validate_duty_cycle(params.get("duty_cycle_percent"))
    allowed_pins = _get_allowed_pins(config)
    sandbox_mode = _get_sandbox_mode(config)

    # Check whitelist
    _validate_pin_in_whitelist(pin, allowed_pins, "gpio.set_pwm")

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={
            "pin": pin,
            "frequency_hz": frequency_hz,
            "duty_cycle_percent": duty_cycle_percent,
        },
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "GPIO set_pwm requested",
        extra={
            "user": ctx.caller.user_id,
            "pin": pin,
            "frequency_hz": frequency_hz,
            "duty_cycle_percent": duty_cycle_percent,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking GPIO PWM")
        return {
            "pin": pin,
            "frequency_hz": frequency_hz,
            "duty_cycle_percent": duty_cycle_percent,
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging GPIO PWM (not executing)")
        return {
            "pin": pin,
            "frequency_hz": frequency_hz,
            "duty_cycle_percent": duty_cycle_percent,
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for GPIO PWM operation",
                details={"operation": "gpio.set_pwm", "pin": pin},
            )

        try:
            result = await ipc_client.call(
                "gpio.pwm",
                {
                    "pin": pin,
                    "frequency_hz": frequency_hz,
                    "duty_cycle_percent": duty_cycle_percent,
                    "caller": ctx.caller.to_dict(),
                },
            )
            return {
                "pin": pin,
                "frequency_hz": frequency_hz,
                "duty_cycle_percent": duty_cycle_percent,
                "timestamp": datetime.now(UTC).isoformat(),
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to set GPIO PWM via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={
                    "pin": pin,
                    "frequency_hz": frequency_hz,
                    "duty_cycle_percent": duty_cycle_percent,
                },
            )
            raise UnavailableError(
                f"Failed to set GPIO PWM: {e}",
                details={"operation": "gpio.set_pwm", "pin": pin},
            ) from e


# =============================================================================
# gpio.get_all_states
# =============================================================================


@require_role("operator")
async def handle_gpio_get_all_states(
    ctx: ToolContext,
    _params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the gpio.get_all_states tool call.

    Reads the state of all configured GPIO pins.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters (empty for this tool).
        config: Optional AppConfig for whitelist and sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - pins: List of pin states
        - timestamp: ISO 8601 timestamp

    Raises:
        PermissionDeniedError: If caller lacks operator role.
        UnavailableError: If privileged agent is unavailable.
    """
    allowed_pins = _get_allowed_pins(config)
    sandbox_mode = _get_sandbox_mode(config)

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"pins": allowed_pins},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "GPIO get_all_states requested",
        extra={
            "user": ctx.caller.user_id,
            "allowed_pins": allowed_pins,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking GPIO get_all_states")
        mock_pins = [
            {
                "pin": pin,
                "mode": "input",
                "value": "low",
                "allowed": True,
            }
            for pin in allowed_pins
        ]
        return {
            "pins": mock_pins,
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning(
            "Sandbox mode 'partial': Logging GPIO get_all_states (not executing)"
        )
        mock_pins = [
            {
                "pin": pin,
                "mode": "unknown",
                "value": "unknown",
                "allowed": True,
            }
            for pin in allowed_pins
        ]
        return {
            "pins": mock_pins,
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for GPIO get_all_states operation",
                details={"operation": "gpio.get_all_states"},
            )

        try:
            result = await ipc_client.call(
                "gpio.get_all_states",
                {"pins": allowed_pins, "caller": ctx.caller.to_dict()},
            )
            return {
                "pins": result.get("pins", []),
                "timestamp": datetime.now(UTC).isoformat(),
                **{k: v for k, v in result.items() if k != "pins"},
            }
        except Exception as e:
            logger.error(f"Failed to get GPIO states via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"pins": allowed_pins},
            )
            raise UnavailableError(
                f"Failed to get GPIO states: {e}",
                details={"operation": "gpio.get_all_states"},
            ) from e
