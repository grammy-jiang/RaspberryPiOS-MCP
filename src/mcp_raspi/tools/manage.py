"""
Manage namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `manage.*` namespace:
- manage.get_server_status: Return server version, uptime, and last update status
- manage.update_server: Trigger self-update to a new version
- manage.check_for_updates: Check if updates are available
- manage.rollback_server: Rollback to previous version

Design follows Doc 05 §8 specifications.
"""

from __future__ import annotations

import platform
from datetime import UTC, datetime
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Any

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import FailedPreconditionError, PermissionDeniedError
from mcp_raspi.logging import get_logger

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig
    from mcp_raspi.updates.state_machine import UpdateStateMachine

logger = get_logger(__name__)

# Global state machine instance (initialized lazily)
# Note: This singleton pattern means concurrent updates are not supported.
# The state machine is reset if configuration changes are detected.
_UPDATE_STATE_MACHINE: UpdateStateMachine | None = None
_UPDATE_STATE_MACHINE_CONFIG_HASH: str | None = None

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
        "manage.check_for_updates": handle_manage_check_for_updates,
        "manage.update_server": handle_manage_update_server,
        "manage.rollback_server": handle_manage_rollback_server,
    }


# =============================================================================
# State Machine Management
# =============================================================================


def _compute_config_hash(config: AppConfig) -> str:
    """Compute a hash of the update-related configuration."""
    import hashlib
    config_str = f"{config.updates.backend}:{config.updates.package_name}:{config.updates.releases_dir}"
    return hashlib.md5(config_str.encode()).hexdigest()


def get_update_state_machine(
    config: AppConfig | None = None,
) -> UpdateStateMachine:
    """
    Get or create the global update state machine.

    The state machine is a singleton. If the configuration changes, the
    state machine is reset to ensure it uses the new configuration.

    Note: Concurrent updates are not supported. Only one update operation
    can run at a time.

    Args:
        config: Optional config to configure the state machine.

    Returns:
        The UpdateStateMachine instance.
    """
    global _UPDATE_STATE_MACHINE, _UPDATE_STATE_MACHINE_CONFIG_HASH

    # Check if configuration has changed
    if config is not None:
        new_hash = _compute_config_hash(config)
        if _UPDATE_STATE_MACHINE_CONFIG_HASH is not None and new_hash != _UPDATE_STATE_MACHINE_CONFIG_HASH:
            logger.info("Update configuration changed, resetting state machine")
            _UPDATE_STATE_MACHINE = None
        _UPDATE_STATE_MACHINE_CONFIG_HASH = new_hash

    if _UPDATE_STATE_MACHINE is None:
        from mcp_raspi.updates.state_machine import UpdateStateMachine

        _UPDATE_STATE_MACHINE = UpdateStateMachine()

        # Configure from AppConfig if provided
        if config:
            _configure_state_machine(_UPDATE_STATE_MACHINE, config)

    return _UPDATE_STATE_MACHINE


def _configure_state_machine(
    state_machine: UpdateStateMachine,
    config: AppConfig,
) -> None:
    """
    Configure the state machine from AppConfig.

    Args:
        state_machine: The state machine to configure.
        config: Application configuration.
    """
    from mcp_raspi.updates.python_backend import PythonPackageBackend
    from mcp_raspi.updates.version import VersionManager

    # Set up backend based on config
    if config.updates.backend == "python_package":
        backend = PythonPackageBackend(
            package_name=config.updates.package_name,
            staging_dir=config.updates.staging_dir,
        )
        state_machine.backend = backend

    # Set up version manager
    version_file = Path(config.updates.releases_dir).parent / "version.json"
    version_manager = VersionManager(version_file=version_file)
    state_machine.version_manager = version_manager

    # Set paths using public setters
    state_machine.releases_dir = Path(config.updates.releases_dir)
    state_machine.current_symlink = Path(config.updates.releases_dir).parent / "current"


def reset_update_state_machine() -> None:
    """Reset the global state machine (useful for testing)."""
    global _UPDATE_STATE_MACHINE, _UPDATE_STATE_MACHINE_CONFIG_HASH
    _UPDATE_STATE_MACHINE = None
    _UPDATE_STATE_MACHINE_CONFIG_HASH = None


# =============================================================================
# manage.check_for_updates
# =============================================================================


