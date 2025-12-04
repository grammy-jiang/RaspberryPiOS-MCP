"""
Tests for the update state machine.

Tests cover:
- UpdateState enum and transitions
- UpdateStateData model
- UpdateStateMachine state transitions
- Full update cycle
- Error handling and rollback
- State persistence
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_raspi.errors import FailedPreconditionError, InvalidArgumentError
from mcp_raspi.updates.backends import PreparedUpdate
from mcp_raspi.updates.state_machine import (
    _VALID_TRANSITIONS,
    UpdateState,
    UpdateStateData,
    UpdateStateMachine,
)

# =============================================================================
# UpdateState Tests
# =============================================================================


class TestUpdateState:
    """Tests for UpdateState enum."""

    def test_state_values(self) -> None:
        """Test that all states have correct string values."""
        assert UpdateState.IDLE.value == "idle"
        assert UpdateState.CHECKING.value == "checking"
        assert UpdateState.PREPARING.value == "preparing"
        assert UpdateState.SWITCHING.value == "switching"
        assert UpdateState.VERIFYING.value == "verifying"
        assert UpdateState.SUCCESS.value == "success"
        assert UpdateState.FAILED.value == "failed"
        assert UpdateState.ROLLING_BACK.value == "rolling_back"

    def test_state_from_string(self) -> None:
        """Test creating state from string."""
        assert UpdateState("idle") == UpdateState.IDLE
        assert UpdateState("checking") == UpdateState.CHECKING
        assert UpdateState("failed") == UpdateState.FAILED


class TestValidTransitions:
    """Tests for valid state transitions."""

    def test_idle_transitions(self) -> None:
        """Test that idle can only transition to checking."""
        valid = _VALID_TRANSITIONS[UpdateState.IDLE]
        assert UpdateState.CHECKING in valid
        assert len(valid) == 1

    def test_checking_transitions(self) -> None:
        """Test checking state transitions."""
        valid = _VALID_TRANSITIONS[UpdateState.CHECKING]
        assert UpdateState.PREPARING in valid
        assert UpdateState.IDLE in valid
        assert UpdateState.FAILED in valid

    def test_preparing_transitions(self) -> None:
        """Test preparing state transitions."""
        valid = _VALID_TRANSITIONS[UpdateState.PREPARING]
        assert UpdateState.SWITCHING in valid
        assert UpdateState.FAILED in valid

    def test_switching_transitions(self) -> None:
        """Test switching state transitions."""
        valid = _VALID_TRANSITIONS[UpdateState.SWITCHING]
        assert UpdateState.VERIFYING in valid
        assert UpdateState.FAILED in valid

    def test_verifying_transitions(self) -> None:
        """Test verifying state transitions."""
        valid = _VALID_TRANSITIONS[UpdateState.VERIFYING]
        assert UpdateState.SUCCESS in valid
        assert UpdateState.FAILED in valid

    def test_failed_transitions(self) -> None:
        """Test failed state transitions."""
        valid = _VALID_TRANSITIONS[UpdateState.FAILED]
        assert UpdateState.ROLLING_BACK in valid
        assert UpdateState.IDLE in valid

    def test_rolling_back_transitions(self) -> None:
        """Test rolling_back state transitions."""
        valid = _VALID_TRANSITIONS[UpdateState.ROLLING_BACK]
        assert UpdateState.IDLE in valid

    def test_success_transitions(self) -> None:
        """Test success state transitions."""
        valid = _VALID_TRANSITIONS[UpdateState.SUCCESS]
        assert UpdateState.IDLE in valid


# =============================================================================
# UpdateStateData Tests
# =============================================================================


class TestUpdateStateData:
    """Tests for UpdateStateData model."""

    def test_default_values(self) -> None:
        """Test default state data values."""
        data = UpdateStateData()
        assert data.state == "idle"
        assert data.target_version is None
        assert data.old_version is None
        assert data.channel is None
        assert data.failure_count == 0
        assert data.error_message is None

    def test_custom_values(self) -> None:
        """Test creating state data with custom values."""
        data = UpdateStateData(
            state="checking",
            target_version="1.2.0",
            old_version="1.1.0",
            channel="stable",
            failure_count=2,
        )
        assert data.state == "checking"
        assert data.target_version == "1.2.0"
        assert data.old_version == "1.1.0"
        assert data.channel == "stable"
        assert data.failure_count == 2

    def test_model_dump(self) -> None:
        """Test that model dumps correctly."""
        data = UpdateStateData(state="preparing", target_version="2.0.0")
        dumped = data.model_dump()
        assert dumped["state"] == "preparing"
        assert dumped["target_version"] == "2.0.0"


# =============================================================================
# UpdateStateMachine Initialization Tests
# =============================================================================


class TestUpdateStateMachineInit:
    """Tests for UpdateStateMachine initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a fresh state file so no existing state interferes
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            assert sm.state == UpdateState.IDLE
            assert sm.backend is None
            assert sm.version_manager is None

    def test_init_with_custom_paths(self) -> None:
        """Test initialization with custom paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            symlink = Path(tmpdir) / "current"
            state_file = Path(tmpdir) / "state.json"

            sm = UpdateStateMachine(
                releases_dir=releases_dir,
                current_symlink=symlink,
                state_file=state_file,
            )

            assert sm._releases_dir == releases_dir
            assert sm._current_symlink == symlink
            assert sm._state_file == state_file

    def test_init_loads_existing_state(self) -> None:
        """Test that init loads existing state from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            # Write existing state
            state_data = {
                "state": "checking",
                "target_version": "1.5.0",
                "channel": "stable",
            }
            state_file.write_text(json.dumps(state_data))

            sm = UpdateStateMachine(state_file=state_file)

            assert sm.state == UpdateState.CHECKING
            assert sm.state_data.target_version == "1.5.0"


