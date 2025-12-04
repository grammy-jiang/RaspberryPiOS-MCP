"""
Version management for the Raspberry Pi MCP Server.

This module implements version tracking and management functionality:
- version.json structure: current, previous, history
- Semantic versioning validation
- Version history tracking

Design follows Doc 10 §5 specifications.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.logging import get_logger

logger = get_logger(__name__)

# Semantic versioning regex pattern
# Accepts: 1.0.0, 1.2.3, 2.0.0-beta.1, 1.0.0-alpha+build.123
SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def parse_semantic_version(version: str) -> dict[str, Any]:
    """
    Parse and validate a semantic version string.

    Args:
        version: Version string (e.g., "1.0.0", "1.2.3-beta.1").

    Returns:
        Dictionary with parsed version components:
        - major: Major version number
        - minor: Minor version number
        - patch: Patch version number
        - prerelease: Pre-release identifier (optional)
        - buildmetadata: Build metadata (optional)

    Raises:
        InvalidArgumentError: If version string is invalid.
    """
    if not version:
        raise InvalidArgumentError(
            "Version string cannot be empty",
            details={"version": version},
        )

    # Strip leading 'v' if present (common in git tags but invalid in semver)
    if version.startswith("v"):
        raise InvalidArgumentError(
            "Version string must not start with 'v' prefix",
            details={"version": version, "hint": "Use '1.0.0' instead of 'v1.0.0'"},
        )

    match = SEMVER_PATTERN.match(version)
    if not match:
        raise InvalidArgumentError(
            f"Invalid semantic version: {version}",
            details={
                "version": version,
                "format": "MAJOR.MINOR.PATCH[-PRERELEASE][+BUILDMETADATA]",
                "examples": ["1.0.0", "1.2.3", "2.0.0-beta.1"],
            },
        )

    return {
        "major": int(match.group("major")),
        "minor": int(match.group("minor")),
        "patch": int(match.group("patch")),
        "prerelease": match.group("prerelease"),
        "buildmetadata": match.group("buildmetadata"),
    }


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two semantic versions.

    Args:
        v1: First version string.
        v2: Second version string.

    Returns:
        -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2

    Raises:
        InvalidArgumentError: If either version is invalid.
    """
    p1 = parse_semantic_version(v1)
    p2 = parse_semantic_version(v2)

    # Compare major, minor, patch
    for key in ["major", "minor", "patch"]:
        if p1[key] < p2[key]:
            return -1
        elif p1[key] > p2[key]:
            return 1

    # Handle prerelease (no prerelease > with prerelease)
    pre1 = p1.get("prerelease")
    pre2 = p2.get("prerelease")

    if pre1 is None and pre2 is not None:
        return 1
    if pre1 is not None and pre2 is None:
        return -1
    if pre1 is not None and pre2 is not None:
        if pre1 < pre2:
            return -1
        elif pre1 > pre2:
            return 1

    return 0


# =============================================================================
# Version History Entry Model
# =============================================================================


