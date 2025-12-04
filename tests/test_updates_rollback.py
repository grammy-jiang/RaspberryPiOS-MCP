"""
Tests for rollback functionality.

Tests cover:
- perform_rollback function
- get_rollback_target function
- RollbackManager class
- Version manager rollback recording
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_raspi.errors import FailedPreconditionError
from mcp_raspi.updates.rollback import (
    RollbackManager,
    can_rollback,
    get_rollback_target,
    perform_rollback,
)
from mcp_raspi.updates.version import VersionManager

# =============================================================================
# perform_rollback Tests
# =============================================================================


class TestPerformRollback:
    """Tests for perform_rollback function."""

    @pytest.mark.asyncio
    async def test_rollback_switches_symlink(self) -> None:
        """Test that rollback switches the symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            # Create version directories
            v1_dir = releases_dir / "v1.0.0"
            v1_dir.mkdir()
            v2_dir = releases_dir / "v2.0.0"
            v2_dir.mkdir()

            # Current symlink points to v2
            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(v2_dir)

            # Rollback to v1
            await perform_rollback(
                previous_version="1.0.0",
                releases_dir=releases_dir,
                current_symlink=symlink,
            )

            # Verify symlink now points to v1
            assert symlink.resolve() == v1_dir

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_version_raises_error(self) -> None:
        """Test that rollback to nonexistent version raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            symlink = Path(tmpdir) / "current"

            with pytest.raises(FailedPreconditionError) as exc_info:
                await perform_rollback(
                    previous_version="3.0.0",
                    releases_dir=releases_dir,
                    current_symlink=symlink,
                )

            assert "not found" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_rollback_with_version_manager(self) -> None:
        """Test rollback with version manager updates version.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            v1_dir = releases_dir / "v1.0.0"
            v1_dir.mkdir()

            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(v1_dir)

            # Create version manager
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("2.0.0")

            await perform_rollback(
                previous_version="1.0.0",
                releases_dir=releases_dir,
                current_symlink=symlink,
                version_manager=manager,
            )

            # Verify version manager was updated
            assert manager.get_current_version() == "1.0.0"


# =============================================================================
# get_rollback_target Tests
# =============================================================================


class TestGetRollbackTarget:
    """Tests for get_rollback_target function."""

    @pytest.mark.asyncio
    async def test_get_target_from_version_manager(self) -> None:
        """Test getting rollback target from version manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("1.0.0")
            manager.update_version("2.0.0")

            target = await get_rollback_target(version_manager=manager)

            assert target == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_target_from_releases_dir(self) -> None:
        """Test getting rollback target from releases directory."""
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            # Create version directories with explicit mtimes
            # v1 is older, v2 is newer
            v1_dir = releases_dir / "v1.0.0"
            v1_dir.mkdir()
            os.utime(v1_dir, (1000, 1000))

            v2_dir = releases_dir / "v2.0.0"
            v2_dir.mkdir()
            os.utime(v2_dir, (2000, 2000))

            # Create current symlink pointing to v2
            current_symlink = releases_dir.parent / "current"
            current_symlink.symlink_to(v2_dir)

            # Need to mock get_current_version_from_symlink within the operations module
            # which is imported inside get_rollback_target
            with patch(
                "mcp_raspi.updates.operations.get_current_version_from_symlink"
            ) as mock_current:
                mock_current.return_value = "2.0.0"
                target = await get_rollback_target(releases_dir=releases_dir)

                # list_installed_versions sorts by mtime (newest first)
                # So order is: v2.0.0 (mtime 2000), v1.0.0 (mtime 1000)
                # Since current is v2.0.0, it should return v1.0.0
                assert target == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_target_returns_none_when_no_options(self) -> None:
        """Test that get_rollback_target returns None when no options."""
        target = await get_rollback_target()
        assert target is None


# =============================================================================
# can_rollback Tests
# =============================================================================


class TestCanRollback:
    """Tests for can_rollback function."""

    @pytest.mark.asyncio
    async def test_can_rollback_true_when_target_exists(self) -> None:
        """Test can_rollback returns True when target exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("1.0.0")
            manager.update_version("2.0.0")

            result = await can_rollback(version_manager=manager)
            assert result is True

    @pytest.mark.asyncio
    async def test_can_rollback_false_when_no_target(self) -> None:
        """Test can_rollback returns False when no target."""
        result = await can_rollback()
        assert result is False


# =============================================================================
# RollbackManager Tests
# =============================================================================


