"""
Update state machine for the Raspberry Pi MCP Server.

This module implements the UpdateStateMachine class that orchestrates
the complete self-update process with rollback capability.

State machine states:
- idle: No update in progress
- checking: Checking for new version
- preparing: Downloading and validating new version
- switching: Switching symlink to new version
- verifying: Running health checks on new version
- success: Update completed successfully
- failed: Update failed, rollback may be needed
- rolling_back: Performing rollback to previous version

Design follows Doc 10 §4-5 specifications.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from mcp_raspi.errors import (
    FailedPreconditionError,
    InternalError,
    InvalidArgumentError,
)
from mcp_raspi.logging import get_logger

if TYPE_CHECKING:
    from mcp_raspi.updates.backends import PreparedUpdate, UpdateBackend
    from mcp_raspi.updates.version import VersionManager

logger = get_logger(__name__)


class UpdateState(str, Enum):
    """
    States for the update state machine.

    State transitions:
    - idle → checking (start update)
    - checking → preparing (new version found)
    - checking → idle (no update available)
    - preparing → switching (download complete)
    - preparing → failed (download failed)
    - switching → verifying (symlink switched)
    - switching → failed (switch failed)
    - verifying → success (health checks passed)
    - verifying → failed (health checks failed)
    - failed → rolling_back (rollback triggered)
    - rolling_back → idle (rollback complete)
    - success → idle (update complete)
    """

    IDLE = "idle"
    CHECKING = "checking"
    PREPARING = "preparing"
    SWITCHING = "switching"
    VERIFYING = "verifying"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"


class UpdateStateData(BaseModel):
    """
    Persistent state data for tracking updates across restarts.

    This model is saved to disk to enable recovery after restarts.
    """

    state: str = Field(
        default=UpdateState.IDLE.value,
        description="Current state machine state",
    )
    target_version: str | None = Field(
        default=None,
        description="Target version for the update",
    )
    old_version: str | None = Field(
        default=None,
        description="Version before the update",
    )
    channel: str | None = Field(
        default=None,
        description="Update channel being used",
    )
    started_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp when update started",
    )
    last_transition_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of last state transition",
    )
    failure_count: int = Field(
        default=0,
        description="Number of consecutive health check failures",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if in failed state",
    )
    progress_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Progress percentage (0-100)",
    )


# Valid state transitions
_VALID_TRANSITIONS: dict[UpdateState, set[UpdateState]] = {
    UpdateState.IDLE: {UpdateState.CHECKING},
    UpdateState.CHECKING: {UpdateState.PREPARING, UpdateState.IDLE, UpdateState.FAILED},
    UpdateState.PREPARING: {UpdateState.SWITCHING, UpdateState.FAILED},
    UpdateState.SWITCHING: {UpdateState.VERIFYING, UpdateState.FAILED},
    UpdateState.VERIFYING: {UpdateState.SUCCESS, UpdateState.FAILED},
    UpdateState.FAILED: {UpdateState.ROLLING_BACK, UpdateState.IDLE},
    UpdateState.ROLLING_BACK: {UpdateState.IDLE},
    UpdateState.SUCCESS: {UpdateState.IDLE},
}


class UpdateStateMachine:
    """
    Manages the update lifecycle through a state machine.

    This class orchestrates:
    - Checking for updates
    - Downloading and staging new versions
    - Switching symlinks atomically
    - Verifying health after update
    - Rolling back on failure

    State persistence enables recovery after process restarts.

    Attributes:
        state: Current state machine state.
        state_data: Persistent state data.
        backend: Update backend for fetching/applying updates.
        version_manager: Manager for version.json operations.
        releases_dir: Directory containing version releases.
        current_symlink: Path to the 'current' symlink.
        state_file: Path to state persistence file.
    """

    DEFAULT_STATE_FILE = Path("/opt/mcp-raspi/update_state.json")
    DEFAULT_RELEASES_DIR = Path("/opt/mcp-raspi/releases")
    DEFAULT_CURRENT_SYMLINK = Path("/opt/mcp-raspi/current")

    # Health check configuration
    HEALTH_CHECK_RETRIES = 3
    HEALTH_CHECK_DELAY_SECONDS = 5
    SERVICE_START_WAIT_SECONDS = 10

    def __init__(
        self,
        backend: UpdateBackend | None = None,
        version_manager: VersionManager | None = None,
        releases_dir: Path | str | None = None,
        current_symlink: Path | str | None = None,
        state_file: Path | str | None = None,
    ) -> None:
        """
        Initialize the UpdateStateMachine.

        Args:
            backend: Update backend for fetching updates.
            version_manager: Manager for version.json.
            releases_dir: Directory containing version releases.
            current_symlink: Path to 'current' symlink.
            state_file: Path to state persistence file.
        """
        self._backend = backend
        self._version_manager = version_manager
        self._releases_dir = (
            Path(releases_dir) if releases_dir else self.DEFAULT_RELEASES_DIR
        )
        self._current_symlink = (
            Path(current_symlink) if current_symlink else self.DEFAULT_CURRENT_SYMLINK
        )
        self._state_file = (
            Path(state_file) if state_file else self.DEFAULT_STATE_FILE
        )
        self._state_data = UpdateStateData()
        self._prepared_update: PreparedUpdate | None = None
        self._progress_callbacks: list[Callable[[UpdateStateData], None]] = []

        # Load any existing state on initialization
        self._load_state()

    @property
    def state(self) -> UpdateState:
        """Get the current state."""
        return UpdateState(self._state_data.state)

    @property
    def state_data(self) -> UpdateStateData:
        """Get the state data."""
        return self._state_data

    @property
    def backend(self) -> UpdateBackend | None:
        """Get the update backend."""
        return self._backend

    @backend.setter
    def backend(self, value: UpdateBackend) -> None:
        """Set the update backend."""
        self._backend = value

    @property
    def version_manager(self) -> VersionManager | None:
        """Get the version manager."""
        return self._version_manager

    @version_manager.setter
    def version_manager(self, value: VersionManager) -> None:
        """Set the version manager."""
        self._version_manager = value

    @property
    def releases_dir(self) -> Path:
        """Get the releases directory path."""
        return self._releases_dir

    @releases_dir.setter
    def releases_dir(self, value: Path | str) -> None:
        """Set the releases directory path."""
        self._releases_dir = Path(value)

    @property
    def current_symlink(self) -> Path:
        """Get the current symlink path."""
        return self._current_symlink

    @current_symlink.setter
    def current_symlink(self, value: Path | str) -> None:
        """Set the current symlink path."""
        self._current_symlink = Path(value)

    def add_progress_callback(
        self, callback: Callable[[UpdateStateData], None]
    ) -> None:
        """Add a callback to be notified of state changes."""
        self._progress_callbacks.append(callback)

    def _notify_progress(self) -> None:
        """Notify all registered callbacks of state change."""
        for callback in self._progress_callbacks:
            try:
                callback(self._state_data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def _transition_to(
        self,
        new_state: UpdateState,
        *,
        error_message: str | None = None,
        progress_percent: float | None = None,
    ) -> None:
        """
        Transition to a new state.

        Args:
            new_state: The state to transition to.
            error_message: Optional error message for failed state.
            progress_percent: Optional progress percentage.

        Raises:
            InvalidArgumentError: If the transition is not valid.
        """
        current = self.state

        if new_state not in _VALID_TRANSITIONS.get(current, set()):
            raise InvalidArgumentError(
                f"Invalid state transition from {current.value} to {new_state.value}",
                details={
                    "current_state": current.value,
                    "target_state": new_state.value,
                    "valid_transitions": [
                        s.value for s in _VALID_TRANSITIONS.get(current, set())
                    ],
                },
            )

        logger.info(
            f"State transition: {current.value} -> {new_state.value}",
            extra={
                "old_state": current.value,
                "new_state": new_state.value,
                "target_version": self._state_data.target_version,
            },
        )

        self._state_data.state = new_state.value
        self._state_data.last_transition_at = datetime.now(UTC).isoformat()

        if error_message is not None:
            self._state_data.error_message = error_message

        if progress_percent is not None:
            self._state_data.progress_percent = progress_percent

        # Save state after transition
        self._save_state()
        self._notify_progress()

    def _save_state(self) -> None:
        """Save current state to disk for persistence."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write
            temp_file = self._state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(self._state_data.model_dump(), f, indent=2)
            temp_file.rename(self._state_file)

            logger.debug(
                "Saved update state",
                extra={"path": str(self._state_file), "state": self._state_data.state},
            )
        except Exception as e:
            logger.warning(f"Failed to save update state: {e}")

    def _load_state(self) -> None:
        """Load state from disk if available."""
        try:
            if self._state_file.exists():
                with open(self._state_file) as f:
                    data = json.load(f)
                self._state_data = UpdateStateData(**data)
                logger.debug(
                    "Loaded update state",
                    extra={
                        "path": str(self._state_file),
                        "state": self._state_data.state,
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to load update state: {e}")
            self._state_data = UpdateStateData()

    def _clear_state(self) -> None:
        """Clear state data and file."""
        self._state_data = UpdateStateData()
        self._prepared_update = None
        if self._state_file.exists():
            try:
                self._state_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to remove state file: {e}")

    def reset(self) -> None:
        """
        Reset the state machine to idle state.

        This should only be called when the state machine is stuck
        or after manual intervention.
        """
        logger.info("Resetting state machine to idle")
        self._clear_state()
        self._save_state()

    async def check_for_updates(
        self,
        channel: str | None = None,
    ) -> str | None:
        """
        Check if a new version is available.

        Args:
            channel: Update channel to check.

        Returns:
            Latest available version, or None if up-to-date.

        Raises:
            FailedPreconditionError: If not in idle state or backend not set.
            UnavailableError: If update source is unreachable.
        """
        if self.state != UpdateState.IDLE:
            raise FailedPreconditionError(
                f"Cannot check for updates while in {self.state.value} state",
                details={"current_state": self.state.value},
            )

        if self._backend is None:
            raise FailedPreconditionError(
                "Update backend not configured",
                details={"hint": "Set the backend before checking for updates"},
            )

        self._state_data.channel = channel
        self._state_data.started_at = datetime.now(UTC).isoformat()
        self._transition_to(UpdateState.CHECKING, progress_percent=0)

        try:
            latest_version = await self._backend.check_for_updates(channel)

            if latest_version is None:
                logger.info("No updates available")
                self._transition_to(UpdateState.IDLE)
                self._clear_state()
                return None

            # Get current version from version manager
            current_version = None
            if self._version_manager:
                try:
                    self._version_manager.load()
                    current_version = self._version_manager.get_current_version()
                except Exception:
                    pass

            self._state_data.target_version = latest_version
            self._state_data.old_version = current_version

            logger.info(
                f"Update available: {current_version or 'unknown'} -> {latest_version}"
            )

            return latest_version

        except Exception as e:
            self._transition_to(
                UpdateState.FAILED,
                error_message=f"Failed to check for updates: {e}",
            )
            raise

    async def prepare_update(
        self,
        target_version: str | None = None,
    ) -> PreparedUpdate:
        """
        Prepare an update for installation.

        Args:
            target_version: Specific version to update to.

        Returns:
            PreparedUpdate ready for application.

        Raises:
            FailedPreconditionError: If not in checking state.
        """
        if self.state != UpdateState.CHECKING:
            raise FailedPreconditionError(
                f"Cannot prepare update while in {self.state.value} state",
                details={
                    "current_state": self.state.value,
                    "expected_state": UpdateState.CHECKING.value,
                },
            )

        if self._backend is None:
            raise FailedPreconditionError("Update backend not configured")

        # Use target_version from state if not provided
        if target_version is None:
            target_version = self._state_data.target_version

        if target_version is None:
            raise InvalidArgumentError(
                "No target version specified",
                details={"hint": "Run check_for_updates first or specify target_version"},
            )

        self._transition_to(UpdateState.PREPARING, progress_percent=10)

        try:
            self._prepared_update = await self._backend.prepare(
                channel=self._state_data.channel,
                target_version=target_version,
            )

            self._state_data.target_version = self._prepared_update.target_version
            self._state_data.progress_percent = 50
            self._save_state()

            logger.info(
                f"Update prepared: {self._prepared_update.target_version}",
                extra={
                    "staging_path": self._prepared_update.staging_path,
                },
            )

            return self._prepared_update

        except Exception as e:
            self._transition_to(
                UpdateState.FAILED,
                error_message=f"Failed to prepare update: {e}",
            )
            raise

    async def apply_update(self) -> None:
        """
        Apply the prepared update by switching symlinks.

        Raises:
            FailedPreconditionError: If not in preparing state or no update prepared.
        """
        if self.state != UpdateState.PREPARING:
            raise FailedPreconditionError(
                f"Cannot apply update while in {self.state.value} state",
                details={"current_state": self.state.value},
            )

        if self._prepared_update is None:
            raise FailedPreconditionError(
                "No update has been prepared",
                details={"hint": "Run prepare_update first"},
            )

        if self._backend is None:
            raise FailedPreconditionError("Update backend not configured")

        self._transition_to(UpdateState.SWITCHING, progress_percent=60)

        try:
            # Apply the update (install to releases directory)
            await self._backend.apply(self._prepared_update, self._releases_dir)

            # Switch the symlink atomically
            from mcp_raspi.updates.operations import (
                atomic_symlink_switch,
                get_version_directory,
            )

            version_dir = get_version_directory(
                self._releases_dir, self._prepared_update.target_version
            )
            if version_dir is None:
                # Construct path if not returned by get_version_directory
                version_dir = (
                    self._releases_dir / f"v{self._prepared_update.target_version}"
                )

            # Validate that the version directory exists before switching
            if not version_dir.exists():
                raise FailedPreconditionError(
                    f"Version directory does not exist: {version_dir}",
                    details={
                        "version": self._prepared_update.target_version,
                        "path": str(version_dir),
                    },
                )

            atomic_symlink_switch(version_dir, self._current_symlink)

            self._state_data.progress_percent = 70
            self._save_state()

            logger.info(
                f"Update applied: {self._prepared_update.target_version}",
                extra={"version_dir": str(version_dir)},
            )

        except Exception as e:
            self._transition_to(
                UpdateState.FAILED,
                error_message=f"Failed to apply update: {e}",
            )
            raise

    async def verify_update(
        self,
        health_check_func: Callable[[], Any] | None = None,
    ) -> bool:
        """
        Verify the update by running health checks.

        Args:
            health_check_func: Optional custom health check function.
                If not provided, uses default health checks.

        Returns:
            True if verification passed, False if failed.

        Raises:
            FailedPreconditionError: If not in switching state.
        """
        if self.state != UpdateState.SWITCHING:
            raise FailedPreconditionError(
                f"Cannot verify update while in {self.state.value} state",
                details={"current_state": self.state.value},
            )

        self._transition_to(UpdateState.VERIFYING, progress_percent=80)

        # Wait for service to start
        logger.info(
            f"Waiting {self.SERVICE_START_WAIT_SECONDS}s for service to start"
        )
        await asyncio.sleep(self.SERVICE_START_WAIT_SECONDS)

        success = False
        for attempt in range(1, self.HEALTH_CHECK_RETRIES + 1):
            try:
                if health_check_func:
                    await health_check_func()
                else:
                    await self._default_health_check()

                success = True
                self._state_data.failure_count = 0
                break

            except Exception as e:
                self._state_data.failure_count += 1
                logger.warning(
                    f"Health check attempt {attempt}/{self.HEALTH_CHECK_RETRIES} failed: {e}"
                )

                if attempt < self.HEALTH_CHECK_RETRIES:
                    await asyncio.sleep(self.HEALTH_CHECK_DELAY_SECONDS)

        if success:
            self._transition_to(UpdateState.SUCCESS, progress_percent=100)

            # Update version.json
            if self._version_manager and self._prepared_update:
                try:
                    self._version_manager.update_version(
                        self._prepared_update.target_version,
                        source=self._state_data.channel or "unknown",
                    )
                except Exception as e:
                    logger.warning(f"Failed to update version.json: {e}")

            return True
        else:
            self._transition_to(
                UpdateState.FAILED,
                error_message=f"Health checks failed after {self.HEALTH_CHECK_RETRIES} attempts",
            )
            return False

    async def _default_health_check(self) -> None:
        """
        Perform default health checks.

        Raises:
            Exception: If health check fails.
        """
        # Import health check module
        from mcp_raspi.updates.health_check import HealthChecker

        checker = HealthChecker()
        await checker.check_service_running()

    async def trigger_rollback(self) -> None:
        """
        Trigger rollback to previous version.

        Raises:
            FailedPreconditionError: If rollback cannot be performed.
        """
        if self.state not in (UpdateState.FAILED, UpdateState.VERIFYING):
            raise FailedPreconditionError(
                f"Cannot rollback while in {self.state.value} state",
                details={
                    "current_state": self.state.value,
                    "valid_states": [UpdateState.FAILED.value, UpdateState.VERIFYING.value],
                },
            )

        # Ensure we have a previous version to rollback to
        previous_version = self._state_data.old_version
        if not previous_version and self._version_manager:
            try:
                self._version_manager.load()
                previous_version = self._version_manager.get_previous_version()
            except Exception:
                pass

        if not previous_version:
            raise FailedPreconditionError(
                "No previous version available for rollback",
                details={"hint": "Cannot rollback without a previous version"},
            )

        # If currently in verifying state, transition to failed first
        if self.state == UpdateState.VERIFYING:
            self._transition_to(
                UpdateState.FAILED,
                error_message="Rollback requested during verification",
            )

        self._transition_to(UpdateState.ROLLING_BACK, progress_percent=85)

        try:
            from mcp_raspi.updates.rollback import perform_rollback

            await perform_rollback(
                previous_version=previous_version,
                releases_dir=self._releases_dir,
                current_symlink=self._current_symlink,
                version_manager=self._version_manager,
            )

            logger.info(f"Rollback completed to version {previous_version}")
            self._transition_to(UpdateState.IDLE)
            self._clear_state()

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            self._state_data.error_message = f"Rollback failed: {e}"
            self._transition_to(UpdateState.IDLE)  # Return to idle even on failure
            raise InternalError(f"Rollback failed: {e}") from e

    async def complete_update(self) -> None:
        """
        Complete the update process and return to idle state.

        This should be called after a successful update.
        """
        if self.state != UpdateState.SUCCESS:
            raise FailedPreconditionError(
                f"Cannot complete update while in {self.state.value} state",
                details={
                    "current_state": self.state.value,
                    "expected_state": UpdateState.SUCCESS.value,
                },
            )

        # Clean up staging files
        if self._backend and self._prepared_update:
            try:
                await self._backend.cleanup_staging(self._prepared_update)
            except Exception as e:
                logger.warning(f"Failed to cleanup staging: {e}")

        self._transition_to(UpdateState.IDLE)
        self._clear_state()
        logger.info("Update completed successfully")

    async def run_full_update(
        self,
        channel: str | None = None,
        target_version: str | None = None,
        health_check_func: Callable[[], Any] | None = None,
        restart_service_func: Callable[[], Any] | None = None,
        auto_rollback: bool = True,
    ) -> dict[str, Any]:
        """
        Run the full update process from start to finish.

        This is the main entry point for `manage.update_server`.

        Args:
            channel: Update channel to use.
            target_version: Specific version to update to.
            health_check_func: Custom health check function.
            restart_service_func: Function to restart the service.
            auto_rollback: Whether to automatically rollback on failure.

        Returns:
            Dictionary with update result:
            - status: "succeeded", "failed", or "no_update"
            - old_version: Version before update
            - new_version: Version after update
            - message: Status message
        """
        result: dict[str, Any] = {
            "status": "pending",
            "old_version": None,
            "new_version": None,
            "message": None,
        }

        try:
            # Step 1: Check for updates
            latest = await self.check_for_updates(channel)
            result["old_version"] = self._state_data.old_version

            if latest is None and target_version is None:
                result["status"] = "no_update"
                result["message"] = "Already at latest version"
                return result

            # If target_version specified, use it
            if target_version:
                self._state_data.target_version = target_version

            result["new_version"] = self._state_data.target_version

            # Step 2: Prepare update
            await self.prepare_update(target_version)

            # Step 3: Apply update
            await self.apply_update()

            # Step 4: Restart service (if function provided)
            if restart_service_func:
                try:
                    await restart_service_func()
                except Exception as e:
                    logger.warning(f"Service restart function failed: {e}")

            # Step 5: Verify update
            verification_passed = await self.verify_update(health_check_func)

            if verification_passed:
                # Step 6: Complete update
                await self.complete_update()
                result["status"] = "succeeded"
                result["message"] = f"Updated to version {self._state_data.target_version}"
            else:
                # Verification failed
                if auto_rollback:
                    await self.trigger_rollback()
                    result["status"] = "failed"
                    result["message"] = "Update failed health checks, rolled back"
                else:
                    result["status"] = "failed"
                    result["message"] = "Update failed health checks"

        except Exception as e:
            logger.error(f"Update failed: {e}")
            result["status"] = "failed"
            result["message"] = str(e)

            # Attempt rollback if in a recoverable state
            if auto_rollback and self.state in (
                UpdateState.FAILED,
                UpdateState.SWITCHING,
                UpdateState.VERIFYING,
            ):
                try:
                    await self.trigger_rollback()
                    result["message"] += " (rolled back)"
                except Exception as rollback_error:
                    result["message"] += f" (rollback failed: {rollback_error})"

        return result

    def get_status(self) -> dict[str, Any]:
        """
        Get the current status of the state machine.

        Returns:
            Dictionary with current status.
        """
        return {
            "state": self._state_data.state,
            "target_version": self._state_data.target_version,
            "old_version": self._state_data.old_version,
            "channel": self._state_data.channel,
            "started_at": self._state_data.started_at,
            "last_transition_at": self._state_data.last_transition_at,
            "progress_percent": self._state_data.progress_percent,
            "failure_count": self._state_data.failure_count,
            "error_message": self._state_data.error_message,
        }
