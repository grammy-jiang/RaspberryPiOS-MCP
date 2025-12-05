"""
Tests for logs namespace tools.

This test module validates:
- logs.get_recent_app_logs returns application logs with filters
- logs.get_recent_audit_logs returns audit logs (admin only)
- Time range filtering works correctly
- Level filtering works correctly
- Pagination (offset/limit) works correctly
- Sensitive data is masked in returned logs
- Viewer role can read app logs, admin required for audit logs
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mcp_raspi.config import AppConfig, LoggingConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.security.rbac import PermissionDeniedError
from mcp_raspi.tools.logs import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    handle_logs_get_recent_app_logs,
    handle_logs_get_recent_audit_logs,
    mask_log_entry,
    mask_sensitive_dict,
    mask_sensitive_string,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="logs.get_recent_app_logs",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def operator_ctx() -> ToolContext:
    """Create a test context with operator role."""
    return ToolContext(
        tool_name="logs.get_recent_app_logs",
        caller=CallerInfo(user_id="operator@example.com", role="operator"),
        request_id="test-req-operator",
    )


@pytest.fixture
def admin_ctx() -> ToolContext:
    """Create a test context with admin role."""
    return ToolContext(
        tool_name="logs.get_recent_app_logs",
        caller=CallerInfo(user_id="admin@example.com", role="admin"),
        request_id="test-req-admin",
    )


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_app_logs(temp_log_dir: Path) -> Path:
    """Create sample application log file."""
    log_path = temp_log_dir / "app.log"

    # Create sample log entries
    entries = [
        {
            "timestamp": "2025-01-15T10:00:00Z",
            "level": "INFO",
            "logger": "mcp_raspi.server",
            "message": "Server started",
        },
        {
            "timestamp": "2025-01-15T10:05:00Z",
            "level": "DEBUG",
            "logger": "mcp_raspi.tools.gpio",
            "message": "GPIO read request",
        },
        {
            "timestamp": "2025-01-15T10:10:00Z",
            "level": "WARNING",
            "logger": "mcp_raspi.security",
            "message": "Rate limit approaching",
        },
        {
            "timestamp": "2025-01-15T10:15:00Z",
            "level": "ERROR",
            "logger": "mcp_raspi.ipc",
            "message": "Connection failed",
            "api_key": "secret_key_12345678",
        },
        {
            "timestamp": "2025-01-15T10:20:00Z",
            "level": "INFO",
            "logger": "mcp_raspi.server",
            "message": "Request processed",
            "token": "bearer_token_abcdefgh",
        },
    ]

    with open(log_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    return log_path


@pytest.fixture
def sample_audit_logs(temp_log_dir: Path) -> Path:
    """Create sample audit log file."""
    log_path = temp_log_dir / "audit.log"

    entries = [
        {
            "timestamp": "2025-01-15T10:00:00Z",
            "event_type": "tool_call",
            "user_id": "user1@example.com",
            "role": "admin",
            "action": "system.reboot",
            "result": "success",
        },
        {
            "timestamp": "2025-01-15T10:05:00Z",
            "event_type": "tool_call",
            "user_id": "user2@example.com",
            "role": "operator",
            "action": "gpio.write_pin",
            "result": "success",
        },
        {
            "timestamp": "2025-01-15T10:10:00Z",
            "event_type": "tool_call",
            "user_id": "user1@example.com",
            "role": "admin",
            "action": "service.control",
            "result": "error",
            "error_code": "permission_denied",
        },
    ]

    with open(log_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    return log_path


@pytest.fixture
def config_with_logs(
    temp_log_dir: Path,  # noqa: ARG001
    sample_app_logs: Path,
    sample_audit_logs: Path,
) -> AppConfig:
    """Create config with log paths."""
    config = AppConfig()
    config.logging = LoggingConfig(
        app_log_path=str(sample_app_logs),
        audit_log_path=str(sample_audit_logs),
    )
    return config


# =============================================================================
# Tests for Sensitive Data Masking
# =============================================================================


class TestSensitiveDataMasking:
    """Tests for sensitive data masking functions."""

    def test_mask_api_key_in_string(self) -> None:
        """Test masking API key in string."""
        text = "Error: api_key=secret12345 failed"
        masked = mask_sensitive_string(text)
        assert "secret12345" not in masked
        assert "REDACTED" in masked

    def test_mask_token_in_string(self) -> None:
        """Test masking token in string."""
        text = 'token: "bearer_abc123xyz"'
        masked = mask_sensitive_string(text)
        assert "bearer_abc123xyz" not in masked
        assert "REDACTED" in masked

    def test_mask_password_in_string(self) -> None:
        """Test masking password in string."""
        text = "password=mysecretpassword"
        masked = mask_sensitive_string(text)
        assert "mysecretpassword" not in masked
        assert "REDACTED" in masked

    def test_mask_bearer_token(self) -> None:
        """Test masking bearer token."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
        masked = mask_sensitive_string(text)
        assert "eyJhbGciOiJIUzI1NiIs" not in masked
        assert "REDACTED" in masked

    def test_mask_sensitive_dict_simple(self) -> None:
        """Test masking sensitive fields in dict."""
        data = {
            "user": "test@example.com",
            "api_key": "secret_key_12345678",
            "token": "bearer_token_abcdefgh",
        }
        masked = mask_sensitive_dict(data)

        assert masked["user"] == "test@example.com"
        assert "REDACTED" in masked["api_key"] or "***" in masked["api_key"]
        assert "REDACTED" in masked["token"] or "***" in masked["token"]

    def test_mask_sensitive_dict_nested(self) -> None:
        """Test masking nested sensitive fields."""
        data = {
            "request": {
                "user": "test@example.com",
                "auth": {
                    "password": "secret123",
                },
            },
        }
        masked = mask_sensitive_dict(data)

        assert masked["request"]["user"] == "test@example.com"
        assert "secret123" not in str(masked)

    def test_mask_log_entry(self) -> None:
        """Test masking a complete log entry."""
        entry = {
            "timestamp": "2025-01-15T10:00:00Z",
            "level": "INFO",
            "message": "Request with api_key=secret123",
            "params": {
                "token": "bearer_abc123xyz",
            },
        }
        masked = mask_log_entry(entry)

        assert masked["timestamp"] == "2025-01-15T10:00:00Z"
        assert masked["level"] == "INFO"
        assert "secret123" not in masked["message"]
        assert "bearer_abc123xyz" not in str(masked)


