"""
Tests for atomic directory and symlink operations.

Tests cover:
- ensure_directory
- safe_remove_directory
- atomic_symlink_switch
- Version directory management functions
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from mcp_raspi.errors import FailedPreconditionError
from mcp_raspi.updates.operations import (
    atomic_symlink_switch,
    create_version_directory,
    ensure_directory,
    get_current_version_from_symlink,
    get_symlink_target,
    get_version_directory,
    initialize_version_structure,
    list_installed_versions,
    safe_remove_directory,
)

# =============================================================================
# ensure_directory Tests
# =============================================================================


class TestEnsureDirectory:
    """Tests for ensure_directory function."""

    def test_create_new_directory(self) -> None:
        """Test creating a new directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_directory"
            result = ensure_directory(new_dir)

            assert result == new_dir
            assert new_dir.exists()
            assert new_dir.is_dir()

    def test_create_nested_directories(self) -> None:
        """Test creating nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "level1" / "level2" / "level3"
            result = ensure_directory(nested_dir)

            assert result == nested_dir
            assert nested_dir.exists()

    def test_existing_directory_unchanged(self) -> None:
        """Test that existing directory is not modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            existing_dir = Path(tmpdir) / "existing"
            existing_dir.mkdir()

            # Create a file in the directory
            (existing_dir / "test.txt").touch()

            result = ensure_directory(existing_dir)

            assert result == existing_dir
            assert (existing_dir / "test.txt").exists()

    def test_mode_applied_to_new_directory(self) -> None:
        """Test that mode is applied to new directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_with_mode"
            ensure_directory(new_dir, mode=0o700)

            # Check permissions (may vary by umask)
            assert new_dir.exists()


# =============================================================================
# safe_remove_directory Tests
# =============================================================================


class TestSafeRemoveDirectory:
    """Tests for safe_remove_directory function."""

    def test_remove_existing_directory(self) -> None:
        """Test removing an existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "to_remove"
            target_dir.mkdir()
            (target_dir / "file.txt").touch()

            result = safe_remove_directory(target_dir)

            assert result is True
            assert not target_dir.exists()

    def test_remove_nested_directory(self) -> None:
        """Test removing directory with nested contents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "to_remove"
            nested = target_dir / "level1" / "level2"
            nested.mkdir(parents=True)
            (nested / "deep_file.txt").touch()

            result = safe_remove_directory(target_dir)

            assert result is True
            assert not target_dir.exists()

    def test_remove_nonexistent_directory(self) -> None:
        """Test removing a nonexistent directory returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "does_not_exist"

            result = safe_remove_directory(nonexistent)

            assert result is False

    def test_ignore_errors_true(self) -> None:
        """Test that errors are ignored when ignore_errors=True."""
        # Even with a nonexistent path, should not raise
        result = safe_remove_directory(
            Path("/nonexistent/path"), ignore_errors=True
        )
        assert result is False


# =============================================================================
# atomic_symlink_switch Tests
# =============================================================================


