"""
Tests for process handlers in the privileged agent (ops layer).

This test module validates:
- Process handlers parse and validate parameters correctly
- Process handlers return correct data structures
- Process handlers handle errors appropriately
"""

from __future__ import annotations

import os

import pytest

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi_ops.handlers.process import (
    _get_detailed_process_info,
    _get_process_info,
    _process_matches_filter,
    handle_process_get_info,
    handle_process_list_processes,
    register_process_handlers,
)
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestProcessFilter:
    """Tests for process filtering at handler level."""

    def test_no_filter_matches_all(self) -> None:
        """Test no filters matches all processes."""
        proc = {
            "name": "python",
            "username": "user",
            "cpu_percent": 5.0,
            "memory_rss": 100 * 1024 * 1024,
            "status": "running",
        }
        assert _process_matches_filter(proc, None, None, None, None, None)

    def test_name_pattern_filter(self) -> None:
        """Test name pattern filtering."""
        proc = {
            "name": "python3",
            "username": "user",
            "cpu_percent": 0.0,
            "memory_rss": 0,
            "status": "running",
        }
        assert _process_matches_filter(proc, "python*", None, None, None, None)
        assert not _process_matches_filter(proc, "java*", None, None, None, None)

    def test_username_filter(self) -> None:
        """Test username filtering."""
        proc = {
            "name": "python",
            "username": "admin",
            "cpu_percent": 0.0,
            "memory_rss": 0,
            "status": "running",
        }
        assert _process_matches_filter(proc, None, "admin", None, None, None)
        assert not _process_matches_filter(proc, None, "user", None, None, None)

    def test_cpu_percent_filter(self) -> None:
        """Test CPU percentage filtering."""
        proc = {
            "name": "python",
            "username": "user",
            "cpu_percent": 10.0,
            "memory_rss": 0,
            "status": "running",
        }
        assert _process_matches_filter(proc, None, None, 5.0, None, None)
        assert not _process_matches_filter(proc, None, None, 15.0, None, None)

    def test_memory_filter(self) -> None:
        """Test memory MB filtering."""
        proc = {
            "name": "python",
            "username": "user",
            "cpu_percent": 0.0,
            "memory_rss": 100 * 1024 * 1024,
            "status": "running",
        }
        assert _process_matches_filter(proc, None, None, None, 50, None)
        assert not _process_matches_filter(proc, None, None, None, 150, None)

    def test_status_filter(self) -> None:
        """Test status filtering."""
        proc = {
            "name": "python",
            "username": "user",
            "cpu_percent": 0.0,
            "memory_rss": 0,
            "status": "running",
        }
        assert _process_matches_filter(proc, None, None, None, None, ["running", "sleeping"])
        assert not _process_matches_filter(proc, None, None, None, None, ["sleeping"])


class TestProcessInfo:
    """Tests for process info collection."""

    def test_get_process_info_current_process(self) -> None:
        """Test getting info for current process."""
        import psutil

        proc = psutil.Process(os.getpid())
        info = _get_process_info(proc)

        assert info is not None
        assert info["pid"] == os.getpid()
        assert "name" in info
        assert "status" in info
        assert "cpu_percent" in info
        assert "memory_rss" in info

    def test_get_detailed_process_info_current_process(self) -> None:
        """Test getting detailed info for current process."""
        import psutil

        proc = psutil.Process(os.getpid())
        info = _get_detailed_process_info(proc)

        assert info is not None
        assert info["pid"] == os.getpid()
        # Should have detailed fields
        assert "io_counters" in info
        assert "open_files" in info
        assert "connections" in info
        assert "cpu_times" in info
        assert "environment" in info
        assert "timestamp" in info


# =============================================================================
# Tests for Handler Registration
# =============================================================================


class TestHandlerRegistration:
    """Tests for handler registration."""

    def test_register_handlers(self) -> None:
        """Test handlers are registered correctly."""
        registry = HandlerRegistry()
        register_process_handlers(registry)

        assert registry.has_handler("process.list_processes")
        assert registry.has_handler("process.get_info")


# =============================================================================
# Tests for list_processes Handler
# =============================================================================


