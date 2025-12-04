"""
Tests for service namespace tools.

This test module validates:
- service.list_services returns services filtered by whitelist
- service.get_status returns valid service status
- service.control_service requires operator role and whitelist
- service.set_enabled requires operator role and whitelist
- Whitelist enforcement works correctly
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_raspi.config import AppConfig, ServiceToolsConfig, TestingConfig, ToolsConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import (
    InvalidArgumentError,
    PermissionDeniedError,
    UnavailableError,
)
from mcp_raspi.tools.service import (
    _is_service_allowed,
    _validate_action,
    _validate_pagination,
    _validate_service_name,
    _validate_state_filter,
    handle_service_control_service,
    handle_service_get_status,
    handle_service_list_services,
    handle_service_set_enabled,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="service.list_services",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def operator_ctx() -> ToolContext:
    """Create a test context with operator role."""
    return ToolContext(
        tool_name="service.control_service",
        caller=CallerInfo(user_id="operator@example.com", role="operator"),
        request_id="test-req-operator",
    )


@pytest.fixture
def admin_ctx() -> ToolContext:
    """Create a test context with admin role."""
    return ToolContext(
        tool_name="service.control_service",
        caller=CallerInfo(user_id="admin@example.com", role="admin"),
        request_id="test-req-admin",
    )


@pytest.fixture
def full_sandbox_config() -> AppConfig:
    """Create config with full sandbox mode and service whitelist."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.tools = ToolsConfig(
        service=ServiceToolsConfig(
            enabled=True,
            allowed_services=["nginx", "docker", "mcp-raspi-*"],
        )
    )
    return config


@pytest.fixture
def partial_sandbox_config() -> AppConfig:
    """Create config with partial sandbox mode and service whitelist."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="partial")
    config.tools = ToolsConfig(
        service=ServiceToolsConfig(
            enabled=True,
            allowed_services=["nginx", "docker"],
        )
    )
    return config


@pytest.fixture
def disabled_sandbox_config() -> AppConfig:
    """Create config with disabled sandbox mode and service whitelist."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="disabled")
    config.tools = ToolsConfig(
        service=ServiceToolsConfig(
            enabled=True,
            allowed_services=["nginx", "docker"],
        )
    )
    return config


@pytest.fixture
def empty_whitelist_config() -> AppConfig:
    """Create config with empty service whitelist."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.tools = ToolsConfig(
        service=ServiceToolsConfig(
            enabled=True,
            allowed_services=[],
        )
    )
    return config


# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestWhitelistValidation:
    """Tests for service whitelist validation."""

    def test_exact_match(self) -> None:
        """Test exact service name match."""
        assert _is_service_allowed("nginx", ["nginx", "docker"])
        assert _is_service_allowed("nginx.service", ["nginx", "docker"])

    def test_wildcard_match(self) -> None:
        """Test wildcard pattern matching."""
        assert _is_service_allowed("mcp-raspi-server", ["mcp-raspi-*"])
        assert _is_service_allowed("mcp-raspi-ops", ["mcp-raspi-*"])
        assert not _is_service_allowed("nginx", ["mcp-raspi-*"])

    def test_empty_whitelist_denies_all(self) -> None:
        """Test empty whitelist denies all services."""
        assert not _is_service_allowed("nginx", [])
        assert not _is_service_allowed("docker", [])

    def test_service_suffix_normalization(self) -> None:
        """Test .service suffix normalization."""
        assert _is_service_allowed("nginx", ["nginx.service"])
        assert _is_service_allowed("nginx.service", ["nginx"])

    def test_case_sensitivity(self) -> None:
        """Test case-sensitive matching (systemd is case-sensitive)."""
        assert not _is_service_allowed("NGINX", ["nginx"])


class TestValidation:
    """Tests for parameter validation functions."""

    def test_validate_service_name_valid(self) -> None:
        """Test valid service names are accepted."""
        assert _validate_service_name("nginx") == "nginx"
        assert _validate_service_name("nginx.service") == "nginx.service"
        assert _validate_service_name("my-service") == "my-service"

    def test_validate_service_name_empty(self) -> None:
        """Test empty service name raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_service_name("")
        assert "required" in str(exc_info.value)

    def test_validate_service_name_none(self) -> None:
        """Test None service name raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_service_name(None)
        assert "required" in str(exc_info.value)

    def test_validate_service_name_path_traversal(self) -> None:
        """Test path traversal attempt is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_service_name("../etc/passwd")
        assert "Invalid" in str(exc_info.value)

    def test_validate_action_valid(self) -> None:
        """Test valid actions are accepted."""
        assert _validate_action("start") == "start"
        assert _validate_action("stop") == "stop"
        assert _validate_action("restart") == "restart"
        assert _validate_action("reload") == "reload"
        assert _validate_action("START") == "start"  # Case insensitive

    def test_validate_action_invalid(self) -> None:
        """Test invalid actions are rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_action("kill")
        assert "Invalid action" in str(exc_info.value)

    def test_validate_state_filter_valid(self) -> None:
        """Test valid state filters are accepted."""
        assert _validate_state_filter("active") == "active"
        assert _validate_state_filter("inactive") == "inactive"
        assert _validate_state_filter("failed") == "failed"
        assert _validate_state_filter(None) is None

    def test_validate_state_filter_invalid(self) -> None:
        """Test invalid state filters are rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_state_filter("running")
        assert "Invalid state" in str(exc_info.value)

    def test_validate_pagination_defaults(self) -> None:
        """Test pagination defaults are applied."""
        offset, limit = _validate_pagination(None, None)
        assert offset == 0
        assert limit == 100

    def test_validate_pagination_valid(self) -> None:
        """Test valid pagination values are accepted."""
        offset, limit = _validate_pagination(10, 50)
        assert offset == 10
        assert limit == 50

    def test_validate_pagination_negative_offset(self) -> None:
        """Test negative offset is rejected."""
        with pytest.raises(InvalidArgumentError):
            _validate_pagination(-1, 50)

    def test_validate_pagination_invalid_limit(self) -> None:
        """Test invalid limit values are rejected."""
        with pytest.raises(InvalidArgumentError):
            _validate_pagination(0, 0)

        with pytest.raises(InvalidArgumentError):
            _validate_pagination(0, 2000)


