"""
Tests for the update backend abstraction.

Tests cover:
- PreparedUpdate model
- UpdateBackend interface
- PythonPackageBackend implementation (mocked)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_raspi.errors import InvalidArgumentError, UnavailableError
from mcp_raspi.updates.backends import PreparedUpdate
from mcp_raspi.updates.python_backend import PythonPackageBackend

# =============================================================================
# PreparedUpdate Model Tests
# =============================================================================


class TestPreparedUpdate:
    """Tests for PreparedUpdate model."""

    def test_create_minimal_update(self) -> None:
        """Test creating update with minimal fields."""
        update = PreparedUpdate(target_version="1.0.0")
        assert update.target_version == "1.0.0"
        assert update.channel is None
        assert update.staging_path is None
        assert update.metadata == {}

    def test_create_full_update(self) -> None:
        """Test creating update with all fields."""
        update = PreparedUpdate(
            target_version="1.2.0",
            channel="stable",
            staging_path="/tmp/staging",
            metadata={"package": "mcp-raspi"},
        )
        assert update.target_version == "1.2.0"
        assert update.channel == "stable"
        assert update.staging_path == "/tmp/staging"
        assert update.metadata["package"] == "mcp-raspi"

    def test_model_dump(self) -> None:
        """Test that model dumps to dictionary correctly."""
        update = PreparedUpdate(
            target_version="1.0.0",
            channel="beta",
        )
        data = update.model_dump()
        assert data["target_version"] == "1.0.0"
        assert data["channel"] == "beta"


# =============================================================================
# PythonPackageBackend Tests
# =============================================================================


class TestPythonPackageBackendInit:
    """Tests for PythonPackageBackend initialization."""

    def test_init_with_defaults(self) -> None:
        """Test backend initializes with default values."""
        backend = PythonPackageBackend()
        assert backend.package_name == "mcp-raspi"
        assert backend.staging_dir == Path("/opt/mcp-raspi/staging")
        assert backend.index_url is None
        assert backend.extra_index_url is None

    def test_init_with_custom_values(self) -> None:
        """Test backend initializes with custom values."""
        backend = PythonPackageBackend(
            package_name="custom-package",
            staging_dir="/tmp/staging",
            index_url="https://pypi.org/simple",
            extra_index_url="https://private.pypi.org/simple",
        )
        assert backend.package_name == "custom-package"
        assert backend.staging_dir == Path("/tmp/staging")
        assert backend.index_url == "https://pypi.org/simple"
        assert backend.extra_index_url == "https://private.pypi.org/simple"


class TestPythonPackageBackendVersionKey:
    """Tests for version sorting key."""

    def test_version_key_ordering(self) -> None:
        """Test that version keys sort correctly."""
        backend = PythonPackageBackend()

        # Create version keys
        key_100 = backend._version_key("1.0.0")
        key_110 = backend._version_key("1.1.0")
        key_200 = backend._version_key("2.0.0")
        key_100_beta = backend._version_key("1.0.0-beta")

        # Verify ordering
        assert key_200 > key_110 > key_100
        assert key_100 > key_100_beta  # release > prerelease

    def test_invalid_version_key(self) -> None:
        """Test that invalid versions get low priority."""
        backend = PythonPackageBackend()
        key_invalid = backend._version_key("invalid")
        key_valid = backend._version_key("0.0.1")

        assert key_valid > key_invalid


class TestPythonPackageBackendCheckForUpdates:
    """Tests for check_for_updates method."""

    @pytest.mark.asyncio
    async def test_check_for_updates_returns_version(self) -> None:
        """Test that check_for_updates returns latest version."""
        backend = PythonPackageBackend()

        with patch.object(
            backend, "get_available_versions", new_callable=AsyncMock
        ) as mock_versions:
            mock_versions.return_value = ["1.2.0", "1.1.0", "1.0.0"]

            result = await backend.check_for_updates()

            assert result == "1.2.0"
            mock_versions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_for_updates_returns_none_when_empty(self) -> None:
        """Test that check_for_updates returns None when no versions."""
        backend = PythonPackageBackend()

        with patch.object(
            backend, "get_available_versions", new_callable=AsyncMock
        ) as mock_versions:
            mock_versions.return_value = []

            result = await backend.check_for_updates()

            assert result is None


class TestPythonPackageBackendGetAvailableVersions:
    """Tests for get_available_versions method."""

    @pytest.mark.asyncio
    async def test_get_versions_parses_pip_output(self) -> None:
        """Test parsing pip index versions output."""
        backend = PythonPackageBackend()

        # Mock the command execution
        async def mock_run_command(*_args: str, **_kwargs: int) -> tuple[int, str, str]:
            return (0, "Available versions: 1.2.0, 1.1.0, 1.0.0", "")

        with patch.object(backend, "_run_command", side_effect=mock_run_command):
            versions = await backend.get_available_versions()

            assert "1.2.0" in versions
            assert "1.1.0" in versions
            assert "1.0.0" in versions

    @pytest.mark.asyncio
    async def test_get_versions_filters_stable_channel(self) -> None:
        """Test that stable channel filters out prereleases."""
        backend = PythonPackageBackend()

        async def mock_run_command(*_args: str, **_kwargs: int) -> tuple[int, str, str]:
            return (0, "Available versions: 1.2.0, 1.1.0-beta, 1.0.0", "")

        with patch.object(backend, "_run_command", side_effect=mock_run_command):
            versions = await backend.get_available_versions(channel="stable")

            assert "1.2.0" in versions
            assert "1.0.0" in versions
            assert "1.1.0-beta" not in versions

    @pytest.mark.asyncio
    async def test_get_versions_respects_limit(self) -> None:
        """Test that version list respects limit parameter."""
        backend = PythonPackageBackend()

        async def mock_run_command(*_args: str, **_kwargs: int) -> tuple[int, str, str]:
            return (0, "Available versions: 1.5.0, 1.4.0, 1.3.0, 1.2.0, 1.1.0, 1.0.0", "")

        with patch.object(backend, "_run_command", side_effect=mock_run_command):
            versions = await backend.get_available_versions(limit=3)

            assert len(versions) == 3


class TestPythonPackageBackendPrepare:
    """Tests for prepare method."""

    @pytest.mark.asyncio
    async def test_prepare_with_target_version(self) -> None:
        """Test prepare with explicit target version."""
        backend = PythonPackageBackend()

        with tempfile.TemporaryDirectory() as tmpdir:
            backend.staging_dir = Path(tmpdir)
            # The staging path that the test sets up to simulate what prepare() would create
            staging_path = Path(tmpdir) / "mcp-raspi-1.0.0"

            async def mock_run_with_side_effect(
                *_args: str, **_kwargs: int
            ) -> tuple[int, str, str]:
                # Create fake downloaded file when pip download is called
                # The staging_path is already created by prepare(), we just
                # need to add the "downloaded" file with sufficient size
                staging_path.mkdir(exist_ok=True)
                wheel_file = staging_path / "mcp-raspi-1.0.0-py3-none-any.whl"
                # Create a minimal valid zip file (wheels are zip files)
                import zipfile

                with zipfile.ZipFile(wheel_file, "w") as zf:
                    zf.writestr("dummy.py", "# Dummy content\n" * 100)
                return (0, "Successfully downloaded mcp-raspi-1.0.0.whl", "")

            with patch.object(
                backend, "_run_command", side_effect=mock_run_with_side_effect
            ):
                update = await backend.prepare(target_version="1.0.0")

                assert update.target_version == "1.0.0"
                assert update.staging_path is not None

    @pytest.mark.asyncio
    async def test_prepare_with_channel(self) -> None:
        """Test prepare resolves version from channel."""
        backend = PythonPackageBackend()

        async def mock_check(_channel: str | None = None) -> str:
            return "1.2.0"

        with tempfile.TemporaryDirectory() as tmpdir:
            backend.staging_dir = Path(tmpdir)
            staging_path = Path(tmpdir) / "mcp-raspi-1.2.0"

            async def mock_run_with_side_effect(
                *_args: str, **_kwargs: int
            ) -> tuple[int, str, str]:
                # Create fake downloaded file with sufficient size
                staging_path.mkdir(exist_ok=True)
                wheel_file = staging_path / "mcp-raspi-1.2.0-py3-none-any.whl"
                # Create a minimal valid zip file (wheels are zip files)
                import zipfile

                with zipfile.ZipFile(wheel_file, "w") as zf:
                    zf.writestr("dummy.py", "# Dummy content\n" * 100)
                return (0, "Successfully downloaded mcp-raspi-1.2.0.whl", "")

            with (
                patch.object(backend, "check_for_updates", side_effect=mock_check),
                patch.object(
                    backend, "_run_command", side_effect=mock_run_with_side_effect
                ),
            ):
                update = await backend.prepare(channel="stable")

                assert update.target_version == "1.2.0"
                assert update.channel == "stable"

    @pytest.mark.asyncio
    async def test_prepare_invalid_version_raises_error(self) -> None:
        """Test that invalid version raises InvalidArgumentError."""
        backend = PythonPackageBackend()

        with pytest.raises(InvalidArgumentError):
            await backend.prepare(target_version="invalid-version")

    @pytest.mark.asyncio
    async def test_prepare_no_version_available_raises_error(self) -> None:
        """Test that no available version raises UnavailableError."""
        backend = PythonPackageBackend()

        async def mock_check(_channel: str | None = None) -> None:
            return None

        with (
            patch.object(backend, "check_for_updates", side_effect=mock_check),
            pytest.raises(UnavailableError),
        ):
            await backend.prepare(channel="stable")


class TestPythonPackageBackendApply:
    """Tests for apply method."""

    @pytest.mark.asyncio
    async def test_apply_creates_version_directory(self) -> None:
        """Test that apply creates version directory."""
        backend = PythonPackageBackend()

        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            staging_dir = Path(tmpdir) / "staging" / "mcp-raspi-1.0.0"

            # Create staging with a wheel file
            staging_dir.mkdir(parents=True)
            wheel_file = staging_dir / "mcp_raspi-1.0.0-py3-none-any.whl"
            wheel_file.touch()

            async def mock_run_command(
                *_args: str, **_kwargs: int
            ) -> tuple[int, str, str]:
                # Simulate successful installation
                version_dir = releases_dir / "v1.0.0"
                version_dir.mkdir(parents=True, exist_ok=True)
                (version_dir / "mcp_raspi").mkdir()
                return (0, "Successfully installed", "")

            update = PreparedUpdate(
                target_version="1.0.0",
                staging_path=str(staging_dir),
            )

            with patch.object(backend, "_run_command", side_effect=mock_run_command):
                await backend.apply(update, releases_dir)

                version_dir = releases_dir / "v1.0.0"
                assert version_dir.exists()

    @pytest.mark.asyncio
    async def test_apply_without_staging_path_raises_error(self) -> None:
        """Test that apply without staging path raises error."""
        from mcp_raspi.errors import FailedPreconditionError

        backend = PythonPackageBackend()

        update = PreparedUpdate(
            target_version="1.0.0",
            staging_path=None,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"

            with pytest.raises(FailedPreconditionError):
                await backend.apply(update, releases_dir)


class TestPythonPackageBackendCleanupStaging:
    """Tests for cleanup_staging method."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_staging_directory(self) -> None:
        """Test that cleanup removes staging directory."""
        backend = PythonPackageBackend()

        with tempfile.TemporaryDirectory() as tmpdir:
            staging_path = Path(tmpdir) / "staging"
            staging_path.mkdir()
            (staging_path / "test_file.txt").touch()

            update = PreparedUpdate(
                target_version="1.0.0",
                staging_path=str(staging_path),
            )

            await backend.cleanup_staging(update)

            assert not staging_path.exists()

    @pytest.mark.asyncio
    async def test_cleanup_handles_nonexistent_path(self) -> None:
        """Test that cleanup handles nonexistent path gracefully."""
        backend = PythonPackageBackend()

        update = PreparedUpdate(
            target_version="1.0.0",
            staging_path="/nonexistent/path",
        )

        # Should not raise
        await backend.cleanup_staging(update)

    @pytest.mark.asyncio
    async def test_cleanup_handles_none_staging_path(self) -> None:
        """Test that cleanup handles None staging path."""
        backend = PythonPackageBackend()

        update = PreparedUpdate(
            target_version="1.0.0",
            staging_path=None,
        )

        # Should not raise
        await backend.cleanup_staging(update)


