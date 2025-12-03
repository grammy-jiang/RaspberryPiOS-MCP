"""
Tests for system namespace tools.

This test module validates:
- system.get_basic_info stub returns expected structure
"""

from __future__ import annotations

import pytest

from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.tools.system import handle_system_get_basic_info


class TestSystemGetBasicInfo:
    """Tests for system.get_basic_info tool."""

    @pytest.fixture
    def ctx(self) -> ToolContext:
        """Create a test context."""
        return ToolContext(
            tool_name="system.get_basic_info",
            caller=CallerInfo(user_id="test@example.com", role="viewer"),
            request_id="test-req-1",
        )

    @pytest.mark.asyncio
    async def test_returns_dict(self, ctx: ToolContext) -> None:
        """Test that handler returns a dictionary."""
        result = await handle_system_get_basic_info(ctx, {})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_required_fields(self, ctx: ToolContext) -> None:
        """Test that result contains all required fields."""
        result = await handle_system_get_basic_info(ctx, {})

        required_fields = [
            "hostname",
            "model",
            "cpu_arch",
            "cpu_cores",
            "memory_total_bytes",
            "os_name",
            "os_version",
            "kernel_version",
            "uptime_seconds",
        ]

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_hostname_is_string(self, ctx: ToolContext) -> None:
        """Test hostname is a string."""
        result = await handle_system_get_basic_info(ctx, {})
        assert isinstance(result["hostname"], str)

    @pytest.mark.asyncio
    async def test_cpu_cores_is_positive_int(self, ctx: ToolContext) -> None:
        """Test cpu_cores is a positive integer."""
        result = await handle_system_get_basic_info(ctx, {})
        assert isinstance(result["cpu_cores"], int)
        assert result["cpu_cores"] > 0

    @pytest.mark.asyncio
    async def test_memory_is_positive_int(self, ctx: ToolContext) -> None:
        """Test memory_total_bytes is a positive integer."""
        result = await handle_system_get_basic_info(ctx, {})
        assert isinstance(result["memory_total_bytes"], int)
        assert result["memory_total_bytes"] > 0

    @pytest.mark.asyncio
    async def test_uptime_is_non_negative(self, ctx: ToolContext) -> None:
        """Test uptime_seconds is non-negative."""
        result = await handle_system_get_basic_info(ctx, {})
        assert isinstance(result["uptime_seconds"], int)
        assert result["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_has_timestamp(self, ctx: ToolContext) -> None:
        """Test result includes a timestamp."""
        result = await handle_system_get_basic_info(ctx, {})
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)

    @pytest.mark.asyncio
    async def test_stub_returns_mock_raspberry_pi_data(self, ctx: ToolContext) -> None:
        """Test stub returns recognizable Raspberry Pi mock data."""
        result = await handle_system_get_basic_info(ctx, {})

        # Verify this is our mock data
        assert "raspberrypi" in result["hostname"].lower()
        assert "raspberry" in result["model"].lower()
        assert result["cpu_arch"] in ["aarch64", "armv7l", "arm64"]
