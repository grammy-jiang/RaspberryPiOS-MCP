"""
Tests for systemd restart functionality.

Tests cover:
- _run_systemctl function
- get_service_status function
- restart_service function
- stop_service function
- start_service function
- wait_for_service_active function
- ServiceManager class
- graceful_restart_for_update function
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_raspi.errors import UnavailableError
from mcp_raspi.updates.systemd_restart import (
    ServiceManager,
    ServiceRestartError,
    _run_systemctl,
    get_service_status,
    graceful_restart_for_update,
    reload_systemd_daemon,
    restart_service,
    start_service,
    stop_service,
    wait_for_service_active,
)

# =============================================================================
# _run_systemctl Tests
# =============================================================================


class TestRunSystemctl:
    """Tests for _run_systemctl function."""

    @pytest.mark.asyncio
    async def test_run_systemctl_success(self) -> None:
        """Test successful systemctl command."""

        async def mock_subprocess(*_args, **_kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"active", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            returncode, stdout, stderr = await _run_systemctl(
                "is-active", "test-service"
            )

            assert returncode == 0
            assert stdout == "active"
            assert stderr == ""

    @pytest.mark.asyncio
    async def test_run_systemctl_not_found(self) -> None:
        """Test systemctl not found raises UnavailableError."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("systemctl not found"),
        ):
            with pytest.raises(UnavailableError) as exc_info:
                await _run_systemctl("is-active", "test-service")

            assert "not available" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_run_systemctl_timeout(self) -> None:
        """Test systemctl timeout raises UnavailableError."""

        async def mock_subprocess(*_args, **_kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(side_effect=TimeoutError())
            return proc

        with (
            patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess),
            patch("asyncio.wait_for", side_effect=TimeoutError()),
        ):
            with pytest.raises(UnavailableError) as exc_info:
                await _run_systemctl("is-active", "test-service", timeout=0.1)

            assert "timed out" in exc_info.value.message


# =============================================================================
# get_service_status Tests
# =============================================================================


class TestGetServiceStatus:
    """Tests for get_service_status function."""

    @pytest.mark.asyncio
    async def test_get_status_active_service(self) -> None:
        """Test getting status of active service."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "active", ""),
        ):
            status = await get_service_status("test-service")

            assert status["status"] == "active"
            assert status["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_status_inactive_service(self) -> None:
        """Test getting status of inactive service."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(1, "inactive", ""),
        ):
            status = await get_service_status("test-service")

            assert status["status"] == "inactive"
            assert status["is_active"] is False

    @pytest.mark.asyncio
    async def test_get_status_systemctl_unavailable(self) -> None:
        """Test getting status when systemctl unavailable."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            side_effect=UnavailableError("systemctl not available"),
        ):
            status = await get_service_status("test-service")

            assert status["status"] == "unknown"
            assert status["is_active"] is False
            assert "error" in status


# =============================================================================
# restart_service Tests
# =============================================================================


class TestRestartService:
    """Tests for restart_service function."""

    @pytest.mark.asyncio
    async def test_restart_success(self) -> None:
        """Test successful service restart."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "", ""),
        ), patch(
            "mcp_raspi.updates.systemd_restart.wait_for_service_active",
            return_value=True,
        ):
            result = await restart_service("test-service")

            assert result is True

    @pytest.mark.asyncio
    async def test_restart_failure(self) -> None:
        """Test failed service restart."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(1, "", "Failed to restart"),
        ):
            with pytest.raises(ServiceRestartError) as exc_info:
                await restart_service("test-service")

            assert "Failed to restart" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_restart_without_wait(self) -> None:
        """Test restart without waiting for service."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "", ""),
        ):
            result = await restart_service("test-service", wait_for_start=False)

            assert result is True

    @pytest.mark.asyncio
    async def test_restart_service_not_active_after_restart(self) -> None:
        """Test restart when service doesn't become active."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "", ""),
        ), patch(
            "mcp_raspi.updates.systemd_restart.wait_for_service_active",
            return_value=False,
        ):
            result = await restart_service("test-service")

            assert result is False

    @pytest.mark.asyncio
    async def test_restart_systemctl_unavailable(self) -> None:
        """Test restart when systemctl unavailable returns True (test env)."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            side_effect=UnavailableError("systemctl not available"),
        ):
            result = await restart_service("test-service")

            assert result is True