# =============================================================================
# State Transition Tests
# =============================================================================


class TestStateTransitions:
    """Tests for state transitions."""

    def test_valid_transition_idle_to_checking(self) -> None:
        """Test valid transition from idle to checking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            sm._transition_to(UpdateState.CHECKING)
            assert sm.state == UpdateState.CHECKING

    def test_valid_transition_checking_to_preparing(self) -> None:
        """Test valid transition from checking to preparing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            sm._state_data.state = UpdateState.CHECKING.value
            sm._transition_to(UpdateState.PREPARING)
            assert sm.state == UpdateState.PREPARING

    def test_invalid_transition_raises_error(self) -> None:
        """Test that invalid transition raises InvalidArgumentError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            # Can't go directly from idle to preparing
            with pytest.raises(InvalidArgumentError) as exc_info:
                sm._transition_to(UpdateState.PREPARING)

            assert "Invalid state transition" in exc_info.value.message

    def test_transition_updates_timestamp(self) -> None:
        """Test that transition updates last_transition_at."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            # Don't assert None initially since loading state may set it
            sm._transition_to(UpdateState.CHECKING)
            assert sm.state_data.last_transition_at is not None

    def test_transition_with_error_message(self) -> None:
        """Test transition with error message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            sm._state_data.state = UpdateState.CHECKING.value

            sm._transition_to(UpdateState.FAILED, error_message="Test error")

            assert sm.state == UpdateState.FAILED
            assert sm.state_data.error_message == "Test error"

    def test_transition_with_progress(self) -> None:
        """Test transition with progress percentage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            sm._transition_to(UpdateState.CHECKING, progress_percent=25.0)

            assert sm.state_data.progress_percent == 25.0


# =============================================================================
# State Persistence Tests
# =============================================================================


