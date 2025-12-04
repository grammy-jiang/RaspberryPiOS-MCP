"""
System power operation handlers for the Privileged Agent.

This module implements handlers for system power operations:
- system.reboot: Execute system reboot
- system.shutdown: Execute system shutdown

These handlers run with elevated privileges and execute actual system commands.
They include safety checks and validation before executing operations.

Design follows Doc 08 §6 (Reboot & Shutdown Design).
"""

from __future__ import annotations

import asyncio
import subprocess
from datetime import UTC, datetime
from typing import Any

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

logger = get_logger(__name__)

# Minimum delay for safety (allows cancellation)
MIN_DELAY_SECONDS = 0
MAX_DELAY_SECONDS = 600

# Allowed commands for safety (no arbitrary shell commands)
REBOOT_COMMAND = ["systemctl", "reboot"]
SHUTDOWN_COMMAND = ["systemctl", "poweroff"]


def _validate_delay(delay_seconds: Any) -> int:
    """
    Validate and normalize delay parameter.

    Args:
        delay_seconds: Raw delay value from request.

    Returns:
        Validated delay in seconds.

    Raises:
        HandlerError: If delay is invalid.
    """
    if not isinstance(delay_seconds, int):
        try:
            delay_seconds = int(delay_seconds)
        except (ValueError, TypeError) as e:
            raise HandlerError(
                code="invalid_argument",
                message=f"Invalid delay_seconds: {delay_seconds}",
                details={"parameter": "delay_seconds"},
            ) from e

    if delay_seconds < MIN_DELAY_SECONDS or delay_seconds > MAX_DELAY_SECONDS:
        raise HandlerError(
            code="invalid_argument",
            message=f"delay_seconds must be between {MIN_DELAY_SECONDS} and {MAX_DELAY_SECONDS}",
            details={
                "parameter": "delay_seconds",
                "value": delay_seconds,
                "min": MIN_DELAY_SECONDS,
                "max": MAX_DELAY_SECONDS,
            },
        )

    return delay_seconds


async def _execute_power_command(
    command: list[str],
    delay_seconds: int,
    operation: str,
    reason: str,
) -> dict[str, Any]:
    """
    Execute a power command after the specified delay.

    Args:
        command: The command to execute.
        delay_seconds: Seconds to wait before execution.
        operation: Operation name for logging.
        reason: Reason for the operation.

    Returns:
        Result dict with execution details.

    Raises:
        HandlerError: If command execution fails.
    """
    logger.warning(
        f"Scheduling {operation}",
        extra={
            "delay_seconds": delay_seconds,
            "reason": reason,
            "command": " ".join(command),
        },
    )

    # If delay is specified, schedule for later
    if delay_seconds > 0:
        # Use systemd's scheduled shutdown mechanism if available
        # Otherwise, use asyncio.sleep + subprocess
        try:
            # For immediate scheduling with wall message support
            if operation == "system.reboot":
                schedule_cmd = ["shutdown", "-r", f"+{delay_seconds // 60 or 1}"]
            else:
                schedule_cmd = ["shutdown", "-h", f"+{delay_seconds // 60 or 1}"]

            if reason:
                schedule_cmd.append(reason[:80])

            result = subprocess.run(
                schedule_cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(
                    f"shutdown command failed, falling back to immediate {operation}",
                    extra={"stderr": result.stderr},
                )
                # Fall through to immediate execution after delay
            else:
                return {
                    "executed": True,
                    "method": "scheduled_shutdown",
                    "scheduled_at": datetime.now(UTC).isoformat(),
                }

        except FileNotFoundError:
            logger.info("shutdown command not found, using direct systemctl")
        except subprocess.TimeoutExpired:
            logger.warning("shutdown command timed out")

        # Fallback: wait and execute directly
        await asyncio.sleep(delay_seconds)

    # Execute the power command
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise HandlerError(
                code="internal",
                message=f"{operation} command failed: {result.stderr}",
                details={
                    "command": " ".join(command),
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                },
            )

        return {
            "executed": True,
            "method": "direct_systemctl",
            "executed_at": datetime.now(UTC).isoformat(),
        }

    except subprocess.TimeoutExpired as e:
        raise HandlerError(
            code="internal",
            message=f"{operation} command timed out",
            details={"command": " ".join(command)},
        ) from e
    except FileNotFoundError as e:
        raise HandlerError(
            code="unavailable",
            message="systemctl command not found",
            details={"command": " ".join(command)},
        ) from e


async def handle_system_reboot(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the system.reboot operation.

    Executes a system reboot with optional delay.

    Args:
        request: IPC request with params:
            - reason: Optional reason string
            - delay_seconds: Delay before reboot (default 5)
            - caller: Caller info dict for audit

    Returns:
        Dict with execution status.

    Raises:
        HandlerError: If reboot fails.
    """
    params = request.params
    reason = params.get("reason", "")
    delay_seconds = _validate_delay(params.get("delay_seconds", 5))
    caller = params.get("caller", {})

    logger.warning(
        "Executing system reboot",
        extra={
            "request_id": request.id,
            "reason": reason,
            "delay_seconds": delay_seconds,
            "caller_user_id": caller.get("user_id"),
            "caller_role": caller.get("role"),
        },
    )

    return await _execute_power_command(
        command=REBOOT_COMMAND,
        delay_seconds=delay_seconds,
        operation="system.reboot",
        reason=reason,
    )


async def handle_system_shutdown(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the system.shutdown operation.

    Executes a system shutdown (poweroff) with optional delay.
    This is a high-risk operation.

    Args:
        request: IPC request with params:
            - reason: Optional reason string
            - delay_seconds: Delay before shutdown (default 5)
            - caller: Caller info dict for audit

    Returns:
        Dict with execution status.

    Raises:
        HandlerError: If shutdown fails.
    """
    params = request.params
    reason = params.get("reason", "")
    delay_seconds = _validate_delay(params.get("delay_seconds", 5))
    caller = params.get("caller", {})

    logger.warning(
        "Executing system shutdown",
        extra={
            "request_id": request.id,
            "reason": reason,
            "delay_seconds": delay_seconds,
            "caller_user_id": caller.get("user_id"),
            "caller_role": caller.get("role"),
        },
    )

    return await _execute_power_command(
        command=SHUTDOWN_COMMAND,
        delay_seconds=delay_seconds,
        operation="system.shutdown",
        reason=reason,
    )


def register_system_handlers(registry: HandlerRegistry) -> None:
    """
    Register system power handlers with the handler registry.

    Args:
        registry: The handler registry to register with.
    """
    registry.register("system.reboot", handle_system_reboot)
    registry.register("system.shutdown", handle_system_shutdown)
    logger.debug("Registered system power handlers")