class TestPythonPackageBackendRunCommand:
    """Tests for _run_command helper method."""

    @pytest.mark.asyncio
    async def test_run_command_success(self) -> None:
        """Test successful command execution."""
        backend = PythonPackageBackend()

        returncode, stdout, stderr = await backend._run_command("echo", "hello")

        assert returncode == 0
        assert "hello" in stdout

    @pytest.mark.asyncio
    async def test_run_command_timeout(self) -> None:
        """Test command timeout handling."""
        backend = PythonPackageBackend()

        with pytest.raises(UnavailableError) as exc_info:
            await backend._run_command("sleep", "5", timeout=1.0)

        assert "timed out" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_run_command_not_found(self) -> None:
        """Test handling of command not found."""
        backend = PythonPackageBackend()

        with pytest.raises(UnavailableError):
            await backend._run_command("nonexistent_command_12345")


class TestPythonPackageBackendGetVersionsFromJsonAPI:
    """Tests for _get_versions_from_json_api method."""

    @pytest.mark.asyncio
    async def test_fallback_json_api_import_error(self) -> None:
        """Test fallback when httpx is not available."""
        backend = PythonPackageBackend()

        # Even without httpx mocking, it should return empty list
        # when the actual request fails
        versions = await backend._get_versions_from_json_api()
        # Result depends on whether httpx can reach PyPI
        assert isinstance(versions, list)


