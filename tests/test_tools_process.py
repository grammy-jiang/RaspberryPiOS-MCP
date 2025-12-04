"""
Tests for process namespace tools.

This test module validates:
- process.list_processes returns running processes
- process.list_processes filtering works correctly
- process.list_processes pagination works correctly
- process.get_info returns detailed process information
- process.get_info handles invalid PIDs
"""

from __future__ import annotations

import os

import pytest

from mcp_raspi.config import AppConfig, ProcessToolsConfig, TestingConfig, ToolsConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.process_utils import process_matches_filter
from mcp_raspi.tools.process import (
    _is_pid_protected,
    _validate_pagination,
    _validate_pid,
    handle_process_get_info,
    handle_process_list_processes,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def viewer_ctx() -> ToolContext:
    """Create a test context with viewer role."""
    return ToolContext(
        tool_name="process.list_processes",
        caller=CallerInfo(user_id="viewer@example.com", role="viewer"),
        request_id="test-req-viewer",
    )


@pytest.fixture
def default_config() -> AppConfig:
    """Create a default config."""
    config = AppConfig()
    config.testing = TestingConfig(sandbox_mode="full")
    config.tools = ToolsConfig(
        process=ProcessToolsConfig(
            enabled=True,
            allowed_users=[],
            deny_pids=[1],  # Protect PID 1
        )
    )
    return config


# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestPidProtection:
    """Tests for PID protection."""

    def test_pid_1_always_protected(self) -> None:
        """Test PID 1 is always protected."""
        assert _is_pid_protected(1, [])
        assert _is_pid_protected(1, [2, 3, 4])

    def test_deny_list_pids_protected(self) -> None:
        """Test PIDs in deny list are protected."""
        assert _is_pid_protected(100, [100, 200])
        assert _is_pid_protected(200, [100, 200])

    def test_non_protected_pids(self) -> None:
        """Test non-protected PIDs are not protected."""
        assert not _is_pid_protected(12345, [])
        assert not _is_pid_protected(12345, [100, 200])


class TestValidation:
    """Tests for parameter validation functions."""

    def test_validate_pid_valid(self) -> None:
        """Test valid PIDs are accepted."""
        assert _validate_pid(1) == 1
        assert _validate_pid(12345) == 12345
        assert _validate_pid("100") == 100  # String conversion

    def test_validate_pid_none(self) -> None:
        """Test None PID raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_pid(None)
        assert "required" in str(exc_info.value)

    def test_validate_pid_negative(self) -> None:
        """Test negative PID raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_pid(-1)
        assert "positive" in str(exc_info.value)

    def test_validate_pid_invalid_string(self) -> None:
        """Test invalid string PID raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            _validate_pid("not_a_number")
        assert "integer" in str(exc_info.value)

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


class TestProcessFilter:
    """Tests for process filtering logic."""

    def test_no_filter_matches_all(self) -> None:
        """Test no filters matches all processes."""
        proc = {"name": "python", "username": "user", "cpu_percent": 5.0, "memory_rss": 100 * 1024 * 1024, "status": "running"}
        assert process_matches_filter(proc, None, None, None, None, None)

    def test_name_pattern_filter(self) -> None:
        """Test name pattern filtering."""
        proc = {"name": "python3", "username": "user", "cpu_percent": 0.0, "memory_rss": 0, "status": "running"}
        assert process_matches_filter(proc, "python*", None, None, None, None)
        assert not process_matches_filter(proc, "java*", None, None, None, None)

    def test_username_filter(self) -> None:
        """Test username filtering."""
        proc = {"name": "python", "username": "admin", "cpu_percent": 0.0, "memory_rss": 0, "status": "running"}
        assert process_matches_filter(proc, None, "admin", None, None, None)
        assert not process_matches_filter(proc, None, "user", None, None, None)

    def test_cpu_percent_filter(self) -> None:
        """Test CPU percentage filtering."""
        proc = {"name": "python", "username": "user", "cpu_percent": 10.0, "memory_rss": 0, "status": "running"}
        assert process_matches_filter(proc, None, None, 5.0, None, None)
        assert not process_matches_filter(proc, None, None, 15.0, None, None)

    def test_memory_mb_filter(self) -> None:
        """Test memory MB filtering."""
        proc = {"name": "python", "username": "user", "cpu_percent": 0.0, "memory_rss": 100 * 1024 * 1024, "status": "running"}
        assert process_matches_filter(proc, None, None, None, 50, None)
        assert not process_matches_filter(proc, None, None, None, 150, None)

    def test_status_filter(self) -> None:
        """Test status filtering."""
        proc = {"name": "python", "username": "user", "cpu_percent": 0.0, "memory_rss": 0, "status": "running"}
        assert process_matches_filter(proc, None, None, None, None, ["running", "sleeping"])
        assert not process_matches_filter(proc, None, None, None, None, ["sleeping"])

    def test_combined_filters(self) -> None:
        """Test multiple filters combined."""
        proc = {"name": "python3", "username": "admin", "cpu_percent": 10.0, "memory_rss": 100 * 1024 * 1024, "status": "running"}
        # All filters match
        assert process_matches_filter(proc, "python*", "admin", 5.0, 50, ["running"])
        # One filter doesn't match
        assert not process_matches_filter(proc, "python*", "user", 5.0, 50, ["running"])


# =============================================================================
# Tests for process.list_processes
# =============================================================================


class TestProcessListProcesses:
    """Tests for process.list_processes tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_process_list_processes(viewer_ctx, {}, _config=default_config)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test result contains required fields."""
        result = await handle_process_list_processes(viewer_ctx, {}, _config=default_config)

        assert "processes" in result
        assert "total_count" in result
        assert "returned_count" in result
        assert "has_more" in result
        assert "timestamp" in result
        assert isinstance(result["processes"], list)

    @pytest.mark.asyncio
    async def test_process_fields(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test each process has required fields."""
        result = await handle_process_list_processes(viewer_ctx, {}, _config=default_config)

        # Should have at least the test process itself
        assert len(result["processes"]) > 0

        proc = result["processes"][0]
        required_fields = ["pid", "name", "status", "username", "cpu_percent", "memory_rss"]
        for field in required_fields:
            assert field in proc, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_pagination(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test pagination parameters work correctly."""
        # Get first page
        result1 = await handle_process_list_processes(
            viewer_ctx, {"offset": 0, "limit": 5}, _config=default_config
        )
        assert result1["returned_count"] <= 5

        # If there are more results, get second page
        if result1["has_more"]:
            result2 = await handle_process_list_processes(
                viewer_ctx, {"offset": 5, "limit": 5}, _config=default_config
            )
            # Both pages should have returned results
            assert len(result1["processes"]) > 0
            assert len(result2["processes"]) > 0

    @pytest.mark.asyncio
    async def test_name_filter(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test name pattern filter works."""
        result = await handle_process_list_processes(
            viewer_ctx,
            {"filter": {"name_pattern": "python*"}},
            _config=default_config,
        )

        # Should find at least the test runner (python)
        names = [p["name"] for p in result["processes"]]
        # At least one should match the pattern
        assert any("python" in name.lower() for name in names) or len(names) == 0

    @pytest.mark.asyncio
    async def test_sorting(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test sorting works correctly."""
        # Sort by PID descending
        result = await handle_process_list_processes(
            viewer_ctx,
            {"sort_by": "pid", "sort_order": "desc"},
            _config=default_config,
        )

        if len(result["processes"]) > 1:
            pids = [p["pid"] for p in result["processes"]]
            assert pids == sorted(pids, reverse=True)

    @pytest.mark.asyncio
    async def test_invalid_sort_field(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test invalid sort field is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_process_list_processes(
                viewer_ctx,
                {"sort_by": "invalid_field"},
                _config=default_config,
            )
        assert "sort_by" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_sort_order(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test invalid sort order is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_process_list_processes(
                viewer_ctx,
                {"sort_order": "invalid"},
                _config=default_config,
            )
        assert "sort_order" in str(exc_info.value)


# =============================================================================
# Tests for process.get_info
# =============================================================================


class TestProcessGetInfo:
    """Tests for process.get_info tool."""

    @pytest.mark.asyncio
    async def test_returns_dict(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test that handler returns a dictionary."""
        # Use current process PID
        pid = os.getpid()
        result = await handle_process_get_info(
            viewer_ctx, {"pid": pid}, config=default_config
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test result contains required fields."""
        pid = os.getpid()
        result = await handle_process_get_info(
            viewer_ctx, {"pid": pid}, config=default_config
        )

        required_fields = [
            "pid",
            "name",
            "status",
            "username",
            "cpu_percent",
            "memory_rss",
            "memory_vms",
            "num_threads",
            "ppid",
        ]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_contains_detailed_fields(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test result contains detailed info fields."""
        pid = os.getpid()
        result = await handle_process_get_info(
            viewer_ctx, {"pid": pid}, config=default_config
        )

        # Detailed fields that should be present
        detailed_fields = ["io_counters", "open_files", "connections", "cpu_times", "environment"]
        for field in detailed_fields:
            assert field in result, f"Missing detailed field: {field}"

    @pytest.mark.asyncio
    async def test_requires_pid(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test pid parameter is required."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_process_get_info(viewer_ctx, {}, config=default_config)
        assert "required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_pid_raises_error(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test invalid PID raises appropriate error."""
        # Use a very high PID that likely doesn't exist
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_process_get_info(
                viewer_ctx, {"pid": 999999999}, config=default_config
            )
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_negative_pid_raises_error(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test negative PID raises error."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            await handle_process_get_info(
                viewer_ctx, {"pid": -1}, config=default_config
            )
        assert "positive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_string_pid_converted(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test string PID is converted to int."""
        pid = os.getpid()
        result = await handle_process_get_info(
            viewer_ctx, {"pid": str(pid)}, config=default_config
        )
        assert result["pid"] == pid

    @pytest.mark.asyncio
    async def test_environment_filtered(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test sensitive environment variables are filtered."""
        pid = os.getpid()
        result = await handle_process_get_info(
            viewer_ctx, {"pid": pid}, config=default_config
        )

        # Check that environment is filtered for sensitive patterns
        env = result.get("environment", {})
        sensitive_patterns = ["key", "secret", "password", "token", "auth", "credential"]
        for key in env:
            for pattern in sensitive_patterns:
                assert pattern not in key.lower(), f"Sensitive key '{key}' should be filtered"

    @pytest.mark.asyncio
    async def test_timestamp_included(
        self, viewer_ctx: ToolContext, default_config: AppConfig
    ) -> None:
        """Test timestamp is included in response."""
        pid = os.getpid()
        result = await handle_process_get_info(
            viewer_ctx, {"pid": pid}, config=default_config
        )
        assert "timestamp" in result
        assert "T" in result["timestamp"]  # ISO 8601 format


# =============================================================================
# Tests for Handlers (ops layer)
# =============================================================================


class TestProcessHandlersOps:
    """Tests for ops-layer process handlers."""

    @pytest.mark.asyncio
    async def test_handler_list_processes_returns_processes(self) -> None:
        """Test ops handler returns processes."""
        from mcp_raspi.ipc.protocol import IPCRequest
        from mcp_raspi_ops.handlers.process import handle_process_list_processes

        request = IPCRequest(id="test-1", operation="process.list_processes", params={})
        result = await handle_process_list_processes(request)

        assert "processes" in result
        assert isinstance(result["processes"], list)
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_handler_get_info_returns_details(self) -> None:
        """Test ops handler returns process details."""
        from mcp_raspi.ipc.protocol import IPCRequest
        from mcp_raspi_ops.handlers.process import handle_process_get_info

        request = IPCRequest(
            id="test-2", operation="process.get_info", params={"pid": os.getpid()}
        )
        result = await handle_process_get_info(request)

        assert "pid" in result
        assert result["pid"] == os.getpid()
        assert "name" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_handler_get_info_invalid_pid(self) -> None:
        """Test ops handler raises error for invalid PID."""
        from mcp_raspi.ipc.protocol import IPCRequest
        from mcp_raspi_ops.handlers.process import handle_process_get_info
        from mcp_raspi_ops.handlers_core import HandlerError

        request = IPCRequest(
            id="test-3", operation="process.get_info", params={"pid": 999999999}
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_process_get_info(request)
        assert "not found" in exc_info.value.message
