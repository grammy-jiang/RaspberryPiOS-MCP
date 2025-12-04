"""
Tests for the version management module.

Tests cover:
- Semantic version parsing and validation
- VersionInfo model
- VersionManager load/save operations
- Version history tracking
- Checksum verification
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.updates.version import (
    LastUpdateStatus,
    VersionHistory,
    VersionInfo,
    VersionManager,
    compare_versions,
    parse_semantic_version,
)

# =============================================================================
# Semantic Version Parsing Tests
# =============================================================================


class TestParseSemanticVersion:
    """Tests for parse_semantic_version function."""

    def test_parse_simple_version(self) -> None:
        """Test parsing simple version like 1.0.0."""
        result = parse_semantic_version("1.0.0")
        assert result["major"] == 1
        assert result["minor"] == 0
        assert result["patch"] == 0
        assert result["prerelease"] is None
        assert result["buildmetadata"] is None

    def test_parse_version_with_prerelease(self) -> None:
        """Test parsing version with prerelease identifier."""
        result = parse_semantic_version("1.0.0-beta.1")
        assert result["major"] == 1
        assert result["minor"] == 0
        assert result["patch"] == 0
        assert result["prerelease"] == "beta.1"
        assert result["buildmetadata"] is None

    def test_parse_version_with_build_metadata(self) -> None:
        """Test parsing version with build metadata."""
        result = parse_semantic_version("1.0.0+build.123")
        assert result["major"] == 1
        assert result["minor"] == 0
        assert result["patch"] == 0
        assert result["prerelease"] is None
        assert result["buildmetadata"] == "build.123"

    def test_parse_version_with_prerelease_and_build(self) -> None:
        """Test parsing version with both prerelease and build metadata."""
        result = parse_semantic_version("2.1.3-alpha.2+build.456")
        assert result["major"] == 2
        assert result["minor"] == 1
        assert result["patch"] == 3
        assert result["prerelease"] == "alpha.2"
        assert result["buildmetadata"] == "build.456"

    def test_parse_large_version_numbers(self) -> None:
        """Test parsing large version numbers."""
        result = parse_semantic_version("100.200.300")
        assert result["major"] == 100
        assert result["minor"] == 200
        assert result["patch"] == 300

    def test_reject_empty_string(self) -> None:
        """Test that empty string is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            parse_semantic_version("")
        assert "empty" in exc_info.value.message.lower()

    def test_reject_v_prefix(self) -> None:
        """Test that 'v' prefix is rejected."""
        with pytest.raises(InvalidArgumentError) as exc_info:
            parse_semantic_version("v1.0.0")
        assert "must not start with 'v'" in exc_info.value.message

    def test_reject_incomplete_version(self) -> None:
        """Test that incomplete versions are rejected."""
        with pytest.raises(InvalidArgumentError):
            parse_semantic_version("1.0")

    def test_reject_invalid_format(self) -> None:
        """Test that invalid formats are rejected."""
        invalid_versions = ["latest", "1.0.0.0", "1.a.0", "abc", "1.0.0-", "1.0.0+"]
        for version in invalid_versions:
            with pytest.raises(InvalidArgumentError):
                parse_semantic_version(version)

    def test_accept_zero_versions(self) -> None:
        """Test that versions with zeros are accepted."""
        result = parse_semantic_version("0.0.0")
        assert result["major"] == 0
        assert result["minor"] == 0
        assert result["patch"] == 0


class TestCompareVersions:
    """Tests for compare_versions function."""

    def test_compare_equal_versions(self) -> None:
        """Test comparing equal versions."""
        assert compare_versions("1.0.0", "1.0.0") == 0

    def test_compare_major_difference(self) -> None:
        """Test comparing versions with different major numbers."""
        assert compare_versions("2.0.0", "1.0.0") == 1
        assert compare_versions("1.0.0", "2.0.0") == -1

    def test_compare_minor_difference(self) -> None:
        """Test comparing versions with different minor numbers."""
        assert compare_versions("1.2.0", "1.1.0") == 1
        assert compare_versions("1.1.0", "1.2.0") == -1

    def test_compare_patch_difference(self) -> None:
        """Test comparing versions with different patch numbers."""
        assert compare_versions("1.0.2", "1.0.1") == 1
        assert compare_versions("1.0.1", "1.0.2") == -1

    def test_compare_prerelease_vs_release(self) -> None:
        """Test that release > prerelease."""
        assert compare_versions("1.0.0", "1.0.0-beta") == 1
        assert compare_versions("1.0.0-beta", "1.0.0") == -1

    def test_compare_prerelease_alphabetically(self) -> None:
        """Test comparing prerelease versions."""
        assert compare_versions("1.0.0-beta", "1.0.0-alpha") == 1
        assert compare_versions("1.0.0-alpha", "1.0.0-beta") == -1