class TestPythonPackageBackendGetInstalledVersion:
    """Tests for get_installed_version method."""

    @pytest.mark.asyncio
    async def test_get_installed_version_nonexistent(self) -> None:
        """Test getting version from nonexistent directory."""
        backend = PythonPackageBackend()

        result = await backend.get_installed_version(Path("/nonexistent"))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_installed_version_no_metadata(self) -> None:
        """Test getting version when no dist-info exists."""
        backend = PythonPackageBackend()

        with tempfile.TemporaryDirectory() as tmpdir:
            version_dir = Path(tmpdir) / "v1.0.0"
            version_dir.mkdir()

            result = await backend.get_installed_version(version_dir)

            assert result is not None
            assert result["version"] == "unknown"

    @pytest.mark.asyncio
    async def test_get_installed_version_with_metadata(self) -> None:
        """Test getting version from dist-info metadata."""
        backend = PythonPackageBackend()

        with tempfile.TemporaryDirectory() as tmpdir:
            version_dir = Path(tmpdir) / "v1.0.0"
            version_dir.mkdir()

            # Create dist-info directory
            dist_info = version_dir / "mcp_raspi-1.0.0.dist-info"
            dist_info.mkdir()

            # Create METADATA file
            metadata = dist_info / "METADATA"
            metadata.write_text(
                "Name: mcp-raspi\n"
                "Version: 1.0.0\n"
                "Summary: Test package\n"
            )

            result = await backend.get_installed_version(version_dir)

            assert result is not None
            assert result["name"] == "mcp-raspi"
            assert result["version"] == "1.0.0"


