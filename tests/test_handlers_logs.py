"""
Tests for log reading handlers in the Privileged Agent.

This test module validates:
- logs.read_app reads application logs correctly
- logs.read_audit reads audit logs with filters
- Time range and level filtering work correctly
- Pagination works correctly
- Handles missing log files gracefully
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi_ops.handlers.logs import (
    handle_logs_read_app,
    handle_logs_read_audit,
    register_logs_handlers,
)
from mcp_raspi_ops.handlers_core import HandlerRegistry

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_app_log(temp_log_dir: Path) -> Path:
    """Create sample application log file."""
    log_path = temp_log_dir / "app.log"

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
        },
        {
            "timestamp": "2025-01-15T10:20:00Z",
            "level": "INFO",
            "logger": "mcp_raspi.server",
            "message": "Request processed",
        },
    ]

    with open(log_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    return log_path


@pytest.fixture
def sample_audit_log(temp_log_dir: Path) -> Path:
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
        },
    ]

    with open(log_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    return log_path


def make_request(
    operation: str,
    params: dict | None = None,
    request_id: str = "test-req-1",
) -> IPCRequest:
    """Create an IPC request for testing."""
    return IPCRequest(
        id=request_id,
        operation=operation,
        timestamp="2025-01-15T10:00:00Z",
        caller={"user_id": "test@example.com", "role": "admin"},
        params=params or {},
    )


# =============================================================================
# Tests for logs.read_app Handler
# =============================================================================


class TestLogsReadAppHandler:
    """Tests for logs.read_app handler."""

    @pytest.mark.asyncio
    async def test_read_all_entries(self, sample_app_log: Path) -> None:
        """Test reading all log entries."""
        request = make_request(
            "logs.read_app",
            {"log_path": str(sample_app_log)},
        )

        result = await handle_logs_read_app(request)

        assert "entries" in result
        assert "total_count" in result
        assert result["total_count"] == 5
        assert len(result["entries"]) == 5

    @pytest.mark.asyncio
    async def test_filter_by_level(self, sample_app_log: Path) -> None:
        """Test filtering by log level."""
        request = make_request(
            "logs.read_app",
            {"log_path": str(sample_app_log), "level": "INFO"},
        )

        result = await handle_logs_read_app(request)

        assert result["total_count"] == 2
        for entry in result["entries"]:
            assert entry["level"] == "INFO"

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self, sample_app_log: Path) -> None:
        """Test filtering by time range."""
        request = make_request(
            "logs.read_app",
            {
                "log_path": str(sample_app_log),
                "start_time": "2025-01-15T10:05:00Z",
                "end_time": "2025-01-15T10:15:00Z",
            },
        )

        result = await handle_logs_read_app(request)

        assert result["total_count"] == 2

    @pytest.mark.asyncio
    async def test_pagination_limit(self, sample_app_log: Path) -> None:
        """Test limit parameter."""
        request = make_request(
            "logs.read_app",
            {"log_path": str(sample_app_log), "limit": 2},
        )

        result = await handle_logs_read_app(request)

        assert len(result["entries"]) == 2
        assert result["total_count"] == 5

    @pytest.mark.asyncio
    async def test_pagination_offset(self, sample_app_log: Path) -> None:
        """Test offset parameter."""
        request = make_request(
            "logs.read_app",
            {"log_path": str(sample_app_log), "offset": 2, "limit": 2},
        )

        result = await handle_logs_read_app(request)

        assert len(result["entries"]) == 2
        assert result["total_count"] == 5

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, temp_log_dir: Path) -> None:
        """Test handling nonexistent log file."""
        request = make_request(
            "logs.read_app",
            {"log_path": str(temp_log_dir / "nonexistent.log")},
        )

        result = await handle_logs_read_app(request)

        assert result["entries"] == []
        assert result["total_count"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_file(self, temp_log_dir: Path) -> None:
        """Test handling empty log file."""
        empty_log = temp_log_dir / "empty.log"
        empty_log.write_text("")

        request = make_request(
            "logs.read_app",
            {"log_path": str(empty_log)},
        )

        result = await handle_logs_read_app(request)

        assert result["entries"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_returns_most_recent_first(self, sample_app_log: Path) -> None:
        """Test that entries are returned most recent first."""
        request = make_request(
            "logs.read_app",
            {"log_path": str(sample_app_log)},
        )

        result = await handle_logs_read_app(request)

        # Most recent should be first
        timestamps = [e["timestamp"] for e in result["entries"]]
        assert timestamps == sorted(timestamps, reverse=True)


# =============================================================================
# Tests for logs.read_audit Handler
# =============================================================================


class TestLogsReadAuditHandler:
    """Tests for logs.read_audit handler."""

    @pytest.mark.asyncio
    async def test_read_all_entries(self, sample_audit_log: Path) -> None:
        """Test reading all audit entries."""
        request = make_request(
            "logs.read_audit",
            {"log_path": str(sample_audit_log)},
        )

        result = await handle_logs_read_audit(request)

        assert result["total_count"] == 3
        assert len(result["entries"]) == 3

    @pytest.mark.asyncio
    async def test_filter_by_user_id(self, sample_audit_log: Path) -> None:
        """Test filtering by user_id."""
        request = make_request(
            "logs.read_audit",
            {"log_path": str(sample_audit_log), "user_id": "user1"},
        )

        result = await handle_logs_read_audit(request)

        assert result["total_count"] == 2
        for entry in result["entries"]:
            assert "user1" in entry["user_id"]

    @pytest.mark.asyncio
    async def test_filter_by_action(self, sample_audit_log: Path) -> None:
        """Test filtering by action."""
        request = make_request(
            "logs.read_audit",
            {"log_path": str(sample_audit_log), "action": "gpio"},
        )

        result = await handle_logs_read_audit(request)

        assert result["total_count"] == 1
        assert "gpio" in result["entries"][0]["action"]

    @pytest.mark.asyncio
    async def test_combined_filters(self, sample_audit_log: Path) -> None:
        """Test combining multiple filters."""
        request = make_request(
            "logs.read_audit",
            {
                "log_path": str(sample_audit_log),
                "user_id": "user1",
                "action": "system",
            },
        )

        result = await handle_logs_read_audit(request)

        assert result["total_count"] == 1
        entry = result["entries"][0]
        assert "user1" in entry["user_id"]
        assert "system" in entry["action"]

    @pytest.mark.asyncio
    async def test_pagination(self, sample_audit_log: Path) -> None:
        """Test pagination."""
        request = make_request(
            "logs.read_audit",
            {"log_path": str(sample_audit_log), "limit": 1, "offset": 1},
        )

        result = await handle_logs_read_audit(request)

        assert len(result["entries"]) == 1
        assert result["total_count"] == 3


# =============================================================================
# Tests for Handler Registration
# =============================================================================


class TestHandlerRegistration:
    """Tests for handler registration."""

    def test_register_logs_handlers(self) -> None:
        """Test that logs handlers are registered correctly."""
        registry = HandlerRegistry()
        register_logs_handlers(registry)

        operations = registry.get_operations()
        assert "logs.read_app" in operations
        assert "logs.read_audit" in operations