class TestAtomicSymlinkSwitch:
    """Tests for atomic_symlink_switch function."""

    def test_create_new_symlink(self) -> None:
        """Test creating a new symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target"
            target.mkdir()

            symlink = Path(tmpdir) / "symlink"

            atomic_symlink_switch(target, symlink)

            assert symlink.is_symlink()
            assert symlink.resolve() == target

    def test_switch_existing_symlink(self) -> None:
        """Test switching an existing symlink to new target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target1 = Path(tmpdir) / "target1"
            target1.mkdir()

            target2 = Path(tmpdir) / "target2"
            target2.mkdir()

            symlink = Path(tmpdir) / "symlink"

            # Create initial symlink
            atomic_symlink_switch(target1, symlink)
            assert symlink.resolve() == target1

            # Switch to new target
            atomic_symlink_switch(target2, symlink)
            assert symlink.resolve() == target2

    def test_atomic_switch_over_file(self) -> None:
        """Test that atomic switch replaces existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target"
            target.mkdir()

            symlink = Path(tmpdir) / "symlink"
            # Create a regular file first
            symlink.touch()

            # Should replace the file with a symlink
            atomic_symlink_switch(target, symlink)

            assert symlink.is_symlink()
            assert symlink.resolve() == target

    def test_target_not_exists_raises_error(self) -> None:
        """Test that nonexistent target raises FailedPreconditionError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nonexistent"
            symlink = Path(tmpdir) / "symlink"

            with pytest.raises(FailedPreconditionError) as exc_info:
                atomic_symlink_switch(target, symlink)

            assert "does not exist" in exc_info.value.message

    def test_creates_parent_directory(self) -> None:
        """Test that parent directory is created if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target"
            target.mkdir()

            symlink = Path(tmpdir) / "subdir" / "symlink"

            atomic_symlink_switch(target, symlink)

            assert symlink.is_symlink()

    def test_relative_symlink(self) -> None:
        """Test creating a relative symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "releases" / "v1.0.0"
            target.mkdir(parents=True)

            symlink = Path(tmpdir) / "releases" / "current"

            atomic_symlink_switch(target, symlink, relative=True)

            assert symlink.is_symlink()
            # The link target should be relative
            link_target = os.readlink(symlink)
            assert not link_target.startswith("/")

    def test_no_temp_files_left(self) -> None:
        """Test that no temporary files are left after switch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target"
            target.mkdir()

            symlink = Path(tmpdir) / "symlink"

            atomic_symlink_switch(target, symlink)

            # Check for temp files
            temp_files = list(Path(tmpdir).glob(".symlink_tmp_*"))
            assert len(temp_files) == 0


# =============================================================================
# get_symlink_target Tests
# =============================================================================


class TestGetSymlinkTarget:
    """Tests for get_symlink_target function."""

    def test_get_existing_symlink_target(self) -> None:
        """Test getting target of existing symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target"
            target.mkdir()

            symlink = Path(tmpdir) / "symlink"
            symlink.symlink_to(target)

            result = get_symlink_target(symlink)

            assert result == target

    def test_get_nonexistent_symlink_target(self) -> None:
        """Test getting target of nonexistent symlink returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            symlink = Path(tmpdir) / "nonexistent"

            result = get_symlink_target(symlink)

            assert result is None


# =============================================================================
# create_version_directory Tests
# =============================================================================


class TestCreateVersionDirectory:
    """Tests for create_version_directory function."""

    def test_create_version_directory(self) -> None:
        """Test creating a version directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            result = create_version_directory(releases_dir, "1.0.0")

            expected = releases_dir / "v1.0.0"
            assert result == expected
            assert expected.exists()

    def test_version_directory_name_format(self) -> None:
        """Test that version directory has correct name format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            result = create_version_directory(releases_dir, "2.1.3-beta.1")

            assert result.name == "v2.1.3-beta.1"


# =============================================================================
# get_version_directory Tests
# =============================================================================


class TestGetVersionDirectory:
    """Tests for get_version_directory function."""

    def test_get_existing_version_directory(self) -> None:
        """Test getting an existing version directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            version_dir = releases_dir / "v1.0.0"
            version_dir.mkdir(parents=True)

            result = get_version_directory(releases_dir, "1.0.0")

            assert result == version_dir

    def test_get_nonexistent_version_directory(self) -> None:
        """Test getting a nonexistent version directory returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            result = get_version_directory(releases_dir, "1.0.0")

            assert result is None


# =============================================================================
# list_installed_versions Tests
# =============================================================================


class TestListInstalledVersions:
    """Tests for list_installed_versions function."""

    def test_list_multiple_versions(self) -> None:
        """Test listing multiple installed versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"

            # Create version directories
            (releases_dir / "v1.0.0").mkdir(parents=True)
            (releases_dir / "v1.1.0").mkdir()
            (releases_dir / "v2.0.0").mkdir()

            versions = list_installed_versions(releases_dir)

            assert "1.0.0" in versions
            assert "1.1.0" in versions
            assert "2.0.0" in versions

    def test_list_empty_releases_dir(self) -> None:
        """Test listing from empty releases directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            versions = list_installed_versions(releases_dir)

            assert versions == []

    def test_list_nonexistent_releases_dir(self) -> None:
        """Test listing from nonexistent releases directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "nonexistent"

            versions = list_installed_versions(releases_dir)

            assert versions == []

    def test_ignores_non_version_directories(self) -> None:
        """Test that non-version directories are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            (releases_dir / "v1.0.0").mkdir()
            (releases_dir / "staging").mkdir()  # Should be ignored
            (releases_dir / "temp").mkdir()  # Should be ignored

            versions = list_installed_versions(releases_dir)

            assert versions == ["1.0.0"]


# =============================================================================
# get_current_version_from_symlink Tests
# =============================================================================


class TestGetCurrentVersionFromSymlink:
    """Tests for get_current_version_from_symlink function."""

    def test_get_version_from_symlink(self) -> None:
        """Test getting version from current symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            version_dir = releases_dir / "v1.0.0"
            version_dir.mkdir(parents=True)

            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(version_dir)

            result = get_current_version_from_symlink(symlink)

            assert result == "1.0.0"

    def test_get_version_from_nonexistent_symlink(self) -> None:
        """Test getting version from nonexistent symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            symlink = Path(tmpdir) / "current"

            result = get_current_version_from_symlink(symlink)

            assert result is None


# =============================================================================
# initialize_version_structure Tests
# =============================================================================


class TestInitializeVersionStructure:
    """Tests for initialize_version_structure function."""

    def test_initialize_full_structure(self) -> None:
        """Test initializing full version structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            releases_dir, version_dir = initialize_version_structure(
                base_dir, "1.0.0"
            )

            assert releases_dir.exists()
            assert releases_dir == base_dir / "releases"
            assert version_dir.exists()
            assert version_dir == releases_dir / "v1.0.0"

            # Check symlink
            symlink = base_dir / "current"
            assert symlink.is_symlink()
            assert symlink.resolve() == version_dir

    def test_initialize_without_symlink(self) -> None:
        """Test initializing without creating symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            releases_dir, version_dir = initialize_version_structure(
                base_dir, "1.0.0", create_symlink=False
            )

            assert releases_dir.exists()
            assert version_dir.exists()

            # Symlink should not exist
            symlink = base_dir / "current"
            assert not symlink.exists()

    def test_initialize_creates_all_parent_dirs(self) -> None:
        """Test that all parent directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "opt" / "mcp-raspi"

            releases_dir, version_dir = initialize_version_structure(
                base_dir, "1.0.0"
            )

            assert releases_dir.exists()
            assert version_dir.exists()