async def handle_manage_check_for_updates(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the manage.check_for_updates tool call.

    Checks if a new version of the MCP server is available.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - channel: Update channel (optional, defaults to "stable")
        config: Optional AppConfig for configuration.

    Returns:
        Dictionary with update availability info:
        - update_available: Whether an update is available
        - current_version: Current server version
        - latest_version: Latest available version
        - channel: Update channel used
    """
    from mcp_raspi import __version__

    # Verify caller has permission (admin role required)
    _check_update_permission(ctx, config, operation="check")

    channel = params.get("channel", "stable")

    # Get the state machine and backend
    state_machine = get_update_state_machine(config)

    if state_machine.backend is None:
        # Create default backend
        from mcp_raspi.updates.python_backend import PythonPackageBackend

        state_machine.backend = PythonPackageBackend()

    try:
        # Check for updates
        latest_version = await state_machine.backend.check_for_updates(channel)

        result: dict[str, Any] = {
            "update_available": latest_version is not None
            and latest_version != __version__,
            "current_version": __version__,
            "latest_version": latest_version,
            "channel": channel,
        }

        logger.info(
            f"Update check: current={__version__}, latest={latest_version}",
            extra={"channel": channel},
        )

        return result

    except Exception as e:
        logger.error(f"Update check failed: {e}")
        return {
            "update_available": False,
            "current_version": __version__,
            "latest_version": None,
            "channel": channel,
            "error": str(e),
        }


# =============================================================================
# manage.update_server
# =============================================================================


async def handle_manage_update_server(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the manage.update_server tool call.

    Triggers a self-update of the MCP server.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - channel: Update channel (optional, defaults to "stable")
            - target_version: Specific version to update to (optional)
            - auto_rollback: Whether to auto-rollback on failure (default: True)
        config: Optional AppConfig for configuration.

    Returns:
        Dictionary with update result:
        - status: "succeeded", "failed", or "no_update"
        - old_version: Version before update
        - new_version: Version after update
        - message: Status message
    """
    from mcp_raspi import __version__

    # Verify caller has permission (admin role required)
    _check_update_permission(ctx, config, operation="update")

    # Check if remote updates are enabled
    if config and not config.updates.enable_remote_server_update:
        raise FailedPreconditionError(
            "Remote server updates are disabled",
            details={
                "hint": "Set updates.enable_remote_server_update=true in config",
                "config_key": "updates.enable_remote_server_update",
            },
        )

    channel = params.get("channel", "stable")
    target_version = params.get("target_version")
    auto_rollback = params.get("auto_rollback", True)

    # Get the state machine
    state_machine = get_update_state_machine(config)

    if state_machine.backend is None:
        from mcp_raspi.updates.python_backend import PythonPackageBackend

        state_machine.backend = PythonPackageBackend()

    # Create restart function for service restart
    async def restart_services() -> None:
        from mcp_raspi.updates.systemd_restart import graceful_restart_for_update

        await graceful_restart_for_update()

    try:
        # Run the full update process
        result = await state_machine.run_full_update(
            channel=channel,
            target_version=target_version,
            auto_rollback=auto_rollback,
            restart_service_func=restart_services,
        )

        logger.info(
            f"Update completed: status={result['status']}",
            extra={
                "old_version": result.get("old_version"),
                "new_version": result.get("new_version"),
            },
        )

        return result

    except Exception as e:
        logger.error(f"Update failed: {e}")
        return {
            "status": "failed",
            "old_version": __version__,
            "new_version": None,
            "message": str(e),
        }


# =============================================================================
# manage.rollback_server
# =============================================================================


async def handle_manage_rollback_server(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the manage.rollback_server tool call.

    Rolls back to the previous version of the MCP server.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - target_version: Specific version to rollback to (optional)
        config: Optional AppConfig for configuration.

    Returns:
        Dictionary with rollback result:
        - status: "succeeded" or "failed"
        - old_version: Version before rollback
        - new_version: Version after rollback
        - message: Status message
    """
    from mcp_raspi import __version__

    # Verify caller has permission (admin role required)
    _check_update_permission(ctx, config, operation="rollback")

    target_version = params.get("target_version")

    try:
        from mcp_raspi.updates.rollback import RollbackManager
        from mcp_raspi.updates.version import VersionManager

        # Set up rollback manager
        releases_dir = Path("/opt/mcp-raspi/releases")
        if config:
            releases_dir = Path(config.updates.releases_dir)

        version_file = releases_dir.parent / "version.json"
        version_manager = VersionManager(version_file=version_file)

        rollback_manager = RollbackManager(
            releases_dir=releases_dir,
            version_manager=version_manager,
        )

        # Perform rollback
        if target_version:
            rolled_back_to = await rollback_manager.rollback_to_version(target_version)
        else:
            rolled_back_to = await rollback_manager.rollback_to_previous()

        # Restart services after rollback
        from mcp_raspi.updates.systemd_restart import graceful_restart_for_update

        await graceful_restart_for_update()

        logger.info(f"Rollback completed to version {rolled_back_to}")

        return {
            "status": "succeeded",
            "old_version": __version__,
            "new_version": rolled_back_to,
            "message": f"Rolled back to version {rolled_back_to}",
        }

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return {
            "status": "failed",
            "old_version": __version__,
            "new_version": None,
            "message": str(e),
        }


# =============================================================================
# Helper Functions
# =============================================================================


def _check_update_permission(
    ctx: ToolContext,
    _config: AppConfig | None,
    *,
    operation: str,
) -> None:
    """
    Check if the caller has permission for update operations.

    Args:
        ctx: The ToolContext with caller info.
        config: Optional config for role checking.
        operation: The operation being performed.

    Raises:
        PermissionDeniedError: If caller lacks permission.
    """
    # Admin role is required for all update operations
    if ctx.caller.role not in ("admin",):
        raise PermissionDeniedError(
            f"Admin role required for {operation} operations",
            details={
                "required_role": "admin",
                "caller_role": ctx.caller.role,
                "operation": operation,
            },
        )