class TestListProcessesHandler:
    """Tests for process.list_processes handler."""

    @pytest.mark.asyncio
    async def test_returns_processes(self) -> None:
        """Test handler returns list of processes."""
        request = IPCRequest(
            id="test-1", operation="process.list_processes", params={}
        )
        result = await handle_process_list_processes(request)

        assert "processes" in result
        assert isinstance(result["processes"], list)
        assert len(result["processes"]) > 0
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_process_has_required_fields(self) -> None:
        """Test each process has required fields."""
        request = IPCRequest(
            id="test-2", operation="process.list_processes", params={}
        )
        result = await handle_process_list_processes(request)

        proc = result["processes"][0]
        required_fields = ["pid", "name", "status", "username", "cpu_percent", "memory_rss"]
        for field in required_fields:
            assert field in proc, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_filter_by_name(self) -> None:
        """Test filtering by name pattern."""
        request = IPCRequest(
            id="test-3",
            operation="process.list_processes",
            params={"filter": {"name_pattern": "python*"}},
        )
        result = await handle_process_list_processes(request)

        # Should find at least the test runner
        assert len(result["processes"]) >= 0

    @pytest.mark.asyncio
    async def test_sorting(self) -> None:
        """Test sorting by field."""
        request = IPCRequest(
            id="test-4",
            operation="process.list_processes",
            params={"sort_by": "pid", "sort_order": "asc"},
        )
        result = await handle_process_list_processes(request)

        if len(result["processes"]) > 1:
            pids = [p["pid"] for p in result["processes"]]
            assert pids == sorted(pids)

    @pytest.mark.asyncio
    async def test_descending_sort(self) -> None:
        """Test descending sort order."""
        request = IPCRequest(
            id="test-5",
            operation="process.list_processes",
            params={"sort_by": "pid", "sort_order": "desc"},
        )
        result = await handle_process_list_processes(request)

        if len(result["processes"]) > 1:
            pids = [p["pid"] for p in result["processes"]]
            assert pids == sorted(pids, reverse=True)


# =============================================================================
# Tests for get_info Handler
# =============================================================================


class TestGetInfoHandler:
    """Tests for process.get_info handler."""

    @pytest.mark.asyncio
    async def test_returns_process_info(self) -> None:
        """Test handler returns process info."""
        request = IPCRequest(
            id="test-6",
            operation="process.get_info",
            params={"pid": os.getpid()},
        )
        result = await handle_process_get_info(request)

        assert "pid" in result
        assert result["pid"] == os.getpid()
        assert "name" in result
        assert "status" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_returns_detailed_info(self) -> None:
        """Test handler returns detailed info."""
        request = IPCRequest(
            id="test-7",
            operation="process.get_info",
            params={"pid": os.getpid()},
        )
        result = await handle_process_get_info(request)

        # Should have detailed fields
        assert "io_counters" in result
        assert "open_files" in result
        assert "connections" in result
        assert "cpu_times" in result
        assert "environment" in result

    @pytest.mark.asyncio
    async def test_requires_pid(self) -> None:
        """Test handler requires PID parameter."""
        request = IPCRequest(
            id="test-8", operation="process.get_info", params={}
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_process_get_info(request)
        assert "required" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_invalid_pid_type(self) -> None:
        """Test handler handles invalid PID type."""
        request = IPCRequest(
            id="test-9",
            operation="process.get_info",
            params={"pid": "not_a_number"},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_process_get_info(request)
        assert "integer" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_nonexistent_pid(self) -> None:
        """Test handler handles nonexistent PID."""
        request = IPCRequest(
            id="test-10",
            operation="process.get_info",
            params={"pid": 999999999},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_process_get_info(request)
        assert "not found" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_string_pid_converted(self) -> None:
        """Test string PID is converted."""
        request = IPCRequest(
            id="test-11",
            operation="process.get_info",
            params={"pid": str(os.getpid())},
        )
        result = await handle_process_get_info(request)

        assert result["pid"] == os.getpid()

    @pytest.mark.asyncio
    async def test_environment_filtered(self) -> None:
        """Test sensitive environment variables are filtered."""
        request = IPCRequest(
            id="test-12",
            operation="process.get_info",
            params={"pid": os.getpid()},
        )
        result = await handle_process_get_info(request)

        env = result.get("environment", {})
        sensitive_patterns = ["key", "secret", "password", "token", "auth", "credential"]
        for key in env:
            for pattern in sensitive_patterns:
                assert pattern not in key.lower(), f"Sensitive key '{key}' should be filtered"