# =============================================================================
# VersionHistory Model Tests
# =============================================================================


class TestVersionHistory:
    """Tests for VersionHistory model."""

    def test_create_basic_history(self) -> None:
        """Test creating a basic history entry."""
        history = VersionHistory(
            version="1.0.0",
            installed_at="2025-01-15T10:00:00Z",
        )
        assert history.version == "1.0.0"
        assert history.source == "pypi"
        assert history.status == "active"
        assert history.updated_from is None

    def test_create_history_with_all_fields(self) -> None:
        """Test creating a history entry with all fields."""
        history = VersionHistory(
            version="1.1.0",
            installed_at="2025-01-16T10:00:00Z",
            source="git",
            status="previous_good",
            updated_from="1.0.0",
        )
        assert history.version == "1.1.0"
        assert history.source == "git"
        assert history.status == "previous_good"
        assert history.updated_from == "1.0.0"

    def test_reject_invalid_version(self) -> None:
        """Test that invalid version is rejected."""
        with pytest.raises(InvalidArgumentError):
            VersionHistory(
                version="invalid",
                installed_at="2025-01-15T10:00:00Z",
            )


# =============================================================================
# VersionInfo Model Tests
# =============================================================================


class TestVersionInfo:
    """Tests for VersionInfo model."""

    def test_create_minimal_version_info(self) -> None:
        """Test creating version info with minimal fields."""
        info = VersionInfo(current="1.0.0")
        assert info.current == "1.0.0"
        assert info.previous is None
        assert info.history == []
        assert info.format_version == "1.0"

    def test_create_full_version_info(self) -> None:
        """Test creating version info with all fields."""
        history = [
            VersionHistory(
                version="1.0.0",
                installed_at="2025-01-15T10:00:00Z",
            )
        ]
        info = VersionInfo(
            current="1.0.0",
            previous="0.9.0",
            history=history,
        )
        assert info.current == "1.0.0"
        assert info.previous == "0.9.0"
        assert len(info.history) == 1

    def test_reject_invalid_current_version(self) -> None:
        """Test that invalid current version is rejected."""
        with pytest.raises(InvalidArgumentError):
            VersionInfo(current="invalid")


# =============================================================================
# LastUpdateStatus Model Tests
# =============================================================================


class TestLastUpdateStatus:
    """Tests for LastUpdateStatus model."""

    def test_create_default_status(self) -> None:
        """Test creating status with default values."""
        status = LastUpdateStatus()
        assert status.status == "pending"
        assert status.started_at is None
        assert status.finished_at is None

    def test_create_succeeded_status(self) -> None:
        """Test creating a succeeded status."""
        status = LastUpdateStatus(
            status="succeeded",
            started_at="2025-01-15T10:00:00Z",
            finished_at="2025-01-15T10:01:00Z",
            old_version="0.9.0",
            new_version="1.0.0",
        )
        assert status.status == "succeeded"
        assert status.old_version == "0.9.0"
        assert status.new_version == "1.0.0"

    def test_progress_percentage_bounds(self) -> None:
        """Test that progress percentage is validated."""
        from pydantic import ValidationError

        status = LastUpdateStatus(progress_percent=50.0)
        assert status.progress_percent == 50.0

        # Test bounds validation (Pydantic should enforce ge=0, le=100)
        with pytest.raises(ValidationError):
            LastUpdateStatus(progress_percent=150.0)

        with pytest.raises(ValidationError):
            LastUpdateStatus(progress_percent=-10.0)


# =============================================================================
# VersionManager Tests
# =============================================================================


