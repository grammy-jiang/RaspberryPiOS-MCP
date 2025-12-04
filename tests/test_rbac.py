"""
Tests for the RBAC (Role-Based Access Control) module.

Tests cover:
- Role hierarchy and permission checks
- RBACEnforcer permission enforcement
- @require_role decorator
- Tool permission mapping
"""

from __future__ import annotations

import pytest

from mcp_raspi.config import RoleConfig, SecurityConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.security.rbac import (
    DEFAULT_TOOL_PERMISSIONS,
    ROLE_HIERARCHY,
    PermissionDeniedError,
    RBACEnforcer,
    has_role,
    require_role,
    require_safety_level,
    role_level,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rbac_enforcer() -> RBACEnforcer:
    """Create an RBACEnforcer for testing."""
    return RBACEnforcer()


@pytest.fixture
def admin_context() -> ToolContext:
    """Create a ToolContext with admin role."""
    return ToolContext(
        tool_name="system.reboot",
        caller=CallerInfo(user_id="admin@example.com", role="admin"),
        request_id="req-001",
    )


@pytest.fixture
def operator_context() -> ToolContext:
    """Create a ToolContext with operator role."""
    return ToolContext(
        tool_name="gpio.write_pin",
        caller=CallerInfo(user_id="operator@example.com", role="operator"),
        request_id="req-002",
    )


@pytest.fixture
def viewer_context() -> ToolContext:
    """Create a ToolContext with viewer role."""
    return ToolContext(
        tool_name="system.get_basic_info",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="req-003",
    )


# =============================================================================
# Tests for Role Hierarchy
# =============================================================================


class TestRoleHierarchy:
    """Tests for role hierarchy functions."""

    def test_role_hierarchy_order(self) -> None:
        """Test role hierarchy is viewer < operator < admin."""
        assert ROLE_HIERARCHY == ["viewer", "operator", "admin"]

    def test_role_level_viewer(self) -> None:
        """Test viewer role level."""
        assert role_level("viewer") == 0

    def test_role_level_operator(self) -> None:
        """Test operator role level."""
        assert role_level("operator") == 1

    def test_role_level_admin(self) -> None:
        """Test admin role level."""
        assert role_level("admin") == 2

    def test_role_level_unknown(self) -> None:
        """Test unknown role returns -1."""
        assert role_level("unknown") == -1

    def test_has_role_admin_can_access_all(self) -> None:
        """Test admin can access everything."""
        assert has_role("admin", "viewer") is True
        assert has_role("admin", "operator") is True
        assert has_role("admin", "admin") is True

    def test_has_role_operator_limited(self) -> None:
        """Test operator can access viewer and operator."""
        assert has_role("operator", "viewer") is True
        assert has_role("operator", "operator") is True
        assert has_role("operator", "admin") is False

    def test_has_role_viewer_limited(self) -> None:
        """Test viewer can only access viewer."""
        assert has_role("viewer", "viewer") is True
        assert has_role("viewer", "operator") is False
        assert has_role("viewer", "admin") is False


# =============================================================================
# Tests for RBACEnforcer
# =============================================================================


class TestRBACEnforcerInit:
    """Tests for RBACEnforcer initialization."""

    def test_default_permissions(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test default tool permissions are set."""
        assert rbac_enforcer._tool_permissions == DEFAULT_TOOL_PERMISSIONS

    def test_from_config(self) -> None:
        """Test RBACEnforcer creation from config."""
        config = SecurityConfig(
            roles={
                "viewer": RoleConfig(allowed_levels=["read_only"]),
                "admin": RoleConfig(allowed_levels=["read_only", "admin"]),
            }
        )

        enforcer = RBACEnforcer.from_config(config)

        assert "viewer" in enforcer._roles_config
        assert "admin" in enforcer._roles_config


class TestRBACEnforcerPermissions:
    """Tests for RBACEnforcer permission checking."""

    def test_get_required_role_exact_match(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test getting required role for known tool."""
        role = rbac_enforcer.get_required_role("system.reboot")
        assert role == "admin"

        role = rbac_enforcer.get_required_role("gpio.write_pin")
        assert role == "operator"

        role = rbac_enforcer.get_required_role("system.get_basic_info")
        assert role == "viewer"

    def test_get_required_role_unknown_tool(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test unknown tools default to admin."""
        role = rbac_enforcer.get_required_role("unknown.tool")
        assert role == "admin"

    def test_check_permission_allowed(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test permission check passes when allowed."""
        # Admin can access admin tools
        assert rbac_enforcer.check_permission("admin", "system.reboot") is True

        # Operator can access operator tools
        assert rbac_enforcer.check_permission("operator", "gpio.write_pin") is True

        # Viewer can access viewer tools
        assert rbac_enforcer.check_permission("viewer", "system.get_basic_info") is True

    def test_check_permission_denied_raises(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test permission check raises when denied."""
        with pytest.raises(PermissionDeniedError, match="Insufficient permissions"):
            rbac_enforcer.check_permission("viewer", "system.reboot")

    def test_check_permission_denied_no_raise(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test permission check returns False without raising."""
        result = rbac_enforcer.check_permission(
            "viewer", "system.reboot", raise_on_failure=False
        )
        assert result is False

    def test_check_permission_higher_role_allowed(
        self, rbac_enforcer: RBACEnforcer
    ) -> None:
        """Test higher roles can access lower-level tools."""
        # Admin can access operator tools
        assert rbac_enforcer.check_permission("admin", "gpio.write_pin") is True

        # Admin can access viewer tools
        assert rbac_enforcer.check_permission("admin", "system.get_basic_info") is True

        # Operator can access viewer tools
        assert rbac_enforcer.check_permission("operator", "system.get_basic_info") is True


class TestRBACEnforcerContext:
    """Tests for RBACEnforcer with ToolContext."""

    def test_check_permission_for_context_allowed(
        self, rbac_enforcer: RBACEnforcer, admin_context: ToolContext
    ) -> None:
        """Test permission check with context - allowed."""
        result = rbac_enforcer.check_permission_for_context(admin_context)
        assert result is True

    def test_check_permission_for_context_denied(
        self, rbac_enforcer: RBACEnforcer, viewer_context: ToolContext
    ) -> None:
        """Test permission check with context - denied."""
        # Change tool to admin-level
        viewer_context.tool_name = "system.reboot"

        with pytest.raises(PermissionDeniedError):
            rbac_enforcer.check_permission_for_context(viewer_context)


class TestRBACEnforcerToolManagement:
    """Tests for tool permission management."""

    def test_set_tool_permission(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test setting custom tool permission."""
        rbac_enforcer.set_tool_permission("custom.tool", "operator")

        assert rbac_enforcer.get_required_role("custom.tool") == "operator"

    def test_get_allowed_tools_admin(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test getting allowed tools for admin."""
        allowed = rbac_enforcer.get_allowed_tools("admin")

        # Admin should have access to all tools
        assert "system.reboot" in allowed
        assert "gpio.write_pin" in allowed
        assert "system.get_basic_info" in allowed

    def test_get_allowed_tools_viewer(self, rbac_enforcer: RBACEnforcer) -> None:
        """Test getting allowed tools for viewer."""
        allowed = rbac_enforcer.get_allowed_tools("viewer")

        # Viewer should only have viewer-level tools
        assert "system.get_basic_info" in allowed
        assert "system.reboot" not in allowed
        assert "gpio.write_pin" not in allowed


# =============================================================================
# Tests for @require_role Decorator
# =============================================================================


class TestRequireRoleDecorator:
    """Tests for the @require_role decorator."""

    @pytest.mark.asyncio
    async def test_require_role_allowed(self, admin_context: ToolContext) -> None:
        """Test decorator allows when role is sufficient."""

        @require_role("admin")
        async def protected_handler(
            _ctx: ToolContext, _params: dict
        ) -> dict[str, str]:
            return {"status": "ok"}

        result = await protected_handler(admin_context, {})
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_require_role_denied(self, viewer_context: ToolContext) -> None:
        """Test decorator raises when role is insufficient."""

        @require_role("admin")
        async def protected_handler(
            _ctx: ToolContext, _params: dict
        ) -> dict[str, str]:
            return {"status": "ok"}

        with pytest.raises(PermissionDeniedError, match="Insufficient permissions"):
            await protected_handler(viewer_context, {})

    @pytest.mark.asyncio
    async def test_require_role_higher_role_allowed(
        self, admin_context: ToolContext
    ) -> None:
        """Test decorator allows higher role to access lower-level handler."""

        @require_role("operator")
        async def operator_handler(
            _ctx: ToolContext, _params: dict
        ) -> dict[str, str]:
            return {"status": "ok"}

        result = await operator_handler(admin_context, {})
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_require_role_context_in_kwargs(
        self, admin_context: ToolContext
    ) -> None:
        """Test decorator finds context in kwargs."""

        @require_role("admin")
        async def handler(_params: dict, ctx: ToolContext | None = None) -> dict[str, str]:
            # ctx is used to pass context via kwargs
            del ctx  # unused in handler body
            return {"status": "ok"}

        result = await handler({}, ctx=admin_context)
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_require_role_missing_context(self) -> None:
        """Test decorator raises when context is missing."""

        @require_role("admin")
        async def handler(_params: dict) -> dict[str, str]:
            return {"status": "ok"}

        with pytest.raises(PermissionDeniedError, match="no context"):
            await handler({})

    @pytest.mark.asyncio
    async def test_require_role_preserves_function_metadata(self) -> None:
        """Test decorator preserves function name and docstring."""

        @require_role("viewer")
        async def my_handler(_ctx: ToolContext) -> None:
            """My docstring."""
            pass

        assert my_handler.__name__ == "my_handler"
        assert my_handler.__doc__ == "My docstring."


# =============================================================================
# Tests for @require_safety_level Decorator
# =============================================================================


class TestRequireSafetyLevelDecorator:
    """Tests for the @require_safety_level decorator."""

    @pytest.mark.asyncio
    async def test_read_only_requires_viewer(self, viewer_context: ToolContext) -> None:
        """Test read_only safety level requires viewer."""

        @require_safety_level("read_only")
        async def read_handler(_ctx: ToolContext) -> str:
            return "data"

        result = await read_handler(viewer_context)
        assert result == "data"

    @pytest.mark.asyncio
    async def test_safe_control_requires_operator(
        self, operator_context: ToolContext
    ) -> None:
        """Test safe_control safety level requires operator."""

        @require_safety_level("safe_control")
        async def control_handler(_ctx: ToolContext) -> str:
            return "controlled"

        result = await control_handler(operator_context)
        assert result == "controlled"

    @pytest.mark.asyncio
    async def test_admin_safety_level(self, admin_context: ToolContext) -> None:
        """Test admin safety level requires admin."""

        @require_safety_level("admin")
        async def admin_handler(_ctx: ToolContext) -> str:
            return "admin action"

        result = await admin_handler(admin_context)
        assert result == "admin action"

    @pytest.mark.asyncio
    async def test_safe_control_denied_for_viewer(
        self, viewer_context: ToolContext
    ) -> None:
        """Test viewer cannot access safe_control level."""

        @require_safety_level("safe_control")
        async def control_handler(_ctx: ToolContext) -> str:
            return "controlled"

        with pytest.raises(PermissionDeniedError):
            await control_handler(viewer_context)


# =============================================================================
# Tests for Default Tool Permissions
# =============================================================================


class TestDefaultToolPermissions:
    """Tests for default tool permission mapping."""

    def test_system_info_tools_are_viewer(self) -> None:
        """Test system info tools require viewer role."""
        assert DEFAULT_TOOL_PERMISSIONS["system.get_basic_info"] == "viewer"
        assert DEFAULT_TOOL_PERMISSIONS["system.get_health_snapshot"] == "viewer"
        assert DEFAULT_TOOL_PERMISSIONS["metrics.get_realtime_metrics"] == "viewer"

    def test_device_control_tools_are_operator(self) -> None:
        """Test device control tools require operator role."""
        assert DEFAULT_TOOL_PERMISSIONS["gpio.write_pin"] == "operator"
        assert DEFAULT_TOOL_PERMISSIONS["gpio.configure_pin"] == "operator"
        assert DEFAULT_TOOL_PERMISSIONS["i2c.write"] == "operator"

    def test_system_control_tools_are_admin(self) -> None:
        """Test system control tools require admin role."""
        assert DEFAULT_TOOL_PERMISSIONS["system.reboot"] == "admin"
        assert DEFAULT_TOOL_PERMISSIONS["system.shutdown"] == "admin"
        assert DEFAULT_TOOL_PERMISSIONS["manage.update_server"] == "admin"

    def test_audit_logs_require_admin(self) -> None:
        """Test audit log access requires admin."""
        assert DEFAULT_TOOL_PERMISSIONS["logs.get_recent_audit_logs"] == "admin"


# =============================================================================
# Tests for PermissionDeniedError
# =============================================================================


class TestPermissionDeniedError:
    """Tests for PermissionDeniedError."""

    def test_error_attributes(self) -> None:
        """Test error has correct attributes."""
        error = PermissionDeniedError(
            message="Access denied",
            details={"tool": "system.reboot", "required_role": "admin"},
        )

        assert error.error_code == "permission_denied"
        assert error.message == "Access denied"
        assert error.details["tool"] == "system.reboot"

    def test_error_str(self) -> None:
        """Test error string representation."""
        error = PermissionDeniedError(message="Access denied")
        assert str(error) == "Access denied"
