"""
Role-Based Access Control (RBAC) for the Raspberry Pi MCP Server.

This module implements authorization checks and the @require_role decorator
for enforcing role requirements on MCP tools.

Design follows Doc 04 §4 (Authorization).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from mcp_raspi.errors import ToolError

if TYPE_CHECKING:
    from mcp_raspi.config import SecurityConfig
    from mcp_raspi.context import ToolContext

logger = logging.getLogger("mcp_raspi.security.rbac")

# Type variable for async handler functions
T = TypeVar("T")


class PermissionDeniedError(ToolError):
    """Error raised when authorization fails."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a PermissionDeniedError."""
        super().__init__(
            error_code="permission_denied",
            message=message,
            details=details,
        )


# Role hierarchy: higher index = higher privilege
ROLE_HIERARCHY = ["viewer", "operator", "admin"]

# Default tool permissions by namespace
DEFAULT_TOOL_PERMISSIONS: dict[str, str] = {
    # Read-only tools - viewer level
    "system.get_basic_info": "viewer",
    "system.get_health_snapshot": "viewer",
    "system.get_capabilities": "viewer",
    "system.get_network_info": "viewer",
    "metrics.get_realtime_metrics": "viewer",
    "metrics.get_samples": "viewer",
    "logs.get_recent_app_logs": "viewer",
    "logs.get_recent_audit_logs": "admin",  # Audit logs require admin
    "service.list_services": "viewer",
    "service.get_status": "viewer",
    "process.list_processes": "viewer",
    "process.get_process_details": "viewer",
    "gpio.list_pins": "viewer",
    "i2c.list_buses": "viewer",
    "manage.get_server_status": "viewer",
    # Operator-level tools - device control
    "gpio.configure_pin": "operator",
    "gpio.read_pin": "operator",
    "gpio.write_pin": "operator",
    "gpio.set_pwm": "operator",
    "i2c.scan_bus": "operator",
    "i2c.read": "operator",
    "i2c.write": "operator",
    "camera.take_photo": "operator",
    "service.control_service": "operator",
    "service.set_enabled": "operator",
    "metrics.start_sampling_job": "operator",
    "metrics.stop_sampling_job": "operator",
    # Admin-level tools - system control
    "system.reboot": "admin",
    "system.shutdown": "admin",
    "manage.update_server": "admin",
    "manage.preview_os_updates": "admin",
    "manage.apply_os_updates": "admin",
    "process.send_signal": "admin",
}


def role_level(role: str) -> int:
    """
    Get the privilege level for a role.

    Args:
        role: Role name.

    Returns:
        Privilege level (higher = more privilege).
    """
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1  # Unknown role has lowest privilege


def has_role(user_role: str, required_role: str) -> bool:
    """
    Check if user role meets the required role level.

    Args:
        user_role: The user's assigned role.
        required_role: The required role for the operation.

    Returns:
        True if user has sufficient privileges.
    """
    return role_level(user_role) >= role_level(required_role)