class TestVersionManager:
    """Tests for VersionManager class."""

    def test_create_manager_with_defaults(self) -> None:
        """Test creating manager with default paths."""
        manager = VersionManager()
        assert manager.version_file == Path("/opt/mcp-raspi/version.json")
        assert manager.backup_file == Path("/opt/mcp-raspi/version.json.backup")

    def test_create_manager_with_custom_paths(self) -> None:
        """Test creating manager with custom paths."""
        manager = VersionManager(
            version_file="/tmp/version.json",
            backup_file="/tmp/version.json.bak",
        )
        assert manager.version_file == Path("/tmp/version.json")
        assert manager.backup_file == Path("/tmp/version.json.bak")

    def test_save_and_load_version_info(self) -> None:
        """Test saving and loading version info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Create initial version
            info = manager.create_initial_version("1.0.0")
            assert info.current == "1.0.0"

            # Create new manager and load
            manager2 = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            loaded = manager2.load()

            assert loaded.current == "1.0.0"
            assert len(loaded.history) == 1
            assert loaded.history[0].version == "1.0.0"

    def test_update_version_tracks_history(self) -> None:
        """Test that update_version properly tracks history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Create initial version
            manager.create_initial_version("1.0.0")

            # Update to new version
            manager.update_version("1.1.0", source="pypi")

            assert manager.get_current_version() == "1.1.0"
            assert manager.get_previous_version() == "1.0.0"
            assert len(manager.version_info.history) == 2

            # Most recent entry should be 1.1.0
            assert manager.version_info.history[0].version == "1.1.0"
            assert manager.version_info.history[0].updated_from == "1.0.0"

    def test_checksum_verification(self) -> None:
        """Test that checksum verification works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Create and save
            manager.create_initial_version("1.0.0")

            # Read file directly and verify checksum exists
            with open(version_file) as f:
                data = json.load(f)

            assert "checksum" in data
            assert data["checksum"].startswith("sha256:")

            # Tamper with file
            data["current"] = "2.0.0"  # Tamper without updating checksum
            with open(version_file, "w") as f:
                json.dump(data, f)

            # Loading should fail due to checksum mismatch
            manager2 = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Should recover from backup
            loaded = manager2.load()
            assert loaded.current == "1.0.0"  # Original value from backup

    def test_recovery_from_backup(self) -> None:
        """Test that manager recovers from backup when primary is corrupted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Create initial version
            manager.create_initial_version("1.0.0")

            # Corrupt primary file
            with open(version_file, "w") as f:
                f.write("not valid json")

            # Load should recover from backup
            manager2 = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            loaded = manager2.load()
            assert loaded.current == "1.0.0"

    def test_load_nonexistent_file_raises_error(self) -> None:
        """Test that loading from nonexistent files raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "nonexistent.json"
            backup_file = Path(tmpdir) / "nonexistent.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            with pytest.raises(RuntimeError) as exc_info:
                manager.load()
            assert "Cannot load version.json" in str(exc_info.value)

    def test_history_limited_to_10_entries(self) -> None:
        """Test that history is limited to 10 entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Create initial version
            manager.create_initial_version("1.0.0")

            # Perform 12 updates
            for i in range(1, 13):
                manager.update_version(f"1.0.{i}", save=True)

            # History should be limited to 10
            assert len(manager.version_info.history) == 10

            # Most recent should be at the front
            assert manager.version_info.history[0].version == "1.0.12"

    def test_to_dict_returns_correct_format(self) -> None:
        """Test that to_dict returns correct dictionary format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            manager.create_initial_version("1.0.0")
            result = manager.to_dict()

            assert result["current"] == "1.0.0"
            assert "history" in result
            assert isinstance(result["history"], list)

    def test_atomic_save(self) -> None:
        """Test that save uses atomic write pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            manager.create_initial_version("1.0.0")

            # Both primary and backup should exist
            assert version_file.exists()
            assert backup_file.exists()

            # No temp files should remain
            temp_files = list(Path(tmpdir).glob(".tmp*"))
            assert len(temp_files) == 0


class TestVersionManagerSaveNoInfo:
    """Test edge cases for VersionManager.save()."""

    def test_save_without_loading_raises_error(self) -> None:
        """Test that save without loading raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Trying to save without loading/creating should raise
            with pytest.raises(ValueError):
                manager.save()


class TestVersionManagerUpdateWithoutLoad:
    """Test update_version without loading."""

    def test_update_version_without_load_raises_error(self) -> None:
        """Test that update_version without loading raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"

            manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )

            # Trying to update without loading should raise
            with pytest.raises(RuntimeError):
                manager.update_version("1.0.0")


class TestVersionInfoProperties:
    """Test VersionInfo property access."""

    def test_get_current_version_not_loaded(self) -> None:
        """Test get_current_version when nothing loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(
                version_file=Path(tmpdir) / "version.json",
                backup_file=Path(tmpdir) / "version.json.backup",
            )

            assert manager.get_current_version() is None

    def test_get_previous_version_not_loaded(self) -> None:
        """Test get_previous_version when nothing loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(
                version_file=Path(tmpdir) / "version.json",
                backup_file=Path(tmpdir) / "version.json.backup",
            )

            assert manager.get_previous_version() is None

    def test_to_dict_not_loaded(self) -> None:
        """Test to_dict when nothing loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = VersionManager(
                version_file=Path(tmpdir) / "version.json",
                backup_file=Path(tmpdir) / "version.json.backup",
            )

            assert manager.to_dict() == {}
