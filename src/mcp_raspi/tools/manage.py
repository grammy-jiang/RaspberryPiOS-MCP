"""
Manage namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `manage.*` namespace:
- manage.get_server_status: Return server version, uptime, and last update status

Design follows Doc 05 §8 specifications.
"""

from __future__ import annotations

import platform
from datetime import UTC, datetime
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Any

from mcp_raspi.context import ToolContext
from mcp_raspi.logging import get_logger

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)

# Server start time (set when module loads, refined when server starts)
_SERVER_START_TIME: float | None = None


def set_server_start_time(start_time: float | None = None) -> None:
    """
    Set the server start time.

    This should be called when the server starts to track uptime.

    Args:
        start_time: Unix timestamp of server start. If None, uses current time.
    """
    global _SERVER_START_TIME
    _SERVER_START_TIME = start_time if start_time is not None else time()


def get_server_start_time() -> float:
    """
    Get the server start time.

    Returns:
        Unix timestamp of server start.
    """
    global _SERVER_START_TIME
    if _SERVER_START_TIME is None:
        # Initialize on first access
        _SERVER_START_TIME = time()
    return _SERVER_START_TIME


# =============================================================================
# manage.get_server_status
# =============================================================================


async def handle_manage_get_server_status(
    _ctx: ToolContext,
    _params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    version_file: Path | str | None = None,
) -> dict[str, Any]:
    """
    Handle the manage.get_server_status tool call.

    Returns the MCP server version, configuration summary, start time,
    uptime, and self-update status for introspection and operations.

    Args:
        _ctx: The ToolContext for this request.
        _params: Request parameters (empty for this tool).
        config: Optional AppConfig for additional info.
        version_file: Path to version.json for version info.

    Returns:
        Dictionary with server status:
        - version: Current server version
        - build: Build information (optional)
        - started_at: ISO 8601 timestamp of server start
        - uptime_seconds: Server uptime in seconds
        - config_summary: Summary of key configuration settings
        - last_update: Last update status (if available)
        - python_version: Python interpreter version
        - platform: Platform information
    """
    from mcp_raspi import __version__

    # Get server uptime
    start_time = get_server_start_time()
    uptime_seconds = int(time() - start_time)
    started_at = datetime.fromtimestamp(start_time, UTC).isoformat()

    # Build result
    result: dict[str, Any] = {
        "version": __version__,
        "build": None,
        "started_at": started_at,
        "uptime_seconds": uptime_seconds,
        "python_version": platform.python_version(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
    }

    # Add configuration summary if available
    if config is not None:
        result["config_summary"] = {
            "security_mode": config.security.mode,
            "sandbox_mode": config.testing.sandbox_mode,
            "update_backend": config.updates.backend,
            "remote_update_enabled": config.updates.enable_remote_server_update,
            "os_update_enabled": config.updates.enable_os_update,
        }
    else:
        result["config_summary"] = {}

    # Try to load version info from version.json
    last_update = await _get_last_update_status(version_file, config)
    result["last_update"] = last_update

    # Try to get version info from version.json if different from package
    version_info = await _get_version_info(version_file, config)
    # Only include installed_version and previous_version if version_info is well-formed and meaningful.
    # These fields are populated during an update transition when the running version differs from the installed version.
    if (
        version_info
        and isinstance(version_info.get("current"), str)
        and version_info.get("current") != __version__
    ):
        installed_version = version_info.get("current")
        previous_version = version_info.get("previous")
        if installed_version:
            result["installed_version"] = installed_version
        if previous_version and isinstance(previous_version, str):
            result["previous_version"] = previous_version
    return result


async def _get_version_info(
    version_file: Path | str | None,
    config: AppConfig | None,
) -> dict[str, Any] | None:
    """
    Load version info from version.json.

    Args:
        version_file: Path to version.json.
        config: AppConfig for default paths.

    Returns:
        Dictionary with version info, or None if not available.
    """
    from mcp_raspi.updates.version import VersionManager

    # Determine version file path
    if version_file:
        path = Path(version_file)
    elif config:
        path = Path(config.updates.releases_dir).parent / "version.json"
    else:
        path = VersionManager.DEFAULT_VERSION_FILE

    try:
        if not path.exists():
            return None

        manager = VersionManager(version_file=path)
        info = manager.load()
        return {
            "current": info.current,
            "previous": info.previous,
            "history_count": len(info.history),
        }
    except Exception as e:
        logger.debug(f"Could not load version info: {e}")
        return None


async def _get_last_update_status(
    version_file: Path | str | None,
    config: AppConfig | None,
) -> dict[str, Any] | None:
    """
    Get the last update status from version.json.

    Args:
        version_file: Path to version.json.
        config: AppConfig for default paths.

    Returns:
        Dictionary with last update status, or None if not available.
    """
    from mcp_raspi.updates.version import VersionManager

    # Determine version file path
    if version_file:
        path = Path(version_file)
    elif config:
        path = Path(config.updates.releases_dir).parent / "version.json"
    else:
        path = VersionManager.DEFAULT_VERSION_FILE

    try:
        if not path.exists():
            return None

        manager = VersionManager(version_file=path)
        info = manager.load()

        # Get the most recent history entry
        if info.history:
            latest = info.history[0]
            return {
                "status": "succeeded" if latest.status == "active" else latest.status,
                "version": latest.version,
                "installed_at": latest.installed_at,
                "source": latest.source,
                "updated_from": latest.updated_from,
            }
        return None
    except Exception as e:
        logger.debug(f"Could not get last update status: {e}")
        return None


# =============================================================================
# Helper function for tool registration
# =============================================================================


def get_manage_tools() -> dict[str, Any]:
    """
    Get all manage namespace tool handlers.

    Returns:
        Dictionary mapping tool names to handler functions.
    """
    return {
        "manage.get_server_status": handle_manage_get_server_status,
    }