# =============================================================================
# Tests for service.list_services
# =============================================================================


class TestServiceListServices:
    """Tests for service.list_services tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_service_list_services(
            viewer_ctx, {}, config=full_sandbox_config
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test result contains required fields."""
        result = await handle_service_list_services(
            viewer_ctx, {}, config=full_sandbox_config
        )

        assert "services" in result
        assert "total_count" in result
        assert "returned_count" in result
        assert "has_more" in result
        assert isinstance(result["services"], list)

    @pytest.mark.asyncio
    async def test_respects_whitelist(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test services are filtered by whitelist."""
        result = await handle_service_list_services(
            viewer_ctx, {}, config=full_sandbox_config
        )

        # All returned services should match whitelist patterns
        for service in result["services"]:
            service_name = service["name"]
            assert _is_service_allowed(
                service_name, full_sandbox_config.tools.service.allowed_services
            ), f"Service {service_name} should be in whitelist"

    @pytest.mark.asyncio
    async def test_empty_whitelist_returns_empty(
        self, viewer_ctx: ToolContext, empty_whitelist_config: AppConfig
    ) -> None:
        """Test empty whitelist returns no services."""
        result = await handle_service_list_services(
            viewer_ctx, {}, config=empty_whitelist_config
        )

        assert result["services"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_pagination_works(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test pagination parameters are respected."""
        result = await handle_service_list_services(
            viewer_ctx, {"offset": 0, "limit": 1}, config=full_sandbox_config
        )

        assert result["returned_count"] <= 1

    @pytest.mark.asyncio
    async def test_state_filter_works(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test state filter is applied."""
        result = await handle_service_list_services(
            viewer_ctx, {"state": "active"}, config=full_sandbox_config
        )

        for service in result["services"]:
            assert service["status"] == "active"

    @pytest.mark.asyncio
    async def test_sandbox_mode_included(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test sandbox mode is included in response."""
        result = await handle_service_list_services(
            viewer_ctx, {}, config=full_sandbox_config
        )

        assert result["sandbox_mode"] == "full"


# =============================================================================
# Tests for service.get_status
# =============================================================================


class TestServiceGetStatus:
    """Tests for service.get_status tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_service_get_status(
            viewer_ctx, {"service_name": "nginx"}, config=full_sandbox_config
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test result contains required fields."""
        result = await handle_service_get_status(
            viewer_ctx, {"service_name": "nginx"}, config=full_sandbox_config
        )

        required_fields = [
            "name",
            "status",
            "enabled",
            "can_start",
            "can_stop",
            "can_reload",
        ]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_requires_service_name(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test service_name is required."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_service_get_status(viewer_ctx, {}, config=full_sandbox_config)
        assert "required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_whitelist_enforced(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test whitelist is enforced for get_status."""
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_service_get_status(
                viewer_ctx, {"service_name": "sshd"}, config=full_sandbox_config
            )
        assert "not in the allowed services" in str(exc_info.value)


# =============================================================================
# Tests for service.control_service
# =============================================================================


class TestServiceControlService:
    """Tests for service.control_service tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test viewer role is denied."""
        from mcp_raspi.security.rbac import PermissionDeniedError as RBACDenied

        with pytest.raises(RBACDenied):
            await handle_service_control_service(
                viewer_ctx,
                {"service_name": "nginx", "action": "restart"},
                config=full_sandbox_config,
            )

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test operator role is allowed."""
        result = await handle_service_control_service(
            operator_ctx,
            {"service_name": "nginx", "action": "restart"},
            config=full_sandbox_config,
        )
        assert "service_name" in result
        assert result["action"] == "restart"

    @pytest.mark.asyncio
    async def test_whitelist_enforced(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test whitelist prevents control of non-whitelisted services."""
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_service_control_service(
                operator_ctx,
                {"service_name": "sshd", "action": "restart"},
                config=full_sandbox_config,
            )
        assert "not in the allowed services" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_requires_service_name(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test service_name is required."""
        with pytest.raises(InvalidArgumentError):
            await handle_service_control_service(
                operator_ctx, {"action": "restart"}, config=full_sandbox_config
            )

    @pytest.mark.asyncio
    async def test_requires_action(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test action is required."""
        with pytest.raises(InvalidArgumentError):
            await handle_service_control_service(
                operator_ctx, {"service_name": "nginx"}, config=full_sandbox_config
            )

    @pytest.mark.asyncio
    async def test_validates_action(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test invalid actions are rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_service_control_service(
                operator_ctx,
                {"service_name": "nginx", "action": "kill"},
                config=full_sandbox_config,
            )
        assert "Invalid action" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode mocks the operation."""
        result = await handle_service_control_service(
            operator_ctx,
            {"service_name": "nginx", "action": "restart"},
            config=full_sandbox_config,
        )
        assert result["mocked"] is True
        assert result["sandbox_mode"] == "full"

    @pytest.mark.asyncio
    async def test_partial_sandbox_logs_only(
        self, operator_ctx: ToolContext, partial_sandbox_config: AppConfig
    ) -> None:
        """Test partial sandbox mode logs but doesn't execute."""
        result = await handle_service_control_service(
            operator_ctx,
            {"service_name": "nginx", "action": "restart"},
            config=partial_sandbox_config,
        )
        assert result["logged_only"] is True
        assert result["sandbox_mode"] == "partial"

    @pytest.mark.asyncio
    async def test_disabled_sandbox_requires_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode requires IPC client."""
        with pytest.raises(UnavailableError):
            await handle_service_control_service(
                operator_ctx,
                {"service_name": "nginx", "action": "restart"},
                config=disabled_sandbox_config,
                ipc_client=None,
            )

    @pytest.mark.asyncio
    async def test_disabled_sandbox_with_ipc_client(
        self, operator_ctx: ToolContext, disabled_sandbox_config: AppConfig
    ) -> None:
        """Test disabled sandbox mode calls IPC client."""
        mock_client = MagicMock()
        mock_client.call = AsyncMock(
            return_value={"status": "active", "previous_status": "inactive"}
        )

        result = await handle_service_control_service(
            operator_ctx,
            {"service_name": "nginx", "action": "start"},
            config=disabled_sandbox_config,
            ipc_client=mock_client,
        )

        assert "status" in result
        mock_client.call.assert_called_once()


# =============================================================================
# Tests for service.set_enabled
# =============================================================================


class TestServiceSetEnabled:
    """Tests for service.set_enabled tool."""

    @pytest.mark.asyncio
    async def test_requires_operator_role(
        self, viewer_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test viewer role is denied."""
        from mcp_raspi.security.rbac import PermissionDeniedError as RBACDenied

        with pytest.raises(RBACDenied):
            await handle_service_set_enabled(
                viewer_ctx,
                {"service_name": "nginx", "enabled": True},
                config=full_sandbox_config,
            )

    @pytest.mark.asyncio
    async def test_operator_allowed(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test operator role is allowed."""
        result = await handle_service_set_enabled(
            operator_ctx,
            {"service_name": "nginx", "enabled": True},
            config=full_sandbox_config,
        )
        assert result["service_name"] == "nginx"
        assert result["enabled"] is True

    @pytest.mark.asyncio
    async def test_whitelist_enforced(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test whitelist prevents enabling non-whitelisted services."""
        with pytest.raises(PermissionDeniedError) as exc_info:
            await handle_service_set_enabled(
                operator_ctx,
                {"service_name": "sshd", "enabled": True},
                config=full_sandbox_config,
            )
        assert "not in the allowed services" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_requires_enabled_parameter(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test enabled parameter is required."""
        with pytest.raises(InvalidArgumentError):
            await handle_service_set_enabled(
                operator_ctx, {"service_name": "nginx"}, config=full_sandbox_config
            )

    @pytest.mark.asyncio
    async def test_enabled_must_be_boolean(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test enabled must be a boolean."""
        with pytest.raises(InvalidArgumentError):
            await handle_service_set_enabled(
                operator_ctx,
                {"service_name": "nginx", "enabled": "yes"},
                config=full_sandbox_config,
            )

    @pytest.mark.asyncio
    async def test_full_sandbox_mocks(
        self, operator_ctx: ToolContext, full_sandbox_config: AppConfig
    ) -> None:
        """Test full sandbox mode mocks the operation."""
        result = await handle_service_set_enabled(
            operator_ctx,
            {"service_name": "nginx", "enabled": False},
            config=full_sandbox_config,
        )
        assert result["mocked"] is True
        assert result["sandbox_mode"] == "full"
        assert result["enabled"] is False
