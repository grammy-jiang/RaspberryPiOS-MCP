"""
Rollback logic for the Raspberry Pi MCP Server.

This module implements rollback functionality to restore the previous
version when an update fails.

Rollback types:
- Automatic rollback: Triggered when health checks fail repeatedly
- Manual rollback: CLI tool to rollback to previous version

Design follows Doc 10 §5.2-5.3 specifications.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_raspi.errors import FailedPreconditionError, InternalError
from mcp_raspi.logging import get_logger

if TYPE_CHECKING:
    from mcp_raspi.updates.version import VersionManager

logger = get_logger(__name__)


async def perform_rollback(
    previous_version: str,
    releases_dir: Path,
    current_symlink: Path,
    version_manager: VersionManager | None = None,
) -> None:
    """
    Perform a rollback to the previous version.

    This function:
    1. Verifies the previous version directory exists
    2. Atomically switches the symlink to the previous version
    3. Updates version.json to reflect the rollback
    4. Does NOT restart services (caller's responsibility)

    Args:
        previous_version: Version string to rollback to.
        releases_dir: Directory containing version releases.
        current_symlink: Path to the 'current' symlink.
        version_manager: Optional VersionManager to update version.json.

    Raises:
        FailedPreconditionError: If previous version directory doesn't exist.
        InternalError: If rollback operation fails.
    """
    from mcp_raspi.updates.operations import (
        atomic_symlink_switch,
        get_version_directory,
    )

    logger.info(f"Starting rollback to version {previous_version}")

    # Verify previous version exists
    version_dir = get_version_directory(releases_dir, previous_version)
    if version_dir is None:
        # Try constructing the path directly
        version_dir = releases_dir / f"v{previous_version}"
        if not version_dir.exists():
            raise FailedPreconditionError(
                f"Previous version directory not found: {version_dir}",
                details={
                    "previous_version": previous_version,
                    "releases_dir": str(releases_dir),
                },
            )

    try:
        # Switch symlink atomically
        atomic_symlink_switch(version_dir, current_symlink)
        logger.info(f"Symlink switched to {version_dir}")

        # Update version.json if manager provided
        if version_manager:
            try:
                # Load current state
                with contextlib.suppress(Exception):
                    version_manager.load()

                # Record rollback in version manager
                version_manager.record_rollback(previous_version)

            except Exception as e:
                logger.warning(f"Failed to update version.json during rollback: {e}")

        logger.info(f"Rollback to {previous_version} completed successfully")

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise InternalError(
            f"Rollback to {previous_version} failed: {e}",
            details={
                "previous_version": previous_version,
                "version_dir": str(version_dir),
            },
        ) from e


async def get_rollback_target(
    version_manager: VersionManager | None = None,
    releases_dir: Path | None = None,
) -> str | None:
    """
    Get the version to rollback to.

    Priority:
    1. Previous version from version.json
    2. Most recent installed version that isn't current

    Args:
        version_manager: VersionManager to get previous version from.
        releases_dir: Directory to scan for installed versions.

    Returns:
        Version string to rollback to, or None if no rollback target available.
    """
    # Try version.json first
    if version_manager:
        try:
            version_manager.load()
            previous = version_manager.get_previous_version()
            if previous:
                return previous
        except Exception as e:
            logger.debug(f"Could not get previous version from version.json: {e}")

    # Fall back to scanning releases directory
    if releases_dir:
        from mcp_raspi.updates.operations import (
            get_current_version_from_symlink,
            list_installed_versions,
        )

        try:
            current = get_current_version_from_symlink()
            installed = list_installed_versions(releases_dir)

            # Find most recent version that isn't current
            for version in installed:
                if version != current:
                    return version
        except Exception as e:
            logger.debug(f"Could not scan releases directory: {e}")

    return None


async def can_rollback(
    version_manager: VersionManager | None = None,
    releases_dir: Path | None = None,
) -> bool:
    """
    Check if rollback is possible.

    Args:
        version_manager: VersionManager to check.
        releases_dir: Releases directory to scan.

    Returns:
        True if rollback is possible, False otherwise.
    """
    target = await get_rollback_target(version_manager, releases_dir)
    return target is not None


class RollbackManager:
    """
    Manages rollback operations.

    This class provides a higher-level interface for rollback operations,
    including service restart integration.
    """

    DEFAULT_RELEASES_DIR = Path("/opt/mcp-raspi/releases")
    DEFAULT_CURRENT_SYMLINK = Path("/opt/mcp-raspi/current")

    def __init__(
        self,
        releases_dir: Path | str | None = None,
        current_symlink: Path | str | None = None,
        version_manager: VersionManager | None = None,
    ) -> None:
        """
        Initialize the RollbackManager.

        Args:
            releases_dir: Directory containing version releases.
            current_symlink: Path to 'current' symlink.
            version_manager: VersionManager for version.json operations.
        """
        self._releases_dir = (
            Path(releases_dir) if releases_dir else self.DEFAULT_RELEASES_DIR
        )
        self._current_symlink = (
            Path(current_symlink) if current_symlink else self.DEFAULT_CURRENT_SYMLINK
        )
        self._version_manager = version_manager

    @property
    def version_manager(self) -> VersionManager | None:
        """Get the version manager."""
        return self._version_manager

    @version_manager.setter
    def version_manager(self, value: VersionManager) -> None:
        """Set the version manager."""
        self._version_manager = value

    async def get_current_version(self) -> str | None:
        """Get the current running version."""
        from mcp_raspi.updates.operations import get_current_version_from_symlink

        return get_current_version_from_symlink(self._current_symlink)

    async def get_available_versions(self) -> list[str]:
        """Get list of installed versions."""
        from mcp_raspi.updates.operations import list_installed_versions

        return list_installed_versions(self._releases_dir)

    async def get_rollback_target(self) -> str | None:
        """Get the version to rollback to."""
        return await get_rollback_target(self._version_manager, self._releases_dir)

    async def can_rollback(self) -> bool:
        """Check if rollback is possible."""
        return await can_rollback(self._version_manager, self._releases_dir)

    async def rollback_to_previous(self) -> str:
        """
        Rollback to the previous version.

        Returns:
            Version that was rolled back to.

        Raises:
            FailedPreconditionError: If no rollback target available.
        """
        target = await self.get_rollback_target()
        if target is None:
            raise FailedPreconditionError(
                "No previous version available for rollback",
                details={"hint": "No rollback target found in version.json or releases"},
            )

        await perform_rollback(
            previous_version=target,
            releases_dir=self._releases_dir,
            current_symlink=self._current_symlink,
            version_manager=self._version_manager,
        )

        return target

    async def rollback_to_version(self, target_version: str) -> str:
        """
        Rollback to a specific version.

        Args:
            target_version: Version to rollback to.

        Returns:
            Version that was rolled back to.

        Raises:
            FailedPreconditionError: If target version doesn't exist.
        """
        # Verify version is available
        available = await self.get_available_versions()
        if target_version not in available:
            raise FailedPreconditionError(
                f"Version {target_version} is not installed",
                details={
                    "target_version": target_version,
                    "available_versions": available,
                },
        )

        await perform_rollback(
            previous_version=target_version,
            releases_dir=self._releases_dir,
            current_symlink=self._current_symlink,
            version_manager=self._version_manager,
        )

        return target_version