class RBACEnforcer:
    """
    Enforces Role-Based Access Control for MCP tools.

    Checks if a user with a given role is allowed to execute a specific tool.

    Example:
        >>> enforcer = RBACEnforcer.from_config(config)
        >>> enforcer.check_permission("operator", "gpio.write_pin")  # OK
        >>> enforcer.check_permission("viewer", "system.reboot")  # Raises
    """

    def __init__(
        self,
        tool_permissions: dict[str, str] | None = None,
        roles_config: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the RBAC enforcer.

        Args:
            tool_permissions: Mapping from tool names to required roles.
            roles_config: Role definitions from configuration.
        """
        self._tool_permissions = tool_permissions or DEFAULT_TOOL_PERMISSIONS.copy()
        self._roles_config = roles_config or {}

    @classmethod
    def from_config(cls, config: SecurityConfig) -> RBACEnforcer:
        """
        Create an RBACEnforcer from configuration.

        Args:
            config: SecurityConfig with role and permission settings.

        Returns:
            Configured RBACEnforcer instance.
        """
        roles_config = {
            name: role_cfg.model_dump() for name, role_cfg in config.roles.items()
        }
        return cls(
            tool_permissions=DEFAULT_TOOL_PERMISSIONS.copy(),
            roles_config=roles_config,
        )

    def get_required_role(self, tool_name: str) -> str:
        """
        Get the required role for a tool.

        Args:
            tool_name: Full tool name (e.g., "system.reboot").

        Returns:
            Required role name, defaulting to "admin" for unknown tools.
        """
        # Check for exact match
        if tool_name in self._tool_permissions:
            return self._tool_permissions[tool_name]

        # Check namespace-level permission
        namespace = tool_name.split(".")[0] if "." in tool_name else tool_name
        namespace_key = f"{namespace}.*"
        if namespace_key in self._tool_permissions:
            return self._tool_permissions[namespace_key]

        # Default to admin for unknown tools (secure by default)
        logger.warning(
            "No permission defined for tool %s, defaulting to admin",
            tool_name,
        )
        return "admin"

    def check_permission(
        self,
        user_role: str,
        tool_name: str,
        raise_on_failure: bool = True,
    ) -> bool:
        """
        Check if a user role is allowed to execute a tool.

        Args:
            user_role: The user's assigned role.
            tool_name: The tool to execute.
            raise_on_failure: If True, raises PermissionDeniedError on failure.

        Returns:
            True if allowed.

        Raises:
            PermissionDeniedError: If not allowed and raise_on_failure is True.
        """
        required_role = self.get_required_role(tool_name)
        allowed = has_role(user_role, required_role)

        if not allowed and raise_on_failure:
            logger.warning(
                "Permission denied: role=%s, tool=%s, required=%s",
                user_role,
                tool_name,
                required_role,
            )
            raise PermissionDeniedError(
                message=f"Insufficient permissions to execute '{tool_name}'",
                details={
                    "tool": tool_name,
                    "required_role": required_role,
                    "user_role": user_role,
                },
            )

        return allowed

    def check_permission_for_context(
        self,
        ctx: ToolContext,
        raise_on_failure: bool = True,
    ) -> bool:
        """
        Check permission using a ToolContext.

        Args:
            ctx: Tool context with caller information.
            raise_on_failure: If True, raises on failure.

        Returns:
            True if allowed.

        Raises:
            PermissionDeniedError: If not allowed and raise_on_failure is True.
        """
        return self.check_permission(
            user_role=ctx.caller.role,
            tool_name=ctx.tool_name,
            raise_on_failure=raise_on_failure,
        )

    def set_tool_permission(self, tool_name: str, required_role: str) -> None:
        """
        Set the required role for a tool.

        Args:
            tool_name: Tool name.
            required_role: Required role name.
        """
        self._tool_permissions[tool_name] = required_role

    def get_allowed_tools(self, user_role: str) -> list[str]:
        """
        Get list of tools allowed for a given role.

        Args:
            user_role: The user's role.

        Returns:
            List of allowed tool names.
        """
        return [
            tool
            for tool, required in self._tool_permissions.items()
            if has_role(user_role, required)
        ]


def require_role(
    required_role: str,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to enforce role requirement on tool handlers.

    This decorator checks that the caller has sufficient role privileges
    before executing the handler. The handler must accept a ToolContext
    as its first argument.

    Args:
        required_role: Minimum role required to execute the tool.

    Returns:
        Decorated function that enforces the role requirement.

    Example:
        >>> @require_role("admin")
        ... async def handle_reboot(ctx: ToolContext, params: dict) -> dict:
        ...     # Only admins can reach here
        ...     ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Find ToolContext in arguments
            ctx: ToolContext | None = None
            for arg in args:
                if hasattr(arg, "caller") and hasattr(arg, "tool_name"):
                    ctx = arg
                    break

            if ctx is None:
                ctx = kwargs.get("ctx")

            if ctx is None:
                logger.error(
                    "require_role decorator: No ToolContext found in arguments"
                )
                raise PermissionDeniedError(
                    message="Authorization check failed: no context",
                    details={"reason": "missing_context"},
                )

            # Check permission
            user_role = ctx.caller.role
            if not has_role(user_role, required_role):
                logger.warning(
                    "Permission denied by @require_role: role=%s, required=%s, tool=%s",
                    user_role,
                    required_role,
                    ctx.tool_name,
                )
                raise PermissionDeniedError(
                    message=f"Insufficient permissions to execute '{ctx.tool_name}'",
                    details={
                        "tool": ctx.tool_name,
                        "required_role": required_role,
                        "user_role": user_role,
                    },
                )

            return await func(*args, **kwargs)

        return cast(Callable[..., T], wrapper)

    return decorator


def require_safety_level(
    safety_level: str,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to enforce safety level requirement on tool handlers.

    Safety levels are: read_only, safe_control, admin
    This maps to roles via the configuration.

    Args:
        safety_level: Required safety level.

    Returns:
        Decorated function.
    """
    # Map safety levels to minimum roles
    safety_to_role = {
        "read_only": "viewer",
        "safe_control": "operator",
        "admin": "admin",
    }
    required_role = safety_to_role.get(safety_level, "admin")
    return require_role(required_role)
