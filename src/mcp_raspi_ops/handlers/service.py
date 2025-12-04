"""
Service operation handlers for the Privileged Agent.

This module implements handlers for systemd service operations:
- service.list_services: List systemd services
- service.get_status: Get detailed service status
- service.control_service: Start/stop/restart/reload services
- service.set_enabled: Enable/disable service autostart

These handlers run with elevated privileges and execute actual systemctl commands.

Design follows Doc 07 §4.2 (Service Management).
"""

from __future__ import annotations

import asyncio
import fnmatch
import re
import subprocess
from datetime import UTC, datetime
from typing import Any

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger
from mcp_raspi.service_utils import is_service_allowed
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

logger = get_logger(__name__)

# Allowed systemctl actions for safety
ALLOWED_ACTIONS = {"start", "stop", "restart", "reload"}

# Default timeout for systemctl commands
SYSTEMCTL_TIMEOUT = 30


def _run_systemctl(
    args: list[str],
    timeout: int = SYSTEMCTL_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """
    Run a systemctl command safely.

    Note: Callers must check the returncode field of the result.
    Non-zero return codes are not automatically raised as exceptions.

    Args:
        args: Arguments to pass to systemctl.
        timeout: Command timeout in seconds.

    Returns:
        CompletedProcess result.

    Raises:
        HandlerError: If command fails.
    """
    cmd = ["systemctl"] + args
    logger.debug("Running systemctl command", extra={"args": args})

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result

    except subprocess.TimeoutExpired as e:
        raise HandlerError(
            code="internal",
            message=f"systemctl command timed out after {timeout}s",
            details={"args": args},
        ) from e

    except FileNotFoundError as e:
        raise HandlerError(
            code="unavailable",
            message="systemctl command not found",
            details={"args": args},
        ) from e


# Regex patterns for parsing systemctl status output
# Pattern for Active line: "Active: <state> (<sub_state>) since..."
ACTIVE_LINE_PATTERN = re.compile(
    r"^Active:\s*(\w+)\s*\((\w+)\)",
    re.IGNORECASE,
)


def _parse_service_status_output(output: str) -> dict[str, Any]:
    """
    Parse systemctl status output into a structured dict.

    Args:
        output: Raw output from systemctl status.

    Returns:
        Dictionary with parsed service status.
    """
    result: dict[str, Any] = {}

    for line in output.splitlines():
        line = line.strip()

        if line.startswith("Loaded:"):
            # Parse loaded state
            if "loaded" in line.lower():
                result["loaded"] = True
                # Extract unit file path
                if "(" in line and ")" in line:
                    path_part = line.split("(")[1].split(")")[0]
                    parts = path_part.split(";")
                    if parts:
                        result["unit_file_path"] = parts[0].strip()
                    if len(parts) > 1:
                        result["unit_file_state"] = parts[1].strip()
            else:
                result["loaded"] = False

        elif line.startswith("Active:"):
            # Parse active state using regex for more robust matching
            match = ACTIVE_LINE_PATTERN.match(line)
            if match:
                state = match.group(1).lower()
                sub_state = match.group(2).lower()
                result["status"] = state
                result["sub_status"] = sub_state
            else:
                # Fallback for lines without the standard format (e.g., "failed")
                line_lower = line.lower()
                if "failed" in line_lower:
                    result["status"] = "failed"
                    result["sub_status"] = "failed"
                elif "activating" in line_lower:
                    result["status"] = "activating"
                    result["sub_status"] = "waiting"
                elif "deactivating" in line_lower:
                    result["status"] = "deactivating"
                    result["sub_status"] = "waiting"
                else:
                    result["status"] = "unknown"
                    result["sub_status"] = "unknown"

            # Note: Timestamp parsing is complex and not critical for status display
            # The "since" field contains various date formats that aren't easily parsed

        elif line.startswith("Main PID:"):
            # Parse main PID
            parts = line.split(":")
            if len(parts) > 1:
                pid_part = parts[1].strip().split()[0]
                try:
                    result["pid"] = int(pid_part)
                except ValueError:
                    result["pid"] = 0

        elif line.startswith("Memory:"):
            # Parse memory usage
            parts = line.split(":")
            if len(parts) > 1:
                mem_str = parts[1].strip()
                try:
                    # Parse memory string like "12.3M" or "1.2G"
                    if mem_str.endswith("K"):
                        result["memory_bytes"] = int(float(mem_str[:-1]) * 1024)
                    elif mem_str.endswith("M"):
                        result["memory_bytes"] = int(float(mem_str[:-1]) * 1024 * 1024)
                    elif mem_str.endswith("G"):
                        result["memory_bytes"] = int(float(mem_str[:-1]) * 1024 * 1024 * 1024)
                except (ValueError, IndexError):
                    # Ignore memory parsing errors; field is optional and may be missing or malformed.
                    pass

        elif line.startswith("CPU:"):
            # Parse CPU usage (cumulative time, not percentage)
            pass

    return result


def _get_all_enabled_states() -> dict[str, str]:
    """
    Get enabled states for all services using systemctl list-unit-files.

    This is more efficient than calling is-enabled for each service individually.

    Returns:
        Dictionary mapping service name to enabled state (enabled/disabled/static/masked).
    """
    result = _run_systemctl(["list-unit-files", "--type=service", "--no-pager", "--plain"])

    enabled_states: dict[str, str] = {}

    if result.returncode != 0:
        logger.warning(
            "systemctl list-unit-files returned non-zero",
            extra={"returncode": result.returncode, "stderr": result.stderr},
        )
        return enabled_states

    for line in result.stdout.strip().splitlines():
        if not line.strip() or "unit files listed" in line.lower():
            continue

        parts = line.split()
        if len(parts) >= 2:
            service_name = parts[0]
            state = parts[1]
            enabled_states[service_name] = state

    return enabled_states


async def handle_service_list_services(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the service.list_services operation.

    Lists systemd services, filtered by whitelist and optional state/pattern filters.

    Args:
        request: IPC request with params:
            - state: Optional state filter (active/inactive/failed)
            - pattern: Optional name pattern filter
            - allowed_services: Whitelist of allowed services

    Returns:
        Dict with list of services.

    Raises:
        HandlerError: If listing fails.
    """
    params = request.params
    state_filter = params.get("state")
    pattern = params.get("pattern")
    allowed_services = params.get("allowed_services", [])

    logger.info(
        "Listing services",
        extra={
            "request_id": request.id,
            "state_filter": state_filter,
            "pattern": pattern,
        },
    )

    # Build systemctl command
    args = ["list-units", "--type=service", "--all", "--no-pager", "--plain"]
    if state_filter:
        args.append(f"--state={state_filter}")

    result = _run_systemctl(args)

    if result.returncode != 0:
        logger.warning(
            "systemctl list-units returned non-zero",
            extra={"returncode": result.returncode, "stderr": result.stderr},
        )

    # Get all enabled states in one batch call (more efficient than per-service calls)
    enabled_states = _get_all_enabled_states()

    # Parse output
    services = []
    lines = result.stdout.strip().splitlines()

    for line in lines:
        # Skip header and empty lines
        if not line.strip() or line.startswith("UNIT") or "loaded units listed" in line:
            continue

        parts = line.split()
        if len(parts) < 4:
            continue

        service_name = parts[0]

        # Skip non-service units
        if not service_name.endswith(".service"):
            continue

        # Apply pattern filter
        if pattern and not fnmatch.fnmatch(service_name, pattern):
            continue

        # Apply whitelist filter
        if allowed_services and not is_service_allowed(service_name, allowed_services):
            continue

        # Parse service info
        load_state = parts[1] if len(parts) > 1 else "unknown"
        active_state = parts[2] if len(parts) > 2 else "unknown"
        sub_state = parts[3] if len(parts) > 3 else "unknown"
        description = " ".join(parts[4:]) if len(parts) > 4 else ""

        # Get enabled state from batch result
        enabled = enabled_states.get(service_name, "") == "enabled"

        services.append({
            "name": service_name,
            "display_name": description,
            "status": active_state,
            "sub_status": sub_state,
            "enabled": enabled,
            "load_state": load_state,
        })

    return {
        "services": services,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def handle_service_get_status(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the service.get_status operation.

    Gets detailed status of a single systemd service.

    Args:
        request: IPC request with params:
            - service_name: Name of the service

    Returns:
        Dict with detailed service status.

    Raises:
        HandlerError: If status query fails.
    """
    params = request.params
    service_name = params.get("service_name")

    if not service_name:
        raise HandlerError(
            code="invalid_argument",
            message="service_name is required",
            details={"parameter": "service_name"},
        )

    logger.info(
        "Getting service status",
        extra={"request_id": request.id, "service_name": service_name},
    )

    # Normalize service name
    if not service_name.endswith(".service"):
        service_name = f"{service_name}.service"

    # Get service status
    status_result = _run_systemctl(["status", service_name, "--no-pager"])

    # Parse status output (status command returns non-zero for inactive services)
    status_info = _parse_service_status_output(status_result.stdout)

    # Get enabled state
    enabled_result = _run_systemctl(["is-enabled", service_name])
    enabled = enabled_result.stdout.strip() == "enabled"

    # Get show output for more details
    show_result = _run_systemctl([
        "show", service_name,
        "--property=Description,ExecStart,WorkingDirectory,User,Group,Restart,Requires,Wants,After,Before"
    ])

    show_info: dict[str, Any] = {}
    for line in show_result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            show_info[key] = value

    return {
        "name": service_name,
        "display_name": show_info.get("Description", ""),
        "status": status_info.get("status", "unknown"),
        "sub_status": status_info.get("sub_status", "unknown"),
        "enabled": enabled,
        "pid": status_info.get("pid", 0),
        "memory_bytes": status_info.get("memory_bytes", 0),
        "unit_file_path": status_info.get("unit_file_path", ""),
        "unit_file_state": status_info.get("unit_file_state", ""),
        "exec_start": show_info.get("ExecStart", "").split() if show_info.get("ExecStart") else [],
        "working_directory": show_info.get("WorkingDirectory", ""),
        "user": show_info.get("User", ""),
        "group": show_info.get("Group", ""),
        "restart_policy": show_info.get("Restart", ""),
        "dependencies": {
            "requires": show_info.get("Requires", "").split() if show_info.get("Requires") else [],
            "wants": show_info.get("Wants", "").split() if show_info.get("Wants") else [],
            "after": show_info.get("After", "").split() if show_info.get("After") else [],
            "before": show_info.get("Before", "").split() if show_info.get("Before") else [],
        },
        "can_start": True,
        "can_stop": True,
        "can_reload": True,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def handle_service_control_service(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the service.control_service operation.

    Controls a systemd service (start/stop/restart/reload).

    Args:
        request: IPC request with params:
            - service_name: Name of the service
            - action: One of start, stop, restart, reload
            - reason: Optional reason for the action
            - caller: Caller info dict for audit

    Returns:
        Dict with operation result.

    Raises:
        HandlerError: If control operation fails.
    """
    params = request.params
    service_name = params.get("service_name")
    action = params.get("action")
    reason = params.get("reason", "")
    caller = params.get("caller", {})

    if not service_name:
        raise HandlerError(
            code="invalid_argument",
            message="service_name is required",
            details={"parameter": "service_name"},
        )

    if not action or action.lower() not in ALLOWED_ACTIONS:
        raise HandlerError(
            code="invalid_argument",
            message=f"Invalid action: {action}. Must be one of: {', '.join(ALLOWED_ACTIONS)}",
            details={"parameter": "action", "value": action},
        )

    action = action.lower()

    logger.warning(
        "Executing service control",
        extra={
            "request_id": request.id,
            "service_name": service_name,
            "action": action,
            "reason": reason,
            "caller_user_id": caller.get("user_id"),
            "caller_role": caller.get("role"),
        },
    )

    # Normalize service name
    if not service_name.endswith(".service"):
        service_name = f"{service_name}.service"

    # Get current status before action
    pre_status_result = _run_systemctl(["is-active", service_name])
    previous_status = pre_status_result.stdout.strip()

    # Execute the action
    result = _run_systemctl([action, service_name])

    if result.returncode != 0:
        raise HandlerError(
            code="internal",
            message=f"Failed to {action} service {service_name}: {result.stderr}",
            details={
                "service_name": service_name,
                "action": action,
                "returncode": result.returncode,
                "stderr": result.stderr,
            },
        )

    # Wait a moment for the service to change state
    await asyncio.sleep(0.5)

    # Get new status after action
    post_status_result = _run_systemctl(["is-active", service_name])
    new_status = post_status_result.stdout.strip()

    return {
        "status": new_status,
        "previous_status": previous_status,
        "executed": True,
    }


async def handle_service_set_enabled(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the service.set_enabled operation.

    Enables or disables a systemd service autostart.

    Args:
        request: IPC request with params:
            - service_name: Name of the service
            - enabled: Whether to enable (True) or disable (False)
            - caller: Caller info dict for audit

    Returns:
        Dict with operation result.

    Raises:
        HandlerError: If enable/disable operation fails.
    """
    params = request.params
    service_name = params.get("service_name")
    enabled = params.get("enabled")
    caller = params.get("caller", {})

    if not service_name:
        raise HandlerError(
            code="invalid_argument",
            message="service_name is required",
            details={"parameter": "service_name"},
        )

    if enabled is None:
        raise HandlerError(
            code="invalid_argument",
            message="enabled is required",
            details={"parameter": "enabled"},
        )

    logger.warning(
        "Setting service enabled state",
        extra={
            "request_id": request.id,
            "service_name": service_name,
            "enabled": enabled,
            "caller_user_id": caller.get("user_id"),
            "caller_role": caller.get("role"),
        },
    )

    # Normalize service name
    if not service_name.endswith(".service"):
        service_name = f"{service_name}.service"

    # Get current enabled state
    pre_enabled_result = _run_systemctl(["is-enabled", service_name])
    previous_enabled = pre_enabled_result.stdout.strip() == "enabled"

    # Execute enable/disable
    action = "enable" if enabled else "disable"
    result = _run_systemctl([action, service_name])

    if result.returncode != 0:
        raise HandlerError(
            code="internal",
            message=f"Failed to {action} service {service_name}: {result.stderr}",
            details={
                "service_name": service_name,
                "action": action,
                "returncode": result.returncode,
                "stderr": result.stderr,
            },
        )

    return {
        "previous_enabled": previous_enabled,
        "executed": True,
    }


def register_service_handlers(registry: HandlerRegistry) -> None:
    """
    Register service handlers with the handler registry.

    Args:
        registry: The handler registry to register with.
    """
    registry.register("service.list_services", handle_service_list_services)
    registry.register("service.get_status", handle_service_get_status)
    registry.register("service.control_service", handle_service_control_service)
    registry.register("service.set_enabled", handle_service_set_enabled)
    logger.debug("Registered service handlers")
