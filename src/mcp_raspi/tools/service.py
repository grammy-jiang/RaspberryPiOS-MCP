"""
Service namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `service.*` namespace:
- service.list_services: List systemd services filtered by whitelist
- service.get_status: Get detailed status of a single service
- service.control_service: Start/stop/restart services with whitelist enforcement
- service.set_enabled: Enable/disable service autostart

Design follows Doc 05 §5-6 (service namespace specification) and Doc 07.
"""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import (
    InvalidArgumentError,
    PermissionDeniedError,
    UnavailableError,
)
from mcp_raspi.logging import get_logger
from mcp_raspi.security.audit_logger import get_audit_logger
from mcp_raspi.security.rbac import require_role
from mcp_raspi.service_utils import is_service_allowed

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)

# Valid service control actions
VALID_ACTIONS = {"start", "stop", "restart", "reload"}

# Valid service states for filtering
VALID_STATES = {"active", "inactive", "failed", "activating", "deactivating"}


def _validate_service_name(service_name: str | None) -> str:
    """
    Validate and normalize service name.

    Args:
        service_name: The service name to validate.

    Returns:
        Validated service name.

    Raises:
        InvalidArgumentError: If service name is invalid.
    """
    if not service_name:
        raise InvalidArgumentError(
            "service_name is required",
            details={"parameter": "service_name"},
        )

    if not isinstance(service_name, str):
        raise InvalidArgumentError(
            "service_name must be a string",
            details={"parameter": "service_name", "type": type(service_name).__name__},
        )

    # Basic validation - no path traversal or injection
    if "/" in service_name or ".." in service_name:
        raise InvalidArgumentError(
            "Invalid service name",
            details={"parameter": "service_name", "value": service_name},
        )

    return service_name


def _validate_action(action: str | None) -> str:
    """
    Validate service control action.

    Args:
        action: The action to validate.

    Returns:
        Validated action string.

    Raises:
        InvalidArgumentError: If action is invalid.
    """
    if not action:
        raise InvalidArgumentError(
            "action is required",
            details={"parameter": "action"},
        )

    action_lower = action.lower()
    if action_lower not in VALID_ACTIONS:
        raise InvalidArgumentError(
            f"Invalid action: {action}. Must be one of: {', '.join(sorted(VALID_ACTIONS))}",
            details={"parameter": "action", "value": action, "valid": list(VALID_ACTIONS)},
        )

    return action_lower


def _validate_state_filter(state: str | None) -> str | None:
    """
    Validate service state filter.

    Args:
        state: The state filter to validate.

    Returns:
        Validated state string or None.

    Raises:
        InvalidArgumentError: If state is invalid.
    """
    if state is None:
        return None

    state_lower = state.lower()
    if state_lower not in VALID_STATES:
        raise InvalidArgumentError(
            f"Invalid state: {state}. Must be one of: {', '.join(sorted(VALID_STATES))}",
            details={"parameter": "state", "value": state, "valid": list(VALID_STATES)},
        )

    return state_lower


def _validate_pagination(
    offset: int | None,
    limit: int | None,
) -> tuple[int, int]:
    """
    Validate pagination parameters.

    Args:
        offset: Number of items to skip.
        limit: Maximum number of items to return.

    Returns:
        Tuple of (offset, limit) with defaults applied.

    Raises:
        InvalidArgumentError: If parameters are invalid.
    """
    if offset is None:
        offset = 0
    elif not isinstance(offset, int) or offset < 0:
        raise InvalidArgumentError(
            "offset must be a non-negative integer",
            details={"parameter": "offset", "value": offset},
        )

    if limit is None:
        limit = 100  # Default limit
    elif not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise InvalidArgumentError(
            "limit must be an integer between 1 and 1000",
            details={"parameter": "limit", "value": limit},
        )

    return offset, limit


# =============================================================================
# service.list_services
# =============================================================================


