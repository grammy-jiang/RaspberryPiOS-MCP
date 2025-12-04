"""
Update backend abstraction for the Raspberry Pi MCP Server.

This module defines the UpdateBackend abstract base class and PreparedUpdate
model that all update backends must implement.

Design follows Doc 10 §3.4 specifications.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PreparedUpdate(BaseModel):
    """
    Represents a prepared update ready to be applied.

    This model is returned by UpdateBackend.prepare() and passed to
    UpdateBackend.apply() to complete the update process.

    Attributes:
        target_version: The version to update to.
        channel: Update channel (e.g., "stable", "beta").
        staging_path: Path to staged update files.
        metadata: Additional backend-specific metadata.
    """

    target_version: str = Field(
        ...,
        description="Target version to update to",
    )
    channel: str | None = Field(
        default=None,
        description="Update channel (e.g., 'stable', 'beta')",
    )
    staging_path: str | None = Field(
        default=None,
        description="Path to staged update files",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional backend-specific metadata",
    )


class UpdateBackend(ABC):
    """
    Abstract base class for update backends.

    Update backends are responsible for:
    - Checking for available updates
    - Downloading and staging new versions
    - Preparing the update for application

    Concrete implementations include:
    - PythonPackageBackend: Updates via PyPI/uv/pip
    - GitBackend: Updates via git (Phase 2+)
    - ArchiveBackend: Updates via tarball download (Phase 2+)
    - AptBackend: Updates via APT (Phase 2+)

    The backend abstraction separates "how to obtain the update" from
    "how to apply it" and state machine orchestration.
    """

    @abstractmethod
    async def check_for_updates(self, channel: str | None = None) -> str | None:
        """
        Check if a new version is available.

        Args:
            channel: Update channel to check (e.g., "stable", "beta").
                    If None, uses the backend's default channel.

        Returns:
            Latest available version string, or None if no update available.

        Raises:
            UnavailableError: If update source is unreachable.
            FailedPreconditionError: If preconditions not met (e.g., network issues).
        """
        pass

    @abstractmethod
    async def prepare(
        self,
        channel: str | None = None,
        target_version: str | None = None,
    ) -> PreparedUpdate:
        """
        Prepare an update for installation.

        This method:
        1. Resolves the target version (from channel or explicit version)
        2. Downloads the update package
        3. Stages the update in a temporary location
        4. Verifies integrity (checksums, signatures if configured)

        Args:
            channel: Update channel (e.g., "stable", "beta").
            target_version: Specific version to update to. If provided,
                          takes precedence over channel resolution.

        Returns:
            PreparedUpdate with staging information.

        Raises:
            InvalidArgumentError: If version is invalid.
            UnavailableError: If update source is unreachable.
            FailedPreconditionError: If disk space is insufficient or
                                     other preconditions not met.
            ResourceExhaustedError: If disk space is insufficient.
        """
        pass

    @abstractmethod
    async def apply(self, update: PreparedUpdate, releases_dir: Path) -> None:
        """
        Apply a prepared update.

        This method:
        1. Moves staged files to the releases directory
        2. Ensures the new version is ready for activation
        3. Does NOT switch symlinks or restart services

        The caller (UpdateService) is responsible for:
        - Switching the current symlink
        - Updating version.json
        - Restarting services

        Args:
            update: PreparedUpdate from prepare().
            releases_dir: Directory containing version releases.

        Raises:
            FailedPreconditionError: If the update cannot be applied.
            InternalError: If an unexpected error occurs.
        """
        pass

    async def cleanup_staging(self, update: PreparedUpdate) -> None:
        """
        Clean up staging area after update.

        This method removes temporary staging files. It should be called
        after both successful and failed updates to free disk space.

        Args:
            update: PreparedUpdate to clean up.
        """
        if update.staging_path:
            staging_path = Path(update.staging_path)
            if staging_path.exists():
                shutil.rmtree(staging_path, ignore_errors=True)

    @abstractmethod
    async def get_available_versions(
        self,
        channel: str | None = None,
        limit: int = 10,
    ) -> list[str]:
        """
        Get list of available versions.

        Args:
            channel: Update channel to query.
            limit: Maximum number of versions to return.

        Returns:
            List of available version strings, newest first.

        Raises:
            UnavailableError: If update source is unreachable.
        """
        pass