class TestStatePersistence:
    """Tests for state persistence."""

    def test_save_state_creates_file(self) -> None:
        """Test that save_state creates state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            sm = UpdateStateMachine(state_file=state_file)

            sm._state_data.state = "checking"
            sm._save_state()

            assert state_file.exists()
            data = json.loads(state_file.read_text())
            assert data["state"] == "checking"

    def test_load_state_restores_data(self) -> None:
        """Test that load_state restores saved data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            # Save state
            sm1 = UpdateStateMachine(state_file=state_file)
            sm1._state_data.state = "preparing"
            sm1._state_data.target_version = "2.0.0"
            sm1._save_state()

            # Load in new instance
            sm2 = UpdateStateMachine(state_file=state_file)

            assert sm2.state == UpdateState.PREPARING
            assert sm2.state_data.target_version == "2.0.0"

    def test_clear_state_removes_file(self) -> None:
        """Test that clear_state removes state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            sm = UpdateStateMachine(state_file=state_file)

            # Save then clear
            sm._save_state()
            assert state_file.exists()

            sm._clear_state()
            assert not state_file.exists()

    def test_reset_returns_to_idle(self) -> None:
        """Test that reset returns to idle state."""
        sm = UpdateStateMachine()
        sm._state_data.state = "checking"
        sm._state_data.target_version = "1.0.0"

        sm.reset()

        assert sm.state == UpdateState.IDLE
        assert sm.state_data.target_version is None


# =============================================================================
# Check For Updates Tests
# =============================================================================


class TestCheckForUpdates:
    """Tests for check_for_updates method."""

    @pytest.mark.asyncio
    async def test_check_requires_idle_state(self) -> None:
        """Test that check_for_updates requires idle state."""
        sm = UpdateStateMachine()
        sm._state_data.state = UpdateState.CHECKING.value

        with pytest.raises(FailedPreconditionError) as exc_info:
            await sm.check_for_updates()

        assert "Cannot check for updates" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_check_requires_backend(self) -> None:
        """Test that check_for_updates requires backend."""
        sm = UpdateStateMachine()

        with pytest.raises(FailedPreconditionError) as exc_info:
            await sm.check_for_updates()

        assert "backend not configured" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_check_returns_latest_version(self) -> None:
        """Test that check_for_updates returns latest version."""
        sm = UpdateStateMachine()

        backend = AsyncMock()
        backend.check_for_updates = AsyncMock(return_value="1.5.0")
        sm.backend = backend

        result = await sm.check_for_updates()

        assert result == "1.5.0"
        assert sm.state == UpdateState.CHECKING
        assert sm.state_data.target_version == "1.5.0"

    @pytest.mark.asyncio
    async def test_check_returns_none_when_up_to_date(self) -> None:
        """Test that check_for_updates returns None when up to date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")

            backend = AsyncMock()
            backend.check_for_updates = AsyncMock(return_value=None)
            sm.backend = backend

            result = await sm.check_for_updates()

            assert result is None
            assert sm.state == UpdateState.IDLE


# =============================================================================
# Prepare Update Tests
# =============================================================================


class TestPrepareUpdate:
    """Tests for prepare_update method."""

    @pytest.mark.asyncio
    async def test_prepare_requires_checking_state(self) -> None:
        """Test that prepare_update requires checking state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            # State is idle, not checking

            with pytest.raises(FailedPreconditionError) as exc_info:
                await sm.prepare_update()

            assert "Cannot prepare update" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_prepare_returns_prepared_update(self) -> None:
        """Test that prepare_update returns PreparedUpdate."""
        sm = UpdateStateMachine()
        sm._state_data.state = UpdateState.CHECKING.value
        sm._state_data.target_version = "2.0.0"

        backend = AsyncMock()
        prepared = PreparedUpdate(
            target_version="2.0.0",
            staging_path="/tmp/staging",
        )
        backend.prepare = AsyncMock(return_value=prepared)
        sm.backend = backend

        result = await sm.prepare_update()

        assert result.target_version == "2.0.0"
        assert sm.state == UpdateState.PREPARING


# =============================================================================
# Apply Update Tests
# =============================================================================


class TestApplyUpdate:
    """Tests for apply_update method."""

    @pytest.mark.asyncio
    async def test_apply_requires_preparing_state(self) -> None:
        """Test that apply_update requires preparing state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            # State is idle, not preparing

            with pytest.raises(FailedPreconditionError) as exc_info:
                await sm.apply_update()

            assert "Cannot apply update" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_apply_requires_prepared_update(self) -> None:
        """Test that apply_update requires a prepared update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            sm._state_data.state = UpdateState.PREPARING.value

            backend = AsyncMock()
            sm.backend = backend

            with pytest.raises(FailedPreconditionError) as exc_info:
                await sm.apply_update()

            assert "No update has been prepared" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_apply_switches_symlink(self) -> None:
        """Test that apply_update switches symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()
            version_dir = releases_dir / "v2.0.0"
            version_dir.mkdir()

            symlink = Path(tmpdir) / "current"

            sm = UpdateStateMachine(
                releases_dir=releases_dir,
                current_symlink=symlink,
                state_file=Path(tmpdir) / "state.json",
            )
            sm._state_data.state = UpdateState.PREPARING.value

            backend = AsyncMock()
            backend.apply = AsyncMock()
            sm.backend = backend

            sm._prepared_update = PreparedUpdate(
                target_version="2.0.0",
                staging_path="/tmp/staging",
            )

            await sm.apply_update()

            assert sm.state == UpdateState.SWITCHING
            backend.apply.assert_awaited_once()