class TestRollbackManager:
    """Tests for RollbackManager class."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        manager = RollbackManager()
        assert manager._releases_dir == Path("/opt/mcp-raspi/releases")
        assert manager._current_symlink == Path("/opt/mcp-raspi/current")

    def test_init_with_custom_paths(self) -> None:
        """Test initialization with custom paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            symlink = Path(tmpdir) / "current"

            manager = RollbackManager(
                releases_dir=releases_dir,
                current_symlink=symlink,
            )

            assert manager._releases_dir == releases_dir
            assert manager._current_symlink == symlink

    @pytest.mark.asyncio
    async def test_get_current_version(self) -> None:
        """Test getting current version from symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()
            version_dir = releases_dir / "v1.5.0"
            version_dir.mkdir()

            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(version_dir)

            manager = RollbackManager(
                releases_dir=releases_dir,
                current_symlink=symlink,
            )

            result = await manager.get_current_version()
            assert result == "1.5.0"

    @pytest.mark.asyncio
    async def test_get_available_versions(self) -> None:
        """Test getting list of available versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            (releases_dir / "v1.0.0").mkdir()
            (releases_dir / "v1.5.0").mkdir()
            (releases_dir / "v2.0.0").mkdir()

            manager = RollbackManager(releases_dir=releases_dir)

            versions = await manager.get_available_versions()

            assert "1.0.0" in versions
            assert "1.5.0" in versions
            assert "2.0.0" in versions

    @pytest.mark.asyncio
    async def test_rollback_to_previous(self) -> None:
        """Test rollback_to_previous method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            v1_dir = releases_dir / "v1.0.0"
            v1_dir.mkdir()
            v2_dir = releases_dir / "v2.0.0"
            v2_dir.mkdir()

            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(v2_dir)

            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            version_manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            version_manager.create_initial_version("1.0.0")
            version_manager.update_version("2.0.0")

            manager = RollbackManager(
                releases_dir=releases_dir,
                current_symlink=symlink,
                version_manager=version_manager,
            )

            result = await manager.rollback_to_previous()

            assert result == "1.0.0"
            assert symlink.resolve() == v1_dir

    @pytest.mark.asyncio
    async def test_rollback_to_version(self) -> None:
        """Test rollback_to_version method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            v1_dir = releases_dir / "v1.0.0"
            v1_dir.mkdir()
            v2_dir = releases_dir / "v2.0.0"
            v2_dir.mkdir()

            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(v2_dir)

            manager = RollbackManager(
                releases_dir=releases_dir,
                current_symlink=symlink,
            )

            result = await manager.rollback_to_version("1.0.0")

            assert result == "1.0.0"
            assert symlink.resolve() == v1_dir

    @pytest.mark.asyncio
    async def test_rollback_to_unavailable_version_raises_error(self) -> None:
        """Test rollback to unavailable version raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            (releases_dir / "v1.0.0").mkdir()

            symlink = Path(tmpdir) / "current"

            manager = RollbackManager(
                releases_dir=releases_dir,
                current_symlink=symlink,
            )

            with pytest.raises(FailedPreconditionError) as exc_info:
                await manager.rollback_to_version("3.0.0")

            assert "not installed" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_can_rollback_method(self) -> None:
        """Test can_rollback method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            version_manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            version_manager.create_initial_version("1.0.0")
            version_manager.update_version("2.0.0")

            manager = RollbackManager(
                releases_dir=releases_dir,
                version_manager=version_manager,
            )

            result = await manager.can_rollback()
            assert result is True


# =============================================================================
# Version Manager record_rollback Tests
# =============================================================================


class TestVersionManagerRecordRollback:
    """Tests for VersionManager.record_rollback method."""

    def test_record_rollback_updates_current(self) -> None:
        """Test that record_rollback updates current version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("2.0.0")

            manager.record_rollback("1.0.0")

            assert manager.get_current_version() == "1.0.0"

    def test_record_rollback_adds_history(self) -> None:
        """Test that record_rollback adds history entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("2.0.0")

            manager.record_rollback("1.0.0")

            assert len(manager.version_info.history) == 2
            assert manager.version_info.history[0].version == "1.0.0"
            assert manager.version_info.history[0].source == "rollback"
            assert manager.version_info.history[0].updated_from == "2.0.0"

    def test_record_rollback_saves_to_disk(self) -> None:
        """Test that record_rollback saves to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager.create_initial_version("2.0.0")
            manager.record_rollback("1.0.0")

            # Load in new manager
            manager2 = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            manager2.load()

            assert manager2.get_current_version() == "1.0.0"
