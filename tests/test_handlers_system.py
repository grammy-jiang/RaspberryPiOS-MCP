"""
Tests for privileged agent system handlers.

This test module validates:
- System reboot handler validation and execution
- System shutdown handler validation and execution
- Handler registration with registry
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi_ops.handlers.system import (
    MAX_DELAY_SECONDS,
    _execute_power_command,
    _validate_delay,
    handle_system_reboot,
    handle_system_shutdown,
    register_system_handlers,
)
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def reboot_request() -> IPCRequest:
    """Create a reboot IPC request."""
    return IPCRequest.create(
        operation="system.reboot",
        params={
            "reason": "Scheduled maintenance",
            "delay_seconds": 5,
            "caller": {"user_id": "admin@example.com", "role": "admin"},
        },
        request_id="test-req-reboot",
    )


@pytest.fixture
def shutdown_request() -> IPCRequest:
    """Create a shutdown IPC request."""
    return IPCRequest.create(
        operation="system.shutdown",
        params={
            "reason": "Power saving",
            "delay_seconds": 10,
            "caller": {"user_id": "admin@example.com", "role": "admin"},
        },
        request_id="test-req-shutdown",
    )


@pytest.fixture
def registry() -> HandlerRegistry:
    """Create a fresh handler registry."""
    return HandlerRegistry()


# =============================================================================
# Tests for Delay Validation
# =============================================================================


class TestValidateDelay:
    """Tests for _validate_delay helper function."""

    def test_valid_delay(self) -> None:
        """Test valid delay values are returned unchanged."""
        assert _validate_delay(0) == 0
        assert _validate_delay(5) == 5
        assert _validate_delay(300) == 300
        assert _validate_delay(600) == 600

    def test_string_converted_to_int(self) -> None:
        """Test string delay is converted to int."""
        assert _validate_delay("10") == 10
        assert _validate_delay("0") == 0

    def test_negative_delay_raises(self) -> None:
        """Test negative delay raises HandlerError."""
        with pytest.raises(HandlerError) as exc_info:
            _validate_delay(-1)
        assert exc_info.value.code == "invalid_argument"
        assert "delay_seconds" in str(exc_info.value.details)

    def test_too_large_delay_raises(self) -> None:
        """Test delay > MAX raises HandlerError."""
        with pytest.raises(HandlerError) as exc_info:
            _validate_delay(MAX_DELAY_SECONDS + 1)
        assert exc_info.value.code == "invalid_argument"

    def test_invalid_type_raises(self) -> None:
        """Test invalid type raises HandlerError."""
        with pytest.raises(HandlerError) as exc_info:
            _validate_delay("not_a_number")
        assert exc_info.value.code == "invalid_argument"


# =============================================================================
# Tests for Execute Power Command
# =============================================================================


class TestExecutePowerCommand:
    """Tests for _execute_power_command helper function."""

    @pytest.mark.asyncio
    async def test_immediate_execution_success(self) -> None:
        """Test immediate power command execution."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = await _execute_power_command(
                command=["systemctl", "reboot"],
                delay_seconds=0,
                operation="system.reboot",
                reason="test",
            )

            assert result["executed"] is True
            mock_run.assert_called()

    @pytest.mark.asyncio
    async def test_command_failure_raises_error(self) -> None:
        """Test command failure raises HandlerError."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Permission denied",
            )

            with pytest.raises(HandlerError) as exc_info:
                await _execute_power_command(
                    command=["systemctl", "reboot"],
                    delay_seconds=0,
                    operation="system.reboot",
                    reason="test",
                )

            assert exc_info.value.code == "internal"
            assert "failed" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_command_not_found_raises_error(self) -> None:
        """Test missing command raises HandlerError."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("No such file")

            with pytest.raises(HandlerError) as exc_info:
                await _execute_power_command(
                    command=["nonexistent_command"],
                    delay_seconds=0,
                    operation="system.reboot",
                    reason="test",
                )

            assert exc_info.value.code == "unavailable"


# =============================================================================
# Tests for System Reboot Handler
# =============================================================================