# =============================================================================
# Tests for logs.get_recent_app_logs
# =============================================================================


class TestLogsGetRecentAppLogs:
    """Tests for logs.get_recent_app_logs tool."""

    @pytest.mark.asyncio
    async def test_viewer_can_read_app_logs(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that viewer role can read application logs."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {}, config=config_with_logs
        )

        assert "entries" in result
        assert "total_count" in result
        assert result["total_count"] == 5

    @pytest.mark.asyncio
    async def test_operator_can_read_app_logs(
        self, operator_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that operator role can read application logs."""
        result = await handle_logs_get_recent_app_logs(
            operator_ctx, {}, config=config_with_logs
        )

        assert "entries" in result
        assert result["total_count"] == 5

    @pytest.mark.asyncio
    async def test_admin_can_read_app_logs(
        self, admin_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that admin role can read application logs."""
        result = await handle_logs_get_recent_app_logs(
            admin_ctx, {}, config=config_with_logs
        )

        assert "entries" in result
        assert result["total_count"] == 5

    @pytest.mark.asyncio
    async def test_level_filtering(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test filtering by log level."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {"level": "INFO"}, config=config_with_logs
        )

        assert result["total_count"] == 2
        for entry in result["entries"]:
            assert entry["level"] == "INFO"

    @pytest.mark.asyncio
    async def test_level_filtering_error(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test filtering by ERROR level."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {"level": "ERROR"}, config=config_with_logs
        )

        assert result["total_count"] == 1
        assert result["entries"][0]["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_invalid_level(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test invalid log level is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_logs_get_recent_app_logs(
                viewer_ctx, {"level": "INVALID"}, config=config_with_logs
            )
        assert "Invalid log level" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pagination_limit(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test limit parameter."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {"limit": 2}, config=config_with_logs
        )

        assert len(result["entries"]) == 2
        assert result["total_count"] == 5
        assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_pagination_offset(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test offset parameter."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {"offset": 2, "limit": 2}, config=config_with_logs
        )

        assert len(result["entries"]) == 2
        assert result["total_count"] == 5

    @pytest.mark.asyncio
    async def test_time_range_filtering(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test filtering by time range."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx,
            {
                "start_time": "2025-01-15T10:05:00Z",
                "end_time": "2025-01-15T10:15:00Z",
            },
            config=config_with_logs,
        )

        # Should include entries at 10:05, 10:10 (2 entries)
        assert result["total_count"] == 2

    @pytest.mark.asyncio
    async def test_invalid_limit_too_large(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that limit exceeding MAX_LIMIT is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_logs_get_recent_app_logs(
                viewer_ctx, {"limit": MAX_LIMIT + 1}, config=config_with_logs
            )
        assert "limit cannot exceed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_limit_negative(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that negative limit is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_logs_get_recent_app_logs(
                viewer_ctx, {"limit": -1}, config=config_with_logs
            )
        assert "limit must be at least 1" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_offset_negative(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that negative offset is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_logs_get_recent_app_logs(
                viewer_ctx, {"offset": -1}, config=config_with_logs
            )
        assert "offset must be non-negative" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_time_range(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that start_time after end_time is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_logs_get_recent_app_logs(
                viewer_ctx,
                {
                    "start_time": "2025-01-15T12:00:00Z",
                    "end_time": "2025-01-15T10:00:00Z",
                },
                config=config_with_logs,
            )
        assert "start_time cannot be after end_time" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sensitive_data_masked(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that sensitive data is masked in returned logs."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {}, config=config_with_logs
        )

        # Check that api_key and token values are masked
        for entry in result["entries"]:
            entry_str = json.dumps(entry)
            assert "secret_key_12345678" not in entry_str
            assert "bearer_token_abcdefgh" not in entry_str

    @pytest.mark.asyncio
    async def test_empty_log_file(
        self, viewer_ctx: ToolContext, temp_log_dir: Path
    ) -> None:
        """Test handling of empty log file."""
        empty_log = temp_log_dir / "empty.log"
        empty_log.write_text("")

        config = AppConfig()
        config.logging = LoggingConfig(app_log_path=str(empty_log))

        result = await handle_logs_get_recent_app_logs(viewer_ctx, {}, config=config)

        assert result["entries"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_nonexistent_log_file(
        self, viewer_ctx: ToolContext, temp_log_dir: Path
    ) -> None:
        """Test handling of nonexistent log file."""
        config = AppConfig()
        config.logging = LoggingConfig(
            app_log_path=str(temp_log_dir / "nonexistent.log")
        )

        result = await handle_logs_get_recent_app_logs(viewer_ctx, {}, config=config)

        assert result["entries"] == []
        assert result["total_count"] == 0


# =============================================================================
# Tests for logs.get_recent_audit_logs
# =============================================================================


class TestLogsGetRecentAuditLogs:
    """Tests for logs.get_recent_audit_logs tool."""

    @pytest.mark.asyncio
    async def test_viewer_denied(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that viewer role is denied access to audit logs."""
        with pytest.raises(PermissionDeniedError):
            await handle_logs_get_recent_audit_logs(
                viewer_ctx, {}, config=config_with_logs
            )

    @pytest.mark.asyncio
    async def test_operator_denied(
        self, operator_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that operator role is denied access to audit logs."""
        with pytest.raises(PermissionDeniedError):
            await handle_logs_get_recent_audit_logs(
                operator_ctx, {}, config=config_with_logs
            )

    @pytest.mark.asyncio
    async def test_admin_allowed(
        self, admin_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that admin role can read audit logs."""
        result = await handle_logs_get_recent_audit_logs(
            admin_ctx, {}, config=config_with_logs
        )

        assert "entries" in result
        assert result["total_count"] == 3

    @pytest.mark.asyncio
    async def test_filter_by_user_id(
        self, admin_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test filtering audit logs by user_id."""
        result = await handle_logs_get_recent_audit_logs(
            admin_ctx, {"user_id": "user1"}, config=config_with_logs
        )

        assert result["total_count"] == 2
        for entry in result["entries"]:
            assert "user1" in entry["user_id"]

    @pytest.mark.asyncio
    async def test_filter_by_action(
        self, admin_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test filtering audit logs by action."""
        result = await handle_logs_get_recent_audit_logs(
            admin_ctx, {"action": "gpio"}, config=config_with_logs
        )

        assert result["total_count"] == 1
        assert "gpio" in result["entries"][0]["action"]

    @pytest.mark.asyncio
    async def test_pagination(
        self, admin_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test pagination of audit logs."""
        result = await handle_logs_get_recent_audit_logs(
            admin_ctx, {"limit": 1, "offset": 1}, config=config_with_logs
        )

        assert len(result["entries"]) == 1
        assert result["total_count"] == 3
        assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_filters_applied_in_response(
        self, admin_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that applied filters are included in response."""
        result = await handle_logs_get_recent_audit_logs(
            admin_ctx,
            {"limit": 10, "offset": 0, "user_id": "user1"},
            config=config_with_logs,
        )

        assert result["filters_applied"]["limit"] == 10
        assert result["filters_applied"]["offset"] == 0
        assert result["filters_applied"]["user_id"] == "user1"


# =============================================================================
# Tests for Default Values
# =============================================================================


class TestDefaultValues:
    """Tests for default parameter values."""

    @pytest.mark.asyncio
    async def test_default_limit(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that default limit is applied."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {}, config=config_with_logs
        )

        assert result["filters_applied"]["limit"] == DEFAULT_LIMIT

    @pytest.mark.asyncio
    async def test_default_offset(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that default offset is 0."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {}, config=config_with_logs
        )

        assert result["filters_applied"]["offset"] == 0

    @pytest.mark.asyncio
    async def test_default_level_none(
        self, viewer_ctx: ToolContext, config_with_logs: AppConfig
    ) -> None:
        """Test that default level filter is None (all levels)."""
        result = await handle_logs_get_recent_app_logs(
            viewer_ctx, {}, config=config_with_logs
        )

        assert result["filters_applied"]["level"] is None
