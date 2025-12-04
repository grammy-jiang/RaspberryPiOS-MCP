"""
Atomic directory and symlink operations for the Raspberry Pi MCP Server.

This module implements safe filesystem operations for version management:
- Atomic symlink switching (using tempfile + os.rename)
- Safe directory creation and removal
- Version directory management

Design follows Doc 10 §5.4 specifications.

CRITICAL: Symlink switching must be atomic to prevent race conditions.
The pattern is:
1. Create temp symlink: os.symlink(target, temp_path)
2. Atomic rename: os.rename(temp_path, final_path)

This ensures the symlink is never in an invalid state.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from mcp_raspi.errors import FailedPreconditionError, InternalError
from mcp_raspi.logging import get_logger

logger = get_logger(__name__)

# Default version directory structure
DEFAULT_RELEASES_DIR = Path("/opt/mcp-raspi/releases")
DEFAULT_CURRENT_SYMLINK = Path("/opt/mcp-raspi/current")


def ensure_directory(path: Path, *, parents: bool = True, mode: int = 0o755) -> Path:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Path to the directory.
        parents: If True, create parent directories as needed.
        mode: Directory permissions (default 0o755).

    Returns:
        The directory path.

    Raises:
        FailedPreconditionError: If directory cannot be created.
    """
    try:
        path.mkdir(parents=parents, mode=mode, exist_ok=True)
        return path
    except OSError as e:
        raise FailedPreconditionError(
            f"Failed to create directory: {path}",
            details={"path": str(path), "error": str(e)},
        ) from e


def safe_remove_directory(path: Path, *, ignore_errors: bool = True) -> bool:
    """
    Safely remove a directory and its contents.

    Args:
        path: Path to the directory to remove.
        ignore_errors: If True, ignore errors during removal.

    Returns:
        True if directory was removed, False if it didn't exist.

    Raises:
        FailedPreconditionError: If removal fails and ignore_errors is False.
    """
    if not path.exists():
        return False

    try:
        shutil.rmtree(path, ignore_errors=ignore_errors)
        logger.debug("Removed directory", extra={"path": str(path)})
        return True
    except OSError as e:
        if not ignore_errors:
            raise FailedPreconditionError(
                f"Failed to remove directory: {path}",
                details={"path": str(path), "error": str(e)},
            ) from e
        return False


def atomic_symlink_switch(
    target: Path,
    symlink_path: Path,
    *,
    relative: bool = False,
) -> None:
    """
    Atomically switch a symlink to point to a new target.

    This operation is atomic on POSIX systems using the temp-symlink + rename pattern:
    1. Create a temporary symlink to the target
    2. Atomically rename the temp symlink to the final path

    This ensures the symlink is never in an invalid state, even if
    the operation is interrupted.

    Args:
        target: The target path the symlink should point to.
        symlink_path: The path where the symlink should be created/updated.
        relative: If True, create a relative symlink.

    Raises:
        FailedPreconditionError: If the target doesn't exist.
        InternalError: If the atomic switch fails.
    """
    # Verify target exists
    if not target.exists():
        raise FailedPreconditionError(
            f"Symlink target does not exist: {target}",
            details={"target": str(target)},
        )

    # Ensure parent directory exists
    symlink_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculate symlink target (relative or absolute)
    if relative:
        # Make target relative to symlink's parent directory
        try:
            link_target = os.path.relpath(target, symlink_path.parent)
        except ValueError:
            # Fall back to absolute if relpath fails (e.g., different drives on Windows)
            link_target = str(target)
    else:
        link_target = str(target)

    # Create temp symlink in the same directory (for atomic rename)
    # Generate a unique temp symlink path and create the symlink directly
    for attempt in range(10):
        temp_name = f".symlink_tmp_{next(tempfile._get_candidate_names())}"
        temp_path = symlink_path.parent / temp_name
        if not temp_path.exists():
            try:
                os.symlink(link_target, temp_path)
                break
            except FileExistsError:
                continue
    else:
        raise InternalError(
            "Failed to create a unique temporary symlink path after 10 attempts",
            details={
                "symlink": str(symlink_path),
                "target": str(target),
            },
        )

    try:
        # Atomic rename (this is the key operation)
        os.rename(temp_path, symlink_path)

        logger.info(
            "Atomic symlink switch completed",
            extra={
                "symlink": str(symlink_path),
                "target": str(target),
            },
        )

    except OSError as e:
        # Clean up temp symlink if it exists
        try:
            if os.path.lexists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass

        raise InternalError(
            f"Failed to switch symlink atomically: {e}",
            details={
                "symlink": str(symlink_path),
                "target": str(target),
                "error": str(e),
            },
        ) from e