# =============================================================================
# Verify Update Tests
# =============================================================================


class TestVerifyUpdate:
    """Tests for verify_update method."""

    @pytest.mark.asyncio
    async def test_verify_requires_switching_state(self) -> None:
        """Test that verify_update requires switching state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            # State is idle, not switching

            with pytest.raises(FailedPreconditionError) as exc_info:
                await sm.verify_update()

            assert "Cannot verify update" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_verify_succeeds_with_passing_health_check(self) -> None:
        """Test that verify_update succeeds with passing health check."""
        sm = UpdateStateMachine()
        sm._state_data.state = UpdateState.SWITCHING.value
        sm._prepared_update = PreparedUpdate(target_version="2.0.0")
        sm.SERVICE_START_WAIT_SECONDS = 0.01  # Speed up test

        async def passing_health_check() -> None:
            pass

        result = await sm.verify_update(health_check_func=passing_health_check)

        assert result is True
        assert sm.state == UpdateState.SUCCESS

    @pytest.mark.asyncio
    async def test_verify_fails_with_failing_health_check(self) -> None:
        """Test that verify_update fails with failing health check."""
        sm = UpdateStateMachine()
        sm._state_data.state = UpdateState.SWITCHING.value
        sm._state_data.old_version = "1.0.0"
        sm.SERVICE_START_WAIT_SECONDS = 0.01
        sm.HEALTH_CHECK_DELAY_SECONDS = 0.01
        sm.HEALTH_CHECK_RETRIES = 2

        async def failing_health_check() -> None:
            raise Exception("Health check failed")

        result = await sm.verify_update(health_check_func=failing_health_check)

        assert result is False
        assert sm.state == UpdateState.FAILED
        assert sm.state_data.failure_count == 2


# =============================================================================
# Rollback Tests
# =============================================================================


class TestRollback:
    """Tests for trigger_rollback method."""

    @pytest.mark.asyncio
    async def test_rollback_requires_failed_state(self) -> None:
        """Test that rollback requires failed or verifying state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            # State is idle

            with pytest.raises(FailedPreconditionError) as exc_info:
                await sm.trigger_rollback()

            assert "Cannot rollback" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_rollback_requires_previous_version(self) -> None:
        """Test that rollback requires a previous version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            sm._state_data.state = UpdateState.FAILED.value
            sm._state_data.old_version = None

            with pytest.raises(FailedPreconditionError) as exc_info:
                await sm.trigger_rollback()

            assert "No previous version available" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_rollback_performs_rollback(self) -> None:
        """Test that rollback performs the rollback operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()
            version_dir = releases_dir / "v1.0.0"
            version_dir.mkdir()

            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(version_dir)

            sm = UpdateStateMachine(
                releases_dir=releases_dir,
                current_symlink=symlink,
                state_file=Path(tmpdir) / "state.json",
            )
            sm._state_data.state = UpdateState.FAILED.value
            sm._state_data.old_version = "1.0.0"

            with patch("mcp_raspi.updates.rollback.perform_rollback") as mock_rollback:
                mock_rollback.return_value = None
                await sm.trigger_rollback()

                assert sm.state == UpdateState.IDLE
                mock_rollback.assert_awaited_once()


# =============================================================================
# Full Update Cycle Tests
# =============================================================================