# =============================================================================
# stop_service Tests
# =============================================================================


class TestStopService:
    """Tests for stop_service function."""

    @pytest.mark.asyncio
    async def test_stop_success(self) -> None:
        """Test successful service stop."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "", ""),
        ):
            result = await stop_service("test-service")

            assert result is True

    @pytest.mark.asyncio
    async def test_stop_failure(self) -> None:
        """Test failed service stop."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(1, "", "Failed to stop"),
        ):
            result = await stop_service("test-service")

            assert result is False

    @pytest.mark.asyncio
    async def test_stop_systemctl_unavailable(self) -> None:
        """Test stop when systemctl unavailable returns True (test env)."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            side_effect=UnavailableError("systemctl not available"),
        ):
            result = await stop_service("test-service")

            assert result is True


# =============================================================================
# start_service Tests
# =============================================================================


class TestStartService:
    """Tests for start_service function."""

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        """Test successful service start."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "", ""),
        ):
            result = await start_service("test-service")

            assert result is True

    @pytest.mark.asyncio
    async def test_start_failure(self) -> None:
        """Test failed service start."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(1, "", "Failed to start"),
        ):
            result = await start_service("test-service")

            assert result is False

    @pytest.mark.asyncio
    async def test_start_systemctl_unavailable(self) -> None:
        """Test start when systemctl unavailable returns True (test env)."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            side_effect=UnavailableError("systemctl not available"),
        ):
            result = await start_service("test-service")

            assert result is True


# =============================================================================
# wait_for_service_active Tests
# =============================================================================


class TestWaitForServiceActive:
    """Tests for wait_for_service_active function."""

    @pytest.mark.asyncio
    async def test_wait_returns_true_immediately(self) -> None:
        """Test wait returns True when service immediately active."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "active", ""),
        ):
            result = await wait_for_service_active(
                "test-service",
                timeout=5.0,
                poll_interval=0.1,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_wait_returns_false_on_timeout(self) -> None:
        """Test wait returns False on timeout."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(1, "inactive", ""),
        ):
            result = await wait_for_service_active(
                "test-service",
                timeout=0.2,
                poll_interval=0.1,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_wait_systemctl_unavailable(self) -> None:
        """Test wait returns True when systemctl unavailable (test env)."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            side_effect=UnavailableError("systemctl not available"),
        ):
            result = await wait_for_service_active(
                "test-service",
                timeout=5.0,
                poll_interval=0.1,
            )

            assert result is True


# =============================================================================
# reload_systemd_daemon Tests
# =============================================================================


class TestReloadSystemdDaemon:
    """Tests for reload_systemd_daemon function."""

    @pytest.mark.asyncio
    async def test_reload_success(self) -> None:
        """Test successful daemon reload."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(0, "", ""),
        ):
            result = await reload_systemd_daemon()

            assert result is True

    @pytest.mark.asyncio
    async def test_reload_failure(self) -> None:
        """Test failed daemon reload."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            return_value=(1, "", "Failed"),
        ):
            result = await reload_systemd_daemon()

            assert result is False

    @pytest.mark.asyncio
    async def test_reload_systemctl_unavailable(self) -> None:
        """Test reload when systemctl unavailable."""
        with patch(
            "mcp_raspi.updates.systemd_restart._run_systemctl",
            side_effect=UnavailableError("systemctl not available"),
        ):
            result = await reload_systemd_daemon()

            assert result is True


# =============================================================================
# ServiceManager Tests
# =============================================================================


class TestServiceManager:
    """Tests for ServiceManager class."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        manager = ServiceManager()

        assert manager.server_service == "mcp-raspi-server"
        assert manager.agent_service == "raspi-ops-agent"

    def test_init_with_custom_values(self) -> None:
        """Test initialization with custom values."""
        manager = ServiceManager(
            server_service="custom-server",
            agent_service="custom-agent",
        )

        assert manager.server_service == "custom-server"
        assert manager.agent_service == "custom-agent"

    @pytest.mark.asyncio
    async def test_restart_server(self) -> None:
        """Test restart_server method."""
        manager = ServiceManager()

        with patch(
            "mcp_raspi.updates.systemd_restart.restart_service",
            return_value=True,
        ) as mock_restart:
            result = await manager.restart_server()

            assert result is True
            mock_restart.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restart_agent(self) -> None:
        """Test restart_agent method."""
        manager = ServiceManager()

        with patch(
            "mcp_raspi.updates.systemd_restart.restart_service",
            return_value=True,
        ) as mock_restart:
            result = await manager.restart_agent()

            assert result is True
            mock_restart.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restart_all(self) -> None:
        """Test restart_all method."""
        manager = ServiceManager()

        with patch.object(
            manager, "restart_agent", return_value=True
        ) as mock_agent, patch.object(
            manager, "restart_server", return_value=True
        ) as mock_server:
            results = await manager.restart_all()

            assert results[manager.agent_service] is True
            assert results[manager.server_service] is True
            mock_agent.assert_awaited_once()
            mock_server.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_status(self) -> None:
        """Test get_status method."""
        manager = ServiceManager()

        with patch(
            "mcp_raspi.updates.systemd_restart.get_service_status",
            return_value={"status": "active", "is_active": True},
        ):
            status = await manager.get_status()

            assert manager.server_service in status
            assert manager.agent_service in status

    @pytest.mark.asyncio
    async def test_are_services_running_both_active(self) -> None:
        """Test are_services_running when both services active."""
        manager = ServiceManager()

        with patch.object(
            manager,
            "get_status",
            return_value={
                manager.server_service: {"is_active": True},
                manager.agent_service: {"is_active": True},
            },
        ):
            result = await manager.are_services_running()

            assert result is True

    @pytest.mark.asyncio
    async def test_are_services_running_one_inactive(self) -> None:
        """Test are_services_running when one service inactive."""
        manager = ServiceManager()

        with patch.object(
            manager,
            "get_status",
            return_value={
                manager.server_service: {"is_active": True},
                manager.agent_service: {"is_active": False},
            },
        ):
            result = await manager.are_services_running()

            assert result is False