async def handle_service_list_services(
    _ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the service.list_services tool call.

    Lists systemd services, filtered by the configured whitelist.

    Args:
        _ctx: The ToolContext for this request.
        params: Request parameters:
            - state: Optional filter by service state (active/inactive/failed)
            - pattern: Optional name pattern filter
            - offset: Pagination offset (default 0)
            - limit: Pagination limit (default 100, max 1000)
        config: AppConfig for whitelist configuration.
        ipc_client: IPC client for agent communication.

    Returns:
        Dictionary with:
        - services: List of ServiceSummary objects
        - total_count: Total number of services matching filter
        - returned_count: Number of services returned
        - has_more: Whether more results are available
    """
    state_filter = _validate_state_filter(params.get("state"))
    pattern = params.get("pattern")
    offset, limit = _validate_pagination(params.get("offset"), params.get("limit"))

    # Get allowed services from config
    allowed_services: list[str] = []
    sandbox_mode = "partial"
    if config is not None:
        allowed_services = config.tools.service.allowed_services
        sandbox_mode = config.testing.sandbox_mode

    logger.debug(
        "Listing services",
        extra={
            "state_filter": state_filter,
            "pattern": pattern,
            "offset": offset,
            "limit": limit,
            "allowed_services": allowed_services,
        },
    )

    # In sandbox mode, return mock data
    if sandbox_mode == "full":
        mock_services = _get_mock_services(allowed_services, state_filter, pattern)
        total = len(mock_services)
        paginated = mock_services[offset : offset + limit]
        return {
            "services": paginated,
            "total_count": total,
            "returned_count": len(paginated),
            "has_more": (offset + limit) < total,
            "sandbox_mode": sandbox_mode,
        }

    # In partial sandbox or with no IPC client, return empty or mock
    if sandbox_mode == "partial" or ipc_client is None:
        if ipc_client is None and sandbox_mode != "partial":
            raise UnavailableError(
                "Privileged agent not available for service operations",
                details={"operation": "service.list_services"},
            )
        # Partial sandbox: return mock data
        mock_services = _get_mock_services(allowed_services, state_filter, pattern)
        total = len(mock_services)
        paginated = mock_services[offset : offset + limit]
        return {
            "services": paginated,
            "total_count": total,
            "returned_count": len(paginated),
            "has_more": (offset + limit) < total,
            "sandbox_mode": sandbox_mode,
        }

    # Real mode: call agent
    try:
        result = await ipc_client.call(
            "service.list_services",
            {
                "state": state_filter,
                "pattern": pattern,
                "allowed_services": allowed_services,
            },
        )

        # Apply pagination on server side
        services = result.get("services", [])
        total = len(services)
        paginated = services[offset : offset + limit]

        return {
            "services": paginated,
            "total_count": total,
            "returned_count": len(paginated),
            "has_more": (offset + limit) < total,
        }

    except Exception as e:
        logger.error(f"Failed to list services via agent: {e}")
        raise UnavailableError(
            f"Failed to list services: {e}",
            details={"operation": "service.list_services"},
        ) from e


def _get_mock_services(
    allowed_services: list[str],
    state_filter: str | None,
    pattern: str | None,
) -> list[dict[str, Any]]:
    """Generate mock service data for sandbox mode."""
    mock_data = [
        {
            "name": "nginx.service",
            "display_name": "A high performance web server",
            "status": "active",
            "sub_status": "running",
            "enabled": True,
            "pid": 1234,
            "memory_bytes": 10485760,
            "uptime_seconds": 86400,
        },
        {
            "name": "docker.service",
            "display_name": "Docker Application Container Engine",
            "status": "active",
            "sub_status": "running",
            "enabled": True,
            "pid": 2345,
            "memory_bytes": 52428800,
            "uptime_seconds": 43200,
        },
        {
            "name": "mcp-raspi-server.service",
            "display_name": "Raspberry Pi MCP Server",
            "status": "active",
            "sub_status": "running",
            "enabled": True,
            "pid": 3456,
            "memory_bytes": 31457280,
            "uptime_seconds": 3600,
        },
    ]

    # Filter by whitelist - always apply (empty whitelist = nothing allowed)
    mock_data = [
        s for s in mock_data if is_service_allowed(s["name"], allowed_services)
    ]

    # Filter by state
    if state_filter:
        mock_data = [s for s in mock_data if s["status"] == state_filter]

    # Filter by pattern
    if pattern:
        mock_data = [s for s in mock_data if fnmatch.fnmatch(s["name"], pattern)]

    return mock_data


# =============================================================================
# service.get_status
# =============================================================================


async def handle_service_get_status(
    _ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the service.get_status tool call.

    Gets detailed status of a single systemd service.

    Args:
        _ctx: The ToolContext for this request.
        params: Request parameters:
            - service_name: Name of the service (required)
        config: AppConfig for whitelist configuration.
        ipc_client: IPC client for agent communication.

    Returns:
        Dictionary with detailed service status (ServiceDetail schema).

    Raises:
        InvalidArgumentError: If service_name is invalid.
        PermissionDeniedError: If service is not in whitelist.
    """
    service_name = _validate_service_name(params.get("service_name"))

    # Get allowed services from config
    allowed_services: list[str] = []
    sandbox_mode = "partial"
    if config is not None:
        allowed_services = config.tools.service.allowed_services
        sandbox_mode = config.testing.sandbox_mode

    # Check whitelist (viewers can still get status of whitelisted services)
    if allowed_services and not is_service_allowed(service_name, allowed_services):
        raise PermissionDeniedError(
            f"Service '{service_name}' is not in the allowed services list",
            details={"service_name": service_name, "allowed_services": allowed_services},
        )

    logger.debug(
        "Getting service status",
        extra={"service_name": service_name, "sandbox_mode": sandbox_mode},
    )

    # In sandbox mode, return mock data
    if sandbox_mode == "full":
        return _get_mock_service_status(service_name)

    if sandbox_mode == "partial" or ipc_client is None:
        if ipc_client is None and sandbox_mode != "partial":
            raise UnavailableError(
                "Privileged agent not available for service operations",
                details={"operation": "service.get_status"},
            )
        return _get_mock_service_status(service_name)

    # Real mode: call agent
    try:
        result = await ipc_client.call(
            "service.get_status",
            {"service_name": service_name},
        )
        return result

    except Exception as e:
        logger.error(f"Failed to get service status via agent: {e}")
        raise UnavailableError(
            f"Failed to get service status: {e}",
            details={"operation": "service.get_status", "service_name": service_name},
        ) from e


def _get_mock_service_status(service_name: str) -> dict[str, Any]:
    """Generate mock service status for sandbox mode."""
    return {
        "name": service_name,
        "display_name": f"Mock service: {service_name}",
        "status": "active",
        "sub_status": "running",
        "enabled": True,
        "pid": 12345,
        "memory_bytes": 20971520,
        "cpu_percent": 0.5,
        "uptime_seconds": 7200,
        "restart_count": 0,
        "unit_file_state": "enabled",
        "description": f"Mock description for {service_name}",
        "can_start": True,
        "can_stop": True,
        "can_reload": True,
        "unit_file_path": f"/etc/systemd/system/{service_name}",
        "exec_start": ["/usr/bin/mock-service"],
        "dependencies": {
            "requires": [],
            "wants": ["network.target"],
            "after": ["network.target"],
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# service.control_service
# =============================================================================


@require_role("operator")
async def handle_service_control_service(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the service.control_service tool call.

    Controls a systemd service (start/stop/restart/reload).
    Requires operator role. Service must be in whitelist.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - service_name: Name of the service (required)
            - action: One of start, stop, restart, reload (required)
            - reason: Optional reason for the action
        config: AppConfig for whitelist configuration.
        ipc_client: IPC client for agent communication.

    Returns:
        Dictionary with:
        - service_name: Name of the service
        - action: Action performed
        - status: New service status
        - previous_status: Status before action
        - timestamp: When action was performed

    Raises:
        InvalidArgumentError: If parameters are invalid.
        PermissionDeniedError: If service not in whitelist or insufficient role.
    """
    service_name = _validate_service_name(params.get("service_name"))
    action = _validate_action(params.get("action"))
    reason = params.get("reason", "")

    # Get config
    allowed_services: list[str] = []
    sandbox_mode = "partial"
    if config is not None:
        allowed_services = config.tools.service.allowed_services
        sandbox_mode = config.testing.sandbox_mode

    # Enforce whitelist for control operations
    if not is_service_allowed(service_name, allowed_services):
        logger.warning(
            "Service control denied - not in whitelist",
            extra={
                "service_name": service_name,
                "action": action,
                "user": ctx.caller.user_id,
            },
        )
        raise PermissionDeniedError(
            f"Service '{service_name}' is not in the allowed services list",
            details={
                "service_name": service_name,
                "action": action,
                "allowed_services": allowed_services,
            },
        )

    audit = get_audit_logger()

    # Log the service control request
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"service_name": service_name, "action": action, "reason": reason},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "Service control requested",
        extra={
            "service_name": service_name,
            "action": action,
            "user": ctx.caller.user_id,
            "reason": reason,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking service control")
        return {
            "service_name": service_name,
            "action": action,
            "status": "active" if action in ("start", "restart") else "inactive",
            "previous_status": "inactive" if action == "start" else "active",
            "timestamp": datetime.now(UTC).isoformat(),
            "sandbox_mode": sandbox_mode,
            "mocked": True,
        }

    if sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging service control (not executing)")
        return {
            "service_name": service_name,
            "action": action,
            "status": "unknown",
            "previous_status": "unknown",
            "timestamp": datetime.now(UTC).isoformat(),
            "sandbox_mode": sandbox_mode,
            "logged_only": True,
        }

    # Disabled sandbox: execute via agent
    if ipc_client is None:
        raise UnavailableError(
            "Privileged agent not available for service control",
            details={"operation": "service.control_service"},
        )

    try:
        result = await ipc_client.call(
            "service.control_service",
            {
                "service_name": service_name,
                "action": action,
                "reason": reason,
                "caller": ctx.caller.to_dict(),
            },
        )

        audit.log_tool_call(
            ctx=ctx,
            status="success",
            params={"service_name": service_name, "action": action},
        )

        return {
            "service_name": service_name,
            "action": action,
            "timestamp": datetime.now(UTC).isoformat(),
            **result,
        }

    except Exception as e:
        logger.error(f"Failed to control service via agent: {e}")
        audit.log_tool_call(
            ctx=ctx,
            status="error",
            error_code="unavailable",
            params={"service_name": service_name, "action": action},
        )
        raise UnavailableError(
            f"Failed to control service: {e}",
            details={"operation": "service.control_service", "service_name": service_name},
        ) from e


# =============================================================================
# service.set_enabled
# =============================================================================


@require_role("operator")
async def handle_service_set_enabled(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the service.set_enabled tool call.

    Enables or disables a systemd service autostart.
    Requires operator role. Service must be in whitelist.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - service_name: Name of the service (required)
            - enabled: Whether to enable (True) or disable (False) (required)
        config: AppConfig for whitelist configuration.
        ipc_client: IPC client for agent communication.

    Returns:
        Dictionary with:
        - service_name: Name of the service
        - enabled: New enabled state
        - previous_enabled: Previous enabled state
        - timestamp: When action was performed

    Raises:
        InvalidArgumentError: If parameters are invalid.
        PermissionDeniedError: If service not in whitelist or insufficient role.
    """
    service_name = _validate_service_name(params.get("service_name"))
    enabled = params.get("enabled")

    if enabled is None:
        raise InvalidArgumentError(
            "enabled is required",
            details={"parameter": "enabled"},
        )

    if not isinstance(enabled, bool):
        raise InvalidArgumentError(
            "enabled must be a boolean",
            details={"parameter": "enabled", "type": type(enabled).__name__},
        )

    # Get config
    allowed_services: list[str] = []
    sandbox_mode = "partial"
    if config is not None:
        allowed_services = config.tools.service.allowed_services
        sandbox_mode = config.testing.sandbox_mode

    # Enforce whitelist
    if not is_service_allowed(service_name, allowed_services):
        logger.warning(
            "Service set_enabled denied - not in whitelist",
            extra={
                "service_name": service_name,
                "enabled": enabled,
                "user": ctx.caller.user_id,
            },
        )
        raise PermissionDeniedError(
            f"Service '{service_name}' is not in the allowed services list",
            details={"service_name": service_name, "allowed_services": allowed_services},
        )

    audit = get_audit_logger()

    # Log the request
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"service_name": service_name, "enabled": enabled},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "Service set_enabled requested",
        extra={
            "service_name": service_name,
            "enabled": enabled,
            "user": ctx.caller.user_id,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking service set_enabled")
        return {
            "service_name": service_name,
            "enabled": enabled,
            "previous_enabled": not enabled,
            "timestamp": datetime.now(UTC).isoformat(),
            "sandbox_mode": sandbox_mode,
            "mocked": True,
        }

    if sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging service set_enabled (not executing)")
        return {
            "service_name": service_name,
            "enabled": enabled,
            "previous_enabled": None,
            "timestamp": datetime.now(UTC).isoformat(),
            "sandbox_mode": sandbox_mode,
            "logged_only": True,
        }

    # Disabled sandbox: execute via agent
    if ipc_client is None:
        raise UnavailableError(
            "Privileged agent not available for service operations",
            details={"operation": "service.set_enabled"},
        )

    try:
        result = await ipc_client.call(
            "service.set_enabled",
            {
                "service_name": service_name,
                "enabled": enabled,
                "caller": ctx.caller.to_dict(),
            },
        )

        audit.log_tool_call(
            ctx=ctx,
            status="success",
            params={"service_name": service_name, "enabled": enabled},
        )

        return {
            "service_name": service_name,
            "enabled": enabled,
            "timestamp": datetime.now(UTC).isoformat(),
            **result,
        }

    except Exception as e:
        logger.error(f"Failed to set service enabled via agent: {e}")
        audit.log_tool_call(
            ctx=ctx,
            status="error",
            error_code="unavailable",
            params={"service_name": service_name, "enabled": enabled},
        )
        raise UnavailableError(
            f"Failed to set service enabled: {e}",
            details={"operation": "service.set_enabled", "service_name": service_name},
        ) from e
