"""
Tests for manage namespace tools.

Tests cover:
- manage.get_server_status tool
- Server start time tracking
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from time import time

import pytest

import mcp_raspi.tools.manage as manage_module
from mcp_raspi.config import AppConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.tools.manage import (
    get_server_start_time,
    handle_manage_get_server_status,
    set_server_start_time,
)
from mcp_raspi.updates.version import VersionManager

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_context() -> ToolContext:
    """Create a mock ToolContext for testing."""
    caller = CallerInfo(
        user_id="test-user",
        role="admin",
    )
    return ToolContext(
        tool_name="manage.get_server_status",
        caller=caller,
        request_id="test-request-123",
    )


@pytest.fixture
def default_config() -> AppConfig:
    """Create a default AppConfig for testing."""
    return AppConfig()


# =============================================================================
# Server Start Time Tests
# =============================================================================


class TestServerStartTime:
    """Tests for server start time tracking."""

    def test_set_and_get_start_time(self) -> None:
        """Test setting and getting server start time."""
        test_time = time()
        set_server_start_time(test_time)

        result = get_server_start_time()

        assert result == test_time

    def test_get_start_time_initializes_if_none(self) -> None:
        """Test that get_server_start_time initializes if not set."""
        # Reset the global
        manage_module._SERVER_START_TIME = None

        before = time()
        result = get_server_start_time()
        after = time()

        assert before <= result <= after

    def test_set_start_time_without_argument(self) -> None:
        """Test setting start time without argument uses current time."""
        before = time()
        set_server_start_time()
        after = time()

        result = get_server_start_time()

        assert before <= result <= after


# =============================================================================
# manage.get_server_status Tests
# =============================================================================


class TestHandleManageGetServerStatus:
    """Tests for handle_manage_get_server_status tool."""

    @pytest.mark.asyncio
    async def test_basic_status_response(self, mock_context: ToolContext) -> None:
        """Test that basic status response contains required fields."""
        # Set a known start time
        start_time = time() - 3600  # 1 hour ago
        set_server_start_time(start_time)

        result = await handle_manage_get_server_status(mock_context, {})

        assert "version" in result
        assert "started_at" in result
        assert "uptime_seconds" in result
        assert "python_version" in result
        assert "platform" in result
        assert "config_summary" in result

    @pytest.mark.asyncio
    async def test_uptime_calculated_correctly(self, mock_context: ToolContext) -> None:
        """Test that uptime is calculated correctly."""
        # Set start time to 1 hour ago
        start_time = time() - 3600
        set_server_start_time(start_time)

        result = await handle_manage_get_server_status(mock_context, {})

        # Uptime should be approximately 3600 seconds
        assert result["uptime_seconds"] >= 3600
        assert result["uptime_seconds"] < 3700  # Allow some margin

    @pytest.mark.asyncio
    async def test_platform_info_present(self, mock_context: ToolContext) -> None:
        """Test that platform info is included."""
        result = await handle_manage_get_server_status(mock_context, {})

        platform = result["platform"]
        assert "system" in platform
        assert "release" in platform
        assert "machine" in platform

    @pytest.mark.asyncio
    async def test_config_summary_with_config(
        self, mock_context: ToolContext, default_config: AppConfig
    ) -> None:
        """Test that config summary is populated when config is provided."""
        result = await handle_manage_get_server_status(
            mock_context, {}, config=default_config
        )

        config_summary = result["config_summary"]
        assert "security_mode" in config_summary
        assert "sandbox_mode" in config_summary
        assert "update_backend" in config_summary
        assert "remote_update_enabled" in config_summary
        assert "os_update_enabled" in config_summary

    @pytest.mark.asyncio
    async def test_config_summary_without_config(
        self, mock_context: ToolContext
    ) -> None:
        """Test that config summary is empty dict when no config provided."""
        result = await handle_manage_get_server_status(mock_context, {}, config=None)

        assert result["config_summary"] == {}

    @pytest.mark.asyncio
    async def test_version_from_package(self, mock_context: ToolContext) -> None:
        """Test that version comes from package __version__."""
        from mcp_raspi import __version__

        result = await handle_manage_get_server_status(mock_context, {})

        assert result["version"] == __version__

    @pytest.mark.asyncio
    async def test_started_at_format(self, mock_context: ToolContext) -> None:
        """Test that started_at is ISO 8601 format."""
        result = await handle_manage_get_server_status(mock_context, {})

        # Should be parseable as ISO 8601
        started_at = result["started_at"]
        assert "T" in started_at
        assert started_at.endswith("Z") or "+" in started_at or "-" in started_at[-6:]

    @pytest.mark.asyncio
    async def test_last_update_from_version_file(
        self, mock_context: ToolContext
    ) -> None:
        """Test that last_update is loaded from version.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            # Create a version file
            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("1.0.0")
            manager.update_version("1.1.0", source="pypi")

            result = await handle_manage_get_server_status(
                mock_context, {}, version_file=version_file
            )

            last_update = result["last_update"]
            assert last_update is not None
            assert last_update["version"] == "1.1.0"
            assert last_update["source"] == "pypi"
            assert last_update["updated_from"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_last_update_none_when_no_file(
        self, mock_context: ToolContext
    ) -> None:
        """Test that last_update is None when no version.json exists."""
        result = await handle_manage_get_server_status(
            mock_context, {}, version_file="/nonexistent/version.json"
        )

        assert result["last_update"] is None

    @pytest.mark.asyncio
    async def test_build_field_present(self, mock_context: ToolContext) -> None:
        """Test that build field is present (even if None)."""
        result = await handle_manage_get_server_status(mock_context, {})

        assert "build" in result


# =============================================================================
# Integration Tests
# =============================================================================


class TestManageToolsIntegration:
    """Integration tests for manage tools."""

    @pytest.mark.asyncio
    async def test_full_status_with_version_file(
        self, mock_context: ToolContext, default_config: AppConfig
    ) -> None:
        """Test full status response with version file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup version file
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("1.0.0")

            # Set start time
            set_server_start_time(time() - 60)

            result = await handle_manage_get_server_status(
                mock_context,
                {},
                config=default_config,
                version_file=version_file,
            )

            # Verify all fields
            assert result["version"] is not None
            assert result["uptime_seconds"] >= 60
            assert result["config_summary"]["security_mode"] == "local"
            assert result["last_update"] is not None
            assert result["last_update"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_handles_corrupt_version_file(
        self, mock_context: ToolContext
    ) -> None:
        """Test that corrupt version file doesn't crash the tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            version_file.write_text("not valid json")

            # Should not raise, just return None for last_update
            result = await handle_manage_get_server_status(
                mock_context, {}, version_file=version_file
            )

            assert result["last_update"] is None