def get_symlink_target(symlink_path: Path) -> Path | None:
    """
    Get the target of a symlink.

    Args:
        symlink_path: Path to the symlink.

    Returns:
        The resolved target path, or None if symlink doesn't exist.
    """
    if not symlink_path.is_symlink():
        return None

    try:
        return symlink_path.resolve()
    except OSError:
        return None


def create_version_directory(
    releases_dir: Path,
    version: str,
    *,
    mode: int = 0o755,
) -> Path:
    """
    Create a version directory in the releases directory.

    Args:
        releases_dir: Parent directory for releases.
        version: Version string (e.g., "1.0.0").
        mode: Directory permissions.

    Returns:
        Path to the created version directory.

    Raises:
        FailedPreconditionError: If directory cannot be created.
    """
    # Sanitize version string for directory name (prefix with 'v')
    version_dir = releases_dir / f"v{version}"
    return ensure_directory(version_dir, mode=mode)


def get_version_directory(releases_dir: Path, version: str) -> Path | None:
    """
    Get the path to a version directory if it exists.

    Args:
        releases_dir: Parent directory for releases.
        version: Version string (e.g., "1.0.0").

    Returns:
        Path to the version directory, or None if it doesn't exist.
    """
    version_dir = releases_dir / f"v{version}"
    if version_dir.exists() and version_dir.is_dir():
        return version_dir
    return None


def list_installed_versions(releases_dir: Path) -> list[str]:
    """
    List all installed versions in the releases directory.

    Args:
        releases_dir: Parent directory for releases.

    Returns:
        List of installed version strings (without 'v' prefix), newest first.
    """
    if not releases_dir.exists():
        return []

    versions = []
    for entry in releases_dir.iterdir():
        if entry.is_dir() and entry.name.startswith("v"):
            version = entry.name[1:]  # Remove 'v' prefix
            versions.append(version)

    # Sort by modification time (newest first)
    version_paths = [(v, releases_dir / f"v{v}") for v in versions]
    version_paths.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)

    return [v for v, _ in version_paths]


def get_current_version_from_symlink(
    symlink_path: Path = DEFAULT_CURRENT_SYMLINK,
) -> str | None:
    """
    Get the current version by reading the 'current' symlink.

    Args:
        symlink_path: Path to the current symlink.

    Returns:
        Version string (without 'v' prefix), or None if symlink doesn't exist.
    """
    target = get_symlink_target(symlink_path)
    if target is None:
        return None

    # Extract version from directory name (e.g., "v1.0.0" -> "1.0.0")
    version_dir_name = target.name
    if version_dir_name.startswith("v"):
        return version_dir_name[1:]
    return version_dir_name


def initialize_version_structure(
    base_dir: Path,
    initial_version: str,
    *,
    create_symlink: bool = True,
) -> tuple[Path, Path]:
    """
    Initialize the version directory structure.

    Creates:
    - /opt/mcp-raspi/releases/
    - /opt/mcp-raspi/releases/v{version}/
    - /opt/mcp-raspi/current -> releases/v{version}/

    Args:
        base_dir: Base directory (e.g., /opt/mcp-raspi).
        initial_version: Initial version string.
        create_symlink: Whether to create the current symlink.

    Returns:
        Tuple of (releases_dir, version_dir).
    """
    releases_dir = ensure_directory(base_dir / "releases")
    version_dir = create_version_directory(releases_dir, initial_version)

    if create_symlink:
        symlink_path = base_dir / "current"
        atomic_symlink_switch(version_dir, symlink_path)

    return releases_dir, version_dir