class TestFullUpdateCycle:
    """Tests for run_full_update method."""

    @pytest.mark.asyncio
    async def test_full_update_success(self) -> None:
        """Test successful full update cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()
            version_dir = releases_dir / "v2.0.0"
            version_dir.mkdir()

            symlink = Path(tmpdir) / "current"

            sm = UpdateStateMachine(
                releases_dir=releases_dir,
                current_symlink=symlink,
                state_file=Path(tmpdir) / "state.json",
            )
            sm.SERVICE_START_WAIT_SECONDS = 0.01

            # Mock backend
            backend = AsyncMock()
            backend.check_for_updates = AsyncMock(return_value="2.0.0")
            backend.prepare = AsyncMock(
                return_value=PreparedUpdate(
                    target_version="2.0.0",
                    staging_path="/tmp/staging",
                )
            )
            backend.apply = AsyncMock()
            backend.cleanup_staging = AsyncMock()
            sm.backend = backend

            async def passing_health_check() -> None:
                pass

            result = await sm.run_full_update(
                channel="stable",
                health_check_func=passing_health_check,
            )

            assert result["status"] == "succeeded"
            assert result["new_version"] == "2.0.0"
            assert sm.state == UpdateState.IDLE

    @pytest.mark.asyncio
    async def test_full_update_no_update_available(self) -> None:
        """Test full update when no update is available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")

            backend = AsyncMock()
            backend.check_for_updates = AsyncMock(return_value=None)
            sm.backend = backend

            result = await sm.run_full_update()

            assert result["status"] == "no_update"
            assert sm.state == UpdateState.IDLE

    @pytest.mark.asyncio
    async def test_full_update_with_auto_rollback(self) -> None:
        """Test full update with auto rollback on failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            releases_dir = Path(tmpdir) / "releases"
            releases_dir.mkdir()

            # Create both versions
            (releases_dir / "v1.0.0").mkdir()
            (releases_dir / "v2.0.0").mkdir()

            symlink = Path(tmpdir) / "current"
            symlink.symlink_to(releases_dir / "v1.0.0")

            # Create version manager with previous version
            version_file = Path(tmpdir) / "version.json"
            backup_file = Path(tmpdir) / "version.json.backup"
            from mcp_raspi.updates.version import VersionManager

            version_manager = VersionManager(
                version_file=version_file,
                backup_file=backup_file,
            )
            version_manager.create_initial_version("1.0.0")

            sm = UpdateStateMachine(
                releases_dir=releases_dir,
                current_symlink=symlink,
                state_file=Path(tmpdir) / "state.json",
            )
            sm.version_manager = version_manager
            sm.SERVICE_START_WAIT_SECONDS = 0.01
            sm.HEALTH_CHECK_DELAY_SECONDS = 0.01
            sm.HEALTH_CHECK_RETRIES = 1

            backend = AsyncMock()
            backend.check_for_updates = AsyncMock(return_value="2.0.0")
            backend.prepare = AsyncMock(
                return_value=PreparedUpdate(
                    target_version="2.0.0",
                    staging_path="/tmp/staging",
                )
            )
            backend.apply = AsyncMock()
            sm.backend = backend

            async def failing_health_check() -> None:
                raise Exception("Service not healthy")

            result = await sm.run_full_update(
                health_check_func=failing_health_check,
                auto_rollback=True,
            )

            assert result["status"] == "failed"
            # After rollback, symlink should point to v1.0.0
            assert "rolled back" in result["message"] or sm.state == UpdateState.IDLE


# =============================================================================
# Get Status Tests
# =============================================================================


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_returns_dict(self) -> None:
        """Test that get_status returns a dictionary."""
        sm = UpdateStateMachine()
        sm._state_data.state = "checking"
        sm._state_data.target_version = "1.5.0"

        status = sm.get_status()

        assert isinstance(status, dict)
        assert status["state"] == "checking"
        assert status["target_version"] == "1.5.0"

    def test_get_status_includes_all_fields(self) -> None:
        """Test that get_status includes all relevant fields."""
        sm = UpdateStateMachine()

        status = sm.get_status()

        assert "state" in status
        assert "target_version" in status
        assert "old_version" in status
        assert "channel" in status
        assert "started_at" in status
        assert "last_transition_at" in status
        assert "progress_percent" in status
        assert "failure_count" in status
        assert "error_message" in status


# =============================================================================
# Progress Callback Tests
# =============================================================================


class TestProgressCallbacks:
    """Tests for progress callback functionality."""

    def test_add_progress_callback(self) -> None:
        """Test adding a progress callback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            callback = MagicMock()

            sm.add_progress_callback(callback)

            assert callback in sm._progress_callbacks

    def test_callback_called_on_transition(self) -> None:
        """Test that callback is called on state transition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")
            callback = MagicMock()
            sm.add_progress_callback(callback)

            sm._transition_to(UpdateState.CHECKING)

            callback.assert_called_once()
            call_args = callback.call_args[0]
            assert call_args[0].state == "checking"

    def test_callback_error_does_not_break_transition(self) -> None:
        """Test that callback errors don't break transitions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = UpdateStateMachine(state_file=Path(tmpdir) / "state.json")

            def failing_callback(_data: UpdateStateData) -> None:
                raise Exception("Callback failed")

            sm.add_progress_callback(failing_callback)

            # Should not raise
            sm._transition_to(UpdateState.CHECKING)
            assert sm.state == UpdateState.CHECKING