class TestHandleSystemReboot:
    """Tests for handle_system_reboot handler."""

    @pytest.mark.asyncio
    async def test_reboot_with_valid_params(self, reboot_request: IPCRequest) -> None:
        """Test reboot handler with valid parameters."""
        with patch("mcp_raspi_ops.handlers.system._execute_power_command") as mock_exec:
            mock_exec.return_value = {"executed": True}

            result = await handle_system_reboot(reboot_request)

            assert result["executed"] is True
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args
            assert call_args.kwargs["delay_seconds"] == 5
            assert call_args.kwargs["reason"] == "Scheduled maintenance"

    @pytest.mark.asyncio
    async def test_reboot_uses_default_delay(self) -> None:
        """Test reboot uses default delay if not specified."""
        request = IPCRequest.create(
            operation="system.reboot",
            params={},
            request_id="test-req",
        )

        with patch("mcp_raspi_ops.handlers.system._execute_power_command") as mock_exec:
            mock_exec.return_value = {"executed": True}

            await handle_system_reboot(request)

            call_args = mock_exec.call_args
            assert call_args.kwargs["delay_seconds"] == 5  # Default

    @pytest.mark.asyncio
    async def test_reboot_logs_caller_info(self, reboot_request: IPCRequest) -> None:
        """Test reboot handler logs caller information."""
        with patch("mcp_raspi_ops.handlers.system._execute_power_command") as mock_exec:
            mock_exec.return_value = {"executed": True}

            with patch("mcp_raspi_ops.handlers.system.logger") as mock_logger:
                await handle_system_reboot(reboot_request)

                # Should have logged the warning
                mock_logger.warning.assert_called()


# =============================================================================
# Tests for System Shutdown Handler
# =============================================================================


class TestHandleSystemShutdown:
    """Tests for handle_system_shutdown handler."""

    @pytest.mark.asyncio
    async def test_shutdown_with_valid_params(
        self, shutdown_request: IPCRequest
    ) -> None:
        """Test shutdown handler with valid parameters."""
        with patch("mcp_raspi_ops.handlers.system._execute_power_command") as mock_exec:
            mock_exec.return_value = {"executed": True}

            result = await handle_system_shutdown(shutdown_request)

            assert result["executed"] is True
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args
            assert call_args.kwargs["delay_seconds"] == 10
            assert call_args.kwargs["reason"] == "Power saving"
            assert call_args.kwargs["operation"] == "system.shutdown"

    @pytest.mark.asyncio
    async def test_shutdown_uses_poweroff_command(
        self, shutdown_request: IPCRequest
    ) -> None:
        """Test shutdown uses poweroff command."""
        with patch("mcp_raspi_ops.handlers.system._execute_power_command") as mock_exec:
            mock_exec.return_value = {"executed": True}

            await handle_system_shutdown(shutdown_request)

            call_args = mock_exec.call_args
            # Should use SHUTDOWN_COMMAND (systemctl poweroff)
            assert call_args.kwargs["command"] == ["systemctl", "poweroff"]


# =============================================================================
# Tests for Handler Registration
# =============================================================================


class TestRegisterSystemHandlers:
    """Tests for register_system_handlers function."""

    def test_registers_both_handlers(self, registry: HandlerRegistry) -> None:
        """Test both reboot and shutdown handlers are registered."""
        register_system_handlers(registry)

        assert registry.has_handler("system.reboot")
        assert registry.has_handler("system.shutdown")

    def test_registered_handlers_are_callable(self, registry: HandlerRegistry) -> None:
        """Test registered handlers can be dispatched."""
        register_system_handlers(registry)

        operations = registry.get_operations()
        assert "system.reboot" in operations
        assert "system.shutdown" in operations

    @pytest.mark.asyncio
    async def test_dispatch_reboot(self, registry: HandlerRegistry) -> None:
        """Test dispatching to reboot handler."""
        register_system_handlers(registry)

        request = IPCRequest.create(
            operation="system.reboot",
            params={"delay_seconds": 0},
            request_id="test-req",
        )

        with patch("mcp_raspi_ops.handlers.system._execute_power_command") as mock_exec:
            mock_exec.return_value = {"executed": True}

            result = await registry.dispatch(request)
            assert result["executed"] is True

    @pytest.mark.asyncio
    async def test_dispatch_shutdown(self, registry: HandlerRegistry) -> None:
        """Test dispatching to shutdown handler."""
        register_system_handlers(registry)

        request = IPCRequest.create(
            operation="system.shutdown",
            params={"delay_seconds": 0},
            request_id="test-req",
        )

        with patch("mcp_raspi_ops.handlers.system._execute_power_command") as mock_exec:
            mock_exec.return_value = {"executed": True}

            result = await registry.dispatch(request)
            assert result["executed"] is True