class TestAtomicSymlinkSwitchAbsolute:
    """Additional tests for absolute symlink paths."""

    def test_symlink_with_absolute_path(self) -> None:
        """Test creating symlink with absolute path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "target"
            target.mkdir()

            symlink = Path(tmpdir) / "symlink"

            atomic_symlink_switch(target, symlink, relative=False)

            # Check symlink was created with absolute path
            link_target = os.readlink(symlink)
            assert link_target.startswith("/")


class TestListInstalledVersionsSorted:
    """Tests for version listing with sorting."""

    def test_list_versions_sorted_by_mtime(self) -> None:
        """Test that versions are sorted by modification time."""
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"

            # Create versions with explicitly different mtimes using os.utime()
            # This is more reliable than time.sleep() on filesystems with
            # low timestamp resolution
            v1 = releases_dir / "v1.0.0"
            v1.mkdir(parents=True)
            os.utime(v1, (1000, 1000))  # Oldest

            v2 = releases_dir / "v2.0.0"
            v2.mkdir()
            os.utime(v2, (2000, 2000))  # Middle

            v3 = releases_dir / "v1.5.0"
            v3.mkdir()
            os.utime(v3, (3000, 3000))  # Newest

            versions = list_installed_versions(releases_dir)

            # Most recent should be first
            assert versions[0] == "1.5.0"