# =============================================================================
# graceful_restart_for_update Tests
# =============================================================================


class TestGracefulRestartForUpdate:
    """Tests for graceful_restart_for_update function."""

    @pytest.mark.asyncio
    async def test_graceful_restart_success(self) -> None:
        """Test successful graceful restart."""
        manager_mock = AsyncMock()
        manager_mock.restart_all = AsyncMock(
            return_value={
                "mcp-raspi-server": True,
                "raspi-ops-agent": True,
            }
        )

        with patch(
            "mcp_raspi.updates.systemd_restart.ServiceManager",
            return_value=manager_mock,
        ):
            result = await graceful_restart_for_update(
                pre_restart_delay=0.01,
                post_restart_delay=0.01,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_graceful_restart_failure(self) -> None:
        """Test graceful restart with failure."""
        manager_mock = AsyncMock()
        manager_mock.restart_all = AsyncMock(
            return_value={
                "mcp-raspi-server": False,  # Failed
                "raspi-ops-agent": True,
            }
        )

        with patch(
            "mcp_raspi.updates.systemd_restart.ServiceManager",
            return_value=manager_mock,
        ):
            result = await graceful_restart_for_update(
                pre_restart_delay=0.01,
                post_restart_delay=0.01,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_graceful_restart_custom_services(self) -> None:
        """Test graceful restart with custom service names."""
        with patch(
            "mcp_raspi.updates.systemd_restart.ServiceManager"
        ) as mock_class:
            mock_instance = AsyncMock()
            mock_instance.restart_all = AsyncMock(
                return_value={
                    "custom-server": True,
                    "custom-agent": True,
                }
            )
            mock_class.return_value = mock_instance

            result = await graceful_restart_for_update(
                server_service="custom-server",
                agent_service="custom-agent",
                pre_restart_delay=0.01,
                post_restart_delay=0.01,
            )

            assert result is True
            mock_class.assert_called_once_with(
                server_service="custom-server",
                agent_service="custom-agent",
            )