class TestPythonPackageBackendGetPipCommand:
    """Tests for _get_pip_command method."""

    @pytest.mark.asyncio
    async def test_get_pip_command_with_uv(self) -> None:
        """Test pip command when uv is available."""
        backend = PythonPackageBackend()
        backend._use_uv = True

        cmd = await backend._get_pip_command()

        assert cmd == ["uv", "pip"]

    @pytest.mark.asyncio
    async def test_get_pip_command_without_uv(self) -> None:
        """Test pip command when uv is not available."""
        backend = PythonPackageBackend()
        backend._use_uv = False

        cmd = await backend._get_pip_command()

        assert cmd == ["pip"]


class TestUpdateBackendCleanupStaging:
    """Tests for UpdateBackend.cleanup_staging base method."""

    @pytest.mark.asyncio
    async def test_base_cleanup_removes_directory(self) -> None:
        """Test base cleanup_staging removes staging directory."""
        from mcp_raspi.updates.backends import UpdateBackend

        # Create a concrete implementation for testing
        class TestBackend(UpdateBackend):
            async def check_for_updates(
                self, _channel: str | None = None
            ) -> str | None:
                return None

            async def prepare(
                self,
                _channel: str | None = None,
                _target_version: str | None = None,
            ) -> PreparedUpdate:
                return PreparedUpdate(target_version="1.0.0")

            async def apply(self, update: PreparedUpdate, releases_dir: Path) -> None:
                pass

            async def get_available_versions(
                self, _channel: str | None = None, _limit: int = 10
            ) -> list[str]:
                return []

        backend = TestBackend()

        with tempfile.TemporaryDirectory() as tmpdir:
            staging_path = Path(tmpdir) / "staging"
            staging_path.mkdir()
            (staging_path / "test.txt").touch()

            update = PreparedUpdate(
                target_version="1.0.0",
                staging_path=str(staging_path),
            )

            await backend.cleanup_staging(update)

            assert not staging_path.exists()


class TestPythonPackageBackendCheckForUpdatesError:
    """Tests for check_for_updates error handling."""

    @pytest.mark.asyncio
    async def test_check_for_updates_reraises_error(self) -> None:
        """Test that check_for_updates re-raises errors."""
        backend = PythonPackageBackend()

        async def mock_get_versions(*_args, **_kwargs):
            raise UnavailableError("Network error")

        with (
            patch.object(
                backend, "get_available_versions", side_effect=mock_get_versions
            ),
            pytest.raises(UnavailableError),
        ):
            await backend.check_for_updates()
