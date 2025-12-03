"""
Tests for the ToolContext module.

This test module validates:
- ToolContext dataclass functionality
- CallerInfo handling
- Context creation and extraction
"""

from __future__ import annotations

from datetime import UTC, datetime

from mcp_raspi.context import CallerInfo, ToolContext

# =============================================================================
# Tests for CallerInfo
# =============================================================================


class TestCallerInfo:
    """Tests for CallerInfo class."""

    def test_caller_info_creation(self) -> None:
        """Test creating a CallerInfo instance."""
        caller = CallerInfo(
            user_id="alice@example.com",
            role="admin",
            ip_address="192.168.1.100",
        )

        assert caller.user_id == "alice@example.com"
        assert caller.role == "admin"
        assert caller.ip_address == "192.168.1.100"

    def test_caller_info_minimal(self) -> None:
        """Test CallerInfo with minimal info (anonymous)."""
        caller = CallerInfo()

        assert caller.user_id is None
        assert caller.role == "anonymous"
        assert caller.ip_address is None

    def test_caller_info_with_groups(self) -> None:
        """Test CallerInfo with groups."""
        caller = CallerInfo(
            user_id="bob@example.com",
            role="operator",
            groups=["iot-ops", "developers"],
        )

        assert caller.groups == ["iot-ops", "developers"]

    def test_caller_info_is_authenticated(self) -> None:
        """Test is_authenticated property."""
        anonymous = CallerInfo()
        authenticated = CallerInfo(user_id="user@example.com", role="viewer")

        assert anonymous.is_authenticated is False
        assert authenticated.is_authenticated is True

    def test_caller_info_to_dict(self) -> None:
        """Test CallerInfo to_dict method."""
        caller = CallerInfo(
            user_id="alice@example.com",
            role="admin",
            ip_address="10.0.0.1",
            groups=["admins"],
        )

        result = caller.to_dict()

        assert result["user_id"] == "alice@example.com"
        assert result["role"] == "admin"
        assert result["ip_address"] == "10.0.0.1"
        assert result["groups"] == ["admins"]


# =============================================================================
# Tests for ToolContext
# =============================================================================


class TestToolContext:
    """Tests for ToolContext class."""

    def test_tool_context_creation(self) -> None:
        """Test creating a ToolContext instance."""
        caller = CallerInfo(user_id="alice@example.com", role="admin")
        ctx = ToolContext(
            tool_name="system.get_basic_info",
            caller=caller,
            request_id="req-123",
        )

        assert ctx.tool_name == "system.get_basic_info"
        assert ctx.caller.user_id == "alice@example.com"
        assert ctx.request_id == "req-123"
        assert ctx.timestamp is not None

    def test_tool_context_with_custom_timestamp(self) -> None:
        """Test ToolContext with custom timestamp."""
        now = datetime.now(UTC)
        ctx = ToolContext(
            tool_name="gpio.read_pin",
            caller=CallerInfo(),
            request_id="req-456",
            timestamp=now,
        )

        assert ctx.timestamp == now

    def test_tool_context_auto_timestamp(self) -> None:
        """Test ToolContext auto-generates timestamp."""
        before = datetime.now(UTC)
        ctx = ToolContext(
            tool_name="system.reboot",
            caller=CallerInfo(),
            request_id="req-789",
        )
        after = datetime.now(UTC)

        assert before <= ctx.timestamp <= after

    def test_tool_context_namespace(self) -> None:
        """Test extracting namespace from tool_name."""
        ctx = ToolContext(
            tool_name="gpio.write_pin",
            caller=CallerInfo(),
            request_id="req-1",
        )

        assert ctx.namespace == "gpio"

    def test_tool_context_namespace_without_dot(self) -> None:
        """Test namespace extraction for single-part tool name."""
        ctx = ToolContext(
            tool_name="status",
            caller=CallerInfo(),
            request_id="req-1",
        )

        assert ctx.namespace == "status"

    def test_tool_context_operation(self) -> None:
        """Test extracting operation from tool_name."""
        ctx = ToolContext(
            tool_name="system.get_basic_info",
            caller=CallerInfo(),
            request_id="req-1",
        )

        assert ctx.operation == "get_basic_info"

    def test_tool_context_operation_without_dot(self) -> None:
        """Test operation extraction for single-part tool name."""
        ctx = ToolContext(
            tool_name="ping",
            caller=CallerInfo(),
            request_id="req-1",
        )

        assert ctx.operation == "ping"

    def test_tool_context_with_numeric_request_id(self) -> None:
        """Test ToolContext with numeric request ID."""
        ctx = ToolContext(
            tool_name="system.health",
            caller=CallerInfo(),
            request_id=42,
        )

        assert ctx.request_id == 42

    def test_tool_context_to_dict(self) -> None:
        """Test ToolContext to_dict method."""
        caller = CallerInfo(user_id="test@example.com", role="viewer")
        ctx = ToolContext(
            tool_name="metrics.get_realtime_metrics",
            caller=caller,
            request_id="req-abc",
        )

        result = ctx.to_dict()

        assert result["tool_name"] == "metrics.get_realtime_metrics"
        assert result["request_id"] == "req-abc"
        assert result["caller"]["user_id"] == "test@example.com"
        assert "timestamp" in result

    def test_tool_context_create_from_request(self) -> None:
        """Test creating ToolContext from a parsed request."""
        from mcp_raspi.protocol import JSONRPCRequest

        request = JSONRPCRequest(
            jsonrpc="2.0",
            id="req-100",
            method="system.get_basic_info",
            params={},
        )

        ctx = ToolContext.from_request(
            request=request,
            caller=CallerInfo(user_id="admin@test.com", role="admin"),
        )

        assert ctx.tool_name == "system.get_basic_info"
        assert ctx.request_id == "req-100"
        assert ctx.caller.user_id == "admin@test.com"

    def test_tool_context_create_for_anonymous(self) -> None:
        """Test creating ToolContext for anonymous request."""
        from mcp_raspi.protocol import JSONRPCRequest

        request = JSONRPCRequest(
            jsonrpc="2.0",
            id=123,
            method="system.get_capabilities",
            params={},
        )

        ctx = ToolContext.from_request(request=request)

        assert ctx.caller.is_authenticated is False
        assert ctx.caller.role == "anonymous"
        assert ctx.request_id == 123

    def test_tool_context_with_metadata(self) -> None:
        """Test ToolContext with additional metadata."""
        ctx = ToolContext(
            tool_name="camera.take_photo",
            caller=CallerInfo(user_id="user@test.com", role="operator"),
            request_id="req-photo-1",
            metadata={"resolution": "1920x1080", "format": "jpeg"},
        )

        assert ctx.metadata["resolution"] == "1920x1080"
        assert ctx.metadata["format"] == "jpeg"

    def test_tool_context_metadata_defaults_to_empty_dict(self) -> None:
        """Test ToolContext metadata defaults to empty dict."""
        ctx = ToolContext(
            tool_name="system.ping",
            caller=CallerInfo(),
            request_id="req-1",
        )

        assert ctx.metadata == {}
