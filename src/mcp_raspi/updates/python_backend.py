"""
Python package update backend for the Raspberry Pi MCP Server.

This module implements the PythonPackageBackend for updating the MCP server
via Python package managers (uv/pip).

Design follows Doc 10 §3.4.2 specifications.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_raspi.errors import (
    FailedPreconditionError,
    InternalError,
    InvalidArgumentError,
    UnavailableError,
)
from mcp_raspi.logging import get_logger
from mcp_raspi.updates.backends import PreparedUpdate, UpdateBackend
from mcp_raspi.updates.operations import create_version_directory, ensure_directory
from mcp_raspi.updates.version import parse_semantic_version

# Optional httpx dependency for PyPI JSON API fallback
try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    if TYPE_CHECKING:
        import httpx

logger = get_logger(__name__)

# Default package name
DEFAULT_PACKAGE_NAME = "mcp-raspi"

# Default staging directory
DEFAULT_STAGING_DIR = Path("/opt/mcp-raspi/staging")


class PythonPackageBackend(UpdateBackend):
    """
    Update backend for Python package-based updates.

    This backend uses uv (preferred) or pip to download and install
    new versions of the MCP server package.

    The update flow:
    1. check_for_updates: Query PyPI for latest version
    2. prepare: Download package to staging directory
    3. apply: Move staged package to releases directory

    Attributes:
        package_name: Name of the Python package.
        staging_dir: Directory for staging downloads.
        index_url: Optional custom PyPI index URL.
        extra_index_url: Optional extra PyPI index URL.
    """

    def __init__(
        self,
        package_name: str = DEFAULT_PACKAGE_NAME,
        staging_dir: Path | str | None = None,
        index_url: str | None = None,
        extra_index_url: str | None = None,
    ) -> None:
        """
        Initialize the PythonPackageBackend.

        Args:
            package_name: Name of the Python package to manage.
            staging_dir: Directory for staging downloads.
            index_url: Optional custom PyPI index URL.
            extra_index_url: Optional extra PyPI index URL.
        """
        self.package_name = package_name
        self.staging_dir = Path(staging_dir) if staging_dir else DEFAULT_STAGING_DIR
        self.index_url = index_url
        self.extra_index_url = extra_index_url
        self._use_uv = self._check_uv_available()

    def _check_uv_available(self) -> bool:
        """Check if uv is available on the system."""
        return shutil.which("uv") is not None

    async def _run_command(
        self,
        *args: str,
        timeout: float = 300.0,
    ) -> tuple[int, str, str]:
        """
        Run a subprocess command asynchronously.

        Args:
            *args: Command and arguments.
            timeout: Command timeout in seconds.

        Returns:
            Tuple of (return_code, stdout, stderr).

        Raises:
            UnavailableError: If command times out or fails to execute.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            return (
                process.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except TimeoutError as e:
            raise UnavailableError(
                f"Command timed out after {timeout}s",
                details={"command": " ".join(args)},
            ) from e
        except OSError as e:
            raise UnavailableError(
                f"Failed to execute command: {e}",
                details={"command": " ".join(args), "error": str(e)},
            ) from e

    async def _get_pip_command(self) -> list[str]:
        """Get the pip command (uv pip or pip)."""
        if self._use_uv:
            return ["uv", "pip"]
        return ["pip"]

    async def check_for_updates(self, channel: str | None = None) -> str | None:
        """
        Check PyPI for available updates.

        Args:
            channel: Update channel (not used for PyPI, included for interface).

        Returns:
            Latest available version string, or None if no update available.

        Raises:
            UnavailableError: If PyPI is unreachable.
        """
        try:
            versions = await self.get_available_versions(channel, limit=1)
            if versions:
                return versions[0]
            return None
        except Exception as e:
            logger.warning(
                "Failed to check for updates",
                extra={"error": str(e)},
            )
            raise

    async def get_available_versions(
        self,
        channel: str | None = None,
        limit: int = 10,
    ) -> list[str]:
        """
        Get list of available versions from PyPI.

        Args:
            channel: Update channel (filters pre-releases if "stable").
            limit: Maximum number of versions to return.

        Returns:
            List of available version strings, newest first.

        Raises:
            UnavailableError: If PyPI is unreachable.
        """
        # Use pip index versions command
        pip_cmd = await self._get_pip_command()

        args = [*pip_cmd, "index", "versions", self.package_name]

        if self.index_url:
            args.extend(["--index-url", self.index_url])
        if self.extra_index_url:
            args.extend(["--extra-index-url", self.extra_index_url])

        returncode, stdout, stderr = await self._run_command(*args)

        if returncode != 0:
            # Try alternative method with pip show
            return await self._get_versions_from_json_api()

        # Parse output like: "mcp-raspi (1.0.0)"
        # or "Available versions: 1.0.0, 0.9.0, ..."
        versions = []
        for line in stdout.splitlines():
            line = line.strip()
            if "Available versions:" in line:
                # Format: "Available versions: 1.0.0, 0.9.0, ..."
                version_part = line.split(":", 1)[1].strip()
                versions.extend(v.strip() for v in version_part.split(","))
            elif line.startswith(self.package_name):
                # Format: "mcp-raspi (1.0.0)"
                if "(" in line and ")" in line:
                    version = line.split("(")[1].split(")")[0].strip()
                    versions.append(version)

        # Filter by channel
        if channel == "stable":
            versions = [v for v in versions if "-" not in v]

        # Validate and sort versions
        valid_versions = []
        for v in versions:
            try:
                parse_semantic_version(v)
                valid_versions.append(v)
            except InvalidArgumentError:
                continue

        # Sort newest first
        valid_versions.sort(key=lambda v: self._version_key(v), reverse=True)

        return valid_versions[:limit]

    async def _get_versions_from_json_api(self) -> list[str]:
        """
        Get versions using PyPI JSON API as fallback.

        Returns:
            List of available version strings.
        """
        if not _HTTPX_AVAILABLE:
            return []

        try:
            async with httpx.AsyncClient() as client:
                url = f"https://pypi.org/pypi/{self.package_name}/json"
                response = await client.get(url, timeout=30.0)
                if response.status_code == 200:
                    data = response.json()
                    releases = list(data.get("releases", {}).keys())
                    # Filter valid semver versions
                    valid_versions = []
                    for v in releases:
                        try:
                            parse_semantic_version(v)
                            valid_versions.append(v)
                        except InvalidArgumentError:
                            continue
                    valid_versions.sort(
                        key=lambda v: self._version_key(v), reverse=True
                    )
                    return valid_versions
        except Exception as e:
            logger.debug(f"PyPI JSON API fallback failed: {e}")

        return []

    def _version_key(self, version: str) -> tuple[int, int, int, str]:
        """Create a sort key for a version string."""
        try:
            parsed = parse_semantic_version(version)
            prerelease = parsed.get("prerelease") or "~"  # ~ sorts after all letters
            return (parsed["major"], parsed["minor"], parsed["patch"], prerelease)
        except InvalidArgumentError:
            return (0, 0, 0, version)

    async def prepare(
        self,
        channel: str | None = None,
        target_version: str | None = None,
    ) -> PreparedUpdate:
        """
        Prepare an update by downloading the package.

        Args:
            channel: Update channel (e.g., "stable", "beta").
            target_version: Specific version to update to.

        Returns:
            PreparedUpdate with staging information.

        Raises:
            InvalidArgumentError: If version is invalid.
            UnavailableError: If package cannot be downloaded.
            FailedPreconditionError: If disk space is insufficient.
        """
        # Resolve target version
        if target_version:
            # Validate the version
            parse_semantic_version(target_version)
            version = target_version
        else:
            # Get latest version for channel
            version = await self.check_for_updates(channel)
            if not version:
                raise UnavailableError(
                    f"No version available for channel: {channel or 'default'}",
                    details={"package": self.package_name, "channel": channel},
                )

        logger.info(
            "Preparing update",
            extra={
                "package": self.package_name,
                "version": version,
                "channel": channel,
            },
        )

        # Create staging directory
        staging_path = self.staging_dir / f"{self.package_name}-{version}"
        ensure_directory(staging_path)

        # Download package to staging
        pip_cmd = await self._get_pip_command()

        args = [
            *pip_cmd,
            "download",
            f"{self.package_name}=={version}",
            "--dest",
            str(staging_path),
            "--no-deps",  # We'll handle dependencies separately
        ]

        if self.index_url:
            args.extend(["--index-url", self.index_url])
        if self.extra_index_url:
            args.extend(["--extra-index-url", self.extra_index_url])

        returncode, stdout, stderr = await self._run_command(*args, timeout=300.0)

        if returncode != 0:
            raise UnavailableError(
                f"Failed to download package: {stderr}",
                details={
                    "package": self.package_name,
                    "version": version,
                    "stderr": stderr,
                },
            )

        # Find downloaded file
        downloaded_files = list(staging_path.glob(f"{self.package_name}*"))
        if not downloaded_files:
            raise InternalError(
                "Package download succeeded but no files found",
                details={"staging_path": str(staging_path)},
            )

        logger.info(
            "Update prepared successfully",
            extra={
                "version": version,
                "staging_path": str(staging_path),
                "files": [f.name for f in downloaded_files],
            },
        )

        return PreparedUpdate(
            target_version=version,
            channel=channel,
            staging_path=str(staging_path),
            metadata={
                "package_name": self.package_name,
                "downloaded_files": [f.name for f in downloaded_files],
            },
        )

    async def apply(self, update: PreparedUpdate, releases_dir: Path) -> None:
        """
        Apply a prepared update to the releases directory.

        Args:
            update: PreparedUpdate from prepare().
            releases_dir: Directory containing version releases.

        Raises:
            FailedPreconditionError: If staging path doesn't exist.
            InternalError: If installation fails.
        """
        if not update.staging_path:
            raise FailedPreconditionError(
                "No staging path in prepared update",
                details={"update": update.model_dump()},
            )

        staging_path = Path(update.staging_path)
        if not staging_path.exists():
            raise FailedPreconditionError(
                f"Staging path does not exist: {staging_path}",
                details={"staging_path": str(staging_path)},
            )

        # Create version directory
        version_dir = create_version_directory(releases_dir, update.target_version)

        logger.info(
            "Applying update",
            extra={
                "version": update.target_version,
                "version_dir": str(version_dir),
            },
        )

        # Install package to version directory using pip install --target
        pip_cmd = await self._get_pip_command()

        # Find wheel or sdist in staging
        staged_files = list(staging_path.glob("*.whl")) or list(
            staging_path.glob("*.tar.gz")
        )
        if not staged_files:
            raise InternalError(
                "No installable package found in staging",
                details={"staging_path": str(staging_path)},
            )

        package_file = staged_files[0]

        # Create a virtual environment or install to target
        args = [
            *pip_cmd,
            "install",
            str(package_file),
            "--target",
            str(version_dir),
            "--no-deps",
        ]

        returncode, stdout, stderr = await self._run_command(*args, timeout=300.0)

        if returncode != 0:
            # Clean up partial installation
            shutil.rmtree(version_dir, ignore_errors=True)
            raise InternalError(
                f"Failed to install package: {stderr}",
                details={
                    "version": update.target_version,
                    "stderr": stderr,
                },
            )

        # Verify installation
        if not any(version_dir.iterdir()):
            raise InternalError(
                "Installation completed but version directory is empty",
                details={"version_dir": str(version_dir)},
            )

        logger.info(
            "Update applied successfully",
            extra={
                "version": update.target_version,
                "version_dir": str(version_dir),
            },
        )

    async def cleanup_staging(self, update: PreparedUpdate) -> None:
        """
        Clean up staging area after update.

        Args:
            update: PreparedUpdate to clean up.
        """
        if update.staging_path:
            staging_path = Path(update.staging_path)
            if staging_path.exists():
                shutil.rmtree(staging_path, ignore_errors=True)
                logger.debug(
                    "Cleaned up staging",
                    extra={"staging_path": str(staging_path)},
                )

    async def get_installed_version(
        self,
        version_dir: Path,
    ) -> dict[str, Any] | None:
        """
        Get information about an installed version.

        Args:
            version_dir: Path to the version directory.

        Returns:
            Dictionary with version info, or None if not installed.
        """
        if not version_dir.exists():
            return None

        # Look for package metadata
        dist_info_dirs = list(version_dir.glob("*.dist-info"))
        if dist_info_dirs:
            metadata_file = dist_info_dirs[0] / "METADATA"
            if metadata_file.exists():
                metadata = {}
                current_key = None
                for line in metadata_file.read_text().splitlines():
                    if ": " in line and not line.startswith(" "):
                        key, value = line.split(": ", 1)
                        metadata[key.lower()] = value
                        current_key = key.lower()
                    elif current_key and line.startswith(" "):
                        metadata[current_key] += "\n" + line.strip()

                return {
                    "name": metadata.get("name", self.package_name),
                    "version": metadata.get("version", "unknown"),
                    "summary": metadata.get("summary", ""),
                    "path": str(version_dir),
                }

        return {"path": str(version_dir), "version": "unknown"}