class VersionHistory(BaseModel):
    """
    A single entry in the version history.

    Attributes:
        version: The version string (e.g., "1.0.0").
        installed_at: ISO 8601 timestamp when the version was installed.
        source: Source of the update (e.g., "pypi", "git", "local").
        status: Status of this version ("active", "previous_good", "archived").
        updated_from: Previous version before this update (optional).
    """

    version: str = Field(
        ...,
        description="Semantic version string",
    )
    installed_at: str = Field(
        ...,
        description="ISO 8601 timestamp when version was installed",
    )
    source: str = Field(
        default="pypi",
        description="Source of the update",
    )
    status: str = Field(
        default="active",
        description="Version status: active, previous_good, archived",
    )
    updated_from: str | None = Field(
        default=None,
        description="Version that was replaced by this update",
    )

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate the version is a valid semantic version."""
        parse_semantic_version(v)  # Raises InvalidArgumentError if invalid
        return v


# =============================================================================
# Version Info Model
# =============================================================================


class VersionInfo(BaseModel):
    """
    Version tracking information stored in version.json.

    This model represents the complete version state including current version,
    previous good version for rollback, and version history.

    Attributes:
        format_version: Schema version for version.json (currently "1.0").
        current: Current active version.
        previous: Previous version (for rollback). Alias for previous_good_version.
        history: List of version history entries.
        last_modified: Timestamp of last modification.
        checksum: Optional SHA256 checksum of the data (excluding checksum field).
    """

    format_version: str = Field(
        default="1.0",
        description="Schema version for version.json",
    )
    current: str = Field(
        ...,
        description="Current active version",
    )
    previous: str | None = Field(
        default=None,
        description="Previous version for rollback",
    )
    history: list[VersionHistory] = Field(
        default_factory=list,
        description="Version history entries",
    )
    last_modified: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of last modification",
    )
    checksum: str | None = Field(
        default=None,
        description="SHA256 checksum for integrity verification",
    )

    @field_validator("current")
    @classmethod
    def validate_current_version(cls, v: str) -> str:
        """Validate the current version is a valid semantic version."""
        parse_semantic_version(v)
        return v

    @field_validator("previous")
    @classmethod
    def validate_previous_version(cls, v: str | None) -> str | None:
        """Validate the previous version if present."""
        if v is not None:
            parse_semantic_version(v)
        return v


# =============================================================================
# Last Update Status Model
# =============================================================================


class LastUpdateStatus(BaseModel):
    """
    Status of the last update operation.

    Attributes:
        status: Status of the update (pending, running, succeeded, failed).
        started_at: ISO 8601 timestamp when update started.
        finished_at: ISO 8601 timestamp when update finished (optional).
        progress_percent: Progress percentage (0-100, optional).
        message: Status message or error message (optional).
        old_version: Version before the update (optional).
        new_version: Target version of the update (optional).
    """

    status: str = Field(
        default="pending",
        description="Update status: pending, running, succeeded, failed",
    )
    started_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when update started",
    )
    finished_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when update finished",
    )
    progress_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Progress percentage (0-100)",
    )
    message: str | None = Field(
        default=None,
        description="Status message or error description",
    )
    old_version: str | None = Field(
        default=None,
        description="Version before the update",
    )
    new_version: str | None = Field(
        default=None,
        description="Target version of the update",
    )


# =============================================================================
# Version Manager
# =============================================================================


class VersionManager:
    """
    Manages version.json and version state for the MCP server.

    This class provides methods to:
    - Load and save version.json with atomic operations
    - Track current and previous versions
    - Maintain version history
    - Validate version integrity via checksums

    Attributes:
        version_file: Path to version.json.
        backup_file: Path to version.json backup.
        version_info: Currently loaded version info.
    """

    DEFAULT_VERSION_FILE = Path("/opt/mcp-raspi/version.json")
    DEFAULT_BACKUP_FILE = Path("/opt/mcp-raspi/version.json.backup")

    def __init__(
        self,
        version_file: Path | str | None = None,
        backup_file: Path | str | None = None,
    ) -> None:
        """
        Initialize the VersionManager.

        Args:
            version_file: Path to version.json. Defaults to /opt/mcp-raspi/version.json.
            backup_file: Path to backup file. Defaults to /opt/mcp-raspi/version.json.backup.
        """
        self.version_file = (
            Path(version_file) if version_file else self.DEFAULT_VERSION_FILE
        )
        self.backup_file = (
            Path(backup_file) if backup_file else self.DEFAULT_BACKUP_FILE
        )
        self._version_info: VersionInfo | None = None

    @property
    def version_info(self) -> VersionInfo | None:
        """Get currently loaded version info."""
        return self._version_info

    def _calculate_checksum(self, data: dict[str, Any]) -> str:
        """
        Calculate SHA256 checksum of version data.

        The checksum is calculated on the data excluding the checksum field itself.

        Args:
            data: Version data dictionary.

        Returns:
            Checksum string in format "sha256:<hex>".
        """
        # Use deepcopy to handle nested mutable objects correctly
        data_copy = copy.deepcopy(data)
        # Remove checksum field if present
        data_copy.pop("checksum", None)
        data_json = json.dumps(data_copy, sort_keys=True, separators=(",", ":"))
        hash_hex = hashlib.sha256(data_json.encode()).hexdigest()
        return f"sha256:{hash_hex}"

    def _verify_checksum(self, data: dict[str, Any]) -> bool:
        """
        Verify the checksum of version data.

        Args:
            data: Version data dictionary including checksum field.

        Returns:
            True if checksum is valid or absent, False if invalid.
        """
        stored_checksum = data.get("checksum")
        if not stored_checksum:
            return True  # No checksum to verify

        calculated = self._calculate_checksum(data)
        return stored_checksum == calculated

    def load(self) -> VersionInfo:
        """
        Load version info from version.json with automatic recovery.

        Attempts to load from primary file first, then backup, then
        attempts reconstruction from filesystem if both fail.

        Returns:
            VersionInfo object with current version state.

        Raises:
            RuntimeError: If all recovery attempts fail.
        """
        # Try primary file
        try:
            return self._load_from_file(self.version_file)
        except (json.JSONDecodeError, FileNotFoundError, ValueError) as e:
            logger.error(
                "version.json corrupted or missing",
                extra={"error": str(e), "path": str(self.version_file)},
            )

        # Try backup file
        try:
            logger.info("Attempting recovery from backup")
            version_info = self._load_from_file(self.backup_file)

            # Restore primary from backup
            self._save_to_file(self.version_file, version_info)
            logger.info("version.json restored from backup")

            return version_info
        except Exception as backup_error:
            logger.error(
                "Backup recovery failed",
                extra={"error": str(backup_error)},
            )

        # Cannot recover - raise error
        raise RuntimeError(
            "Cannot load version.json: primary and backup files are invalid or missing"
        )

    def _load_from_file(self, path: Path) -> VersionInfo:
        """
        Load and validate version info from a file.

        Args:
            path: Path to version file.

        Returns:
            VersionInfo object.

        Raises:
            FileNotFoundError: If file doesn't exist.
            json.JSONDecodeError: If JSON is invalid.
            ValueError: If checksum verification fails.
        """
        with open(path) as f:
            data = json.load(f)

        # Verify checksum if present
        if not self._verify_checksum(data):
            raise ValueError(f"Checksum verification failed for {path}")

        # Remove checksum before creating VersionInfo
        data.pop("checksum", None)
        version_info = VersionInfo(**data)
        self._version_info = version_info

        logger.debug(
            "Loaded version info",
            extra={
                "path": str(path),
                "current": version_info.current,
                "previous": version_info.previous,
            },
        )

        return version_info

    def save(self, version_info: VersionInfo | None = None) -> None:
        """
        Save version info to version.json with backup.

        Uses atomic write (write to temp, then rename) to prevent corruption.

        Args:
            version_info: Version info to save. If None, saves current version_info.
        """
        if version_info is None:
            version_info = self._version_info

        if version_info is None:
            raise ValueError("No version info to save")

        # Update last_modified
        version_info.last_modified = datetime.now(UTC).isoformat()

        # Save to primary file
        self._save_to_file(self.version_file, version_info)

        # Save backup
        self._save_to_file(self.backup_file, version_info)

        self._version_info = version_info

    def _save_to_file(self, path: Path, version_info: VersionInfo) -> None:
        """
        Save version info to a file with atomic write.

        Args:
            path: Path to save to.
            version_info: Version info to save.
        """
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and calculate checksum
        data = version_info.model_dump(exclude_none=True)
        data["checksum"] = self._calculate_checksum(data)

        # Atomic write: write to temp file, then rename
        temp_path = path.with_suffix(".tmp")

        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            # Ensure data is written to disk
            os.fsync(f.fileno())

        # Atomic rename
        temp_path.rename(path)

        logger.debug("Saved version info", extra={"path": str(path)})

    def get_current_version(self) -> str | None:
        """
        Get the current active version.

        Returns:
            Current version string or None if not loaded.
        """
        if self._version_info is None:
            return None
        return self._version_info.current

    def get_previous_version(self) -> str | None:
        """
        Get the previous version for rollback.

        Returns:
            Previous version string or None if not available.
        """
        if self._version_info is None:
            return None
        return self._version_info.previous

    def update_version(
        self,
        new_version: str,
        source: str = "pypi",
        *,
        save: bool = True,
    ) -> None:
        """
        Update to a new version, updating history and previous version.

        Args:
            new_version: The new version being installed.
            source: Source of the update (e.g., "pypi", "git").
            save: Whether to save changes to disk immediately.

        Raises:
            InvalidArgumentError: If new_version is invalid.
            RuntimeError: If no version info is loaded.
        """
        # Validate new version
        parse_semantic_version(new_version)

        if self._version_info is None:
            raise RuntimeError("No version info loaded")

        old_version = self._version_info.current

        # Update history entries - mark old current as previous_good
        for entry in self._version_info.history:
            if entry.version == old_version:
                entry.status = "previous_good"

        # Create new history entry
        new_entry = VersionHistory(
            version=new_version,
            installed_at=datetime.now(UTC).isoformat(),
            source=source,
            status="active",
            updated_from=old_version,
        )

        # Update version info
        self._version_info.previous = old_version
        self._version_info.current = new_version
        self._version_info.history.insert(0, new_entry)

        # Limit history size (keep last 10 entries)
        if len(self._version_info.history) > 10:
            self._version_info.history = self._version_info.history[:10]

        if save:
            self.save()

        logger.info(
            "Version updated",
            extra={
                "old_version": old_version,
                "new_version": new_version,
                "source": source,
            },
        )

    def create_initial_version(
        self,
        version: str,
        source: str = "initial",
    ) -> VersionInfo:
        """
        Create an initial version.json for first-time setup.

        Args:
            version: Initial version string.
            source: Source of the initial version.

        Returns:
            Created VersionInfo object.
        """
        # Validate version
        parse_semantic_version(version)

        history_entry = VersionHistory(
            version=version,
            installed_at=datetime.now(UTC).isoformat(),
            source=source,
            status="active",
        )

        version_info = VersionInfo(
            current=version,
            previous=None,
            history=[history_entry],
        )

        self._version_info = version_info
        self.save()

        logger.info(
            "Created initial version info",
            extra={"version": version, "source": source},
        )

        return version_info

    def to_dict(self) -> dict[str, Any]:
        """
        Convert current version info to dictionary.

        Returns:
            Dictionary representation of version info.
        """
        if self._version_info is None:
            return {}
        return self._version_info.model_dump()
