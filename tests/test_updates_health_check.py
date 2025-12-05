"""
Tests for health check functionality.

Tests cover:
- HealthCheckResult model
- HealthChecker class
- Individual health check methods
- wait_for_service_healthy function
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_raspi.updates.health_check import (
    HealthChecker,
    HealthCheckResult,
    wait_for_service_healthy,
)

# =============================================================================
# HealthCheckResult Tests
# =============================================================================


class TestHealthCheckResult:
    """Tests for HealthCheckResult class."""

    def test_create_passing_result(self) -> None:
        """Test creating a passing health check result."""
        result = HealthCheckResult(
            name="test_check",
            passed=True,
            message="Check passed",
        )

        assert result.name == "test_check"
        assert result.passed is True
        assert result.message == "Check passed"
        assert result.details == {}

    def test_create_failing_result(self) -> None:
        """Test creating a failing health check result."""
        result = HealthCheckResult(
            name="test_check",
            passed=False,
            message="Check failed",
            details={"error": "Connection refused"},
        )

        assert result.passed is False
        assert result.details["error"] == "Connection refused"

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = HealthCheckResult(
            name="my_check",
            passed=True,
            message="OK",
            details={"latency_ms": 10},
        )

        data = result.to_dict()

        assert data["name"] == "my_check"
        assert data["passed"] is True
        assert data["message"] == "OK"
        assert data["details"]["latency_ms"] == 10


# =============================================================================
# HealthChecker Initialization Tests
# =============================================================================


class TestHealthCheckerInit:
    """Tests for HealthChecker initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        checker = HealthChecker()

        assert checker.service_name == "mcp-raspi-server"
        assert checker.agent_service_name == "raspi-ops-agent"
        assert checker.socket_path == Path("/run/mcp-raspi/ops-agent.sock")
        assert checker.http_port == 8000

    def test_init_with_custom_values(self) -> None:
        """Test initialization with custom values."""
        checker = HealthChecker(
            service_name="custom-server",
            agent_service_name="custom-agent",
            socket_path="/tmp/custom.sock",
            http_port=9000,
        )

        assert checker.service_name == "custom-server"
        assert checker.agent_service_name == "custom-agent"
        assert checker.socket_path == Path("/tmp/custom.sock")
        assert checker.http_port == 9000


# =============================================================================
# Service Running Check Tests
# =============================================================================


class TestCheckServiceRunning:
    """Tests for check_service_running method."""

    @pytest.mark.asyncio
    async def test_check_active_service(self) -> None:
        """Test checking an active service."""
        checker = HealthChecker()

        async def mock_subprocess(*_args, **_kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"active", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            result = await checker.check_service_running("test-service")

            assert result.passed is True
            assert "active" in result.message

    @pytest.mark.asyncio
    async def test_check_inactive_service(self) -> None:
        """Test checking an inactive service."""
        checker = HealthChecker()

        async def mock_subprocess(*_args, **_kwargs):
            proc = MagicMock()
            proc.returncode = 1
            proc.communicate = AsyncMock(return_value=(b"inactive", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            result = await checker.check_service_running("test-service")

            assert result.passed is False
            assert "inactive" in result.message

    @pytest.mark.asyncio
    async def test_check_service_systemctl_not_found(self) -> None:
        """Test that missing systemctl returns passing result (test env)."""
        checker = HealthChecker()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("systemctl not found"),
        ):
            result = await checker.check_service_running("test-service")

            # In test environment without systemctl, should pass
            assert result.passed is True
            assert "not available" in result.message

    @pytest.mark.asyncio
    async def test_check_service_timeout(self) -> None:
        """Test handling of check timeout."""
        checker = HealthChecker()

        async def slow_subprocess(*_args, **_kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(side_effect=TimeoutError())
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=slow_subprocess):
            # Use asyncio.wait_for to force timeout
            result = await checker.check_service_running("test-service")

            # Even with error, should return a result
            assert result.passed is False
            assert "Timeout" in result.message


# =============================================================================
# Socket Check Tests
# =============================================================================


class TestCheckSocketExists:
    """Tests for check_socket_exists method."""

    @pytest.mark.asyncio
    async def test_socket_exists(self) -> None:
        """Test when socket file exists and is a socket."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import socket as sock

            socket_path = Path(tmpdir) / "test.sock"

            # Create actual Unix socket
            s = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
            try:
                s.bind(str(socket_path))

                checker = HealthChecker(socket_path=socket_path)
                result = await checker.check_socket_exists()

                assert result.passed is True
            finally:
                s.close()
                socket_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_socket_not_exists(self) -> None:
        """Test when socket file doesn't exist."""
        checker = HealthChecker(socket_path="/nonexistent/socket.sock")
        result = await checker.check_socket_exists()

        assert result.passed is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_socket_is_regular_file(self) -> None:
        """Test when path exists but is not a socket."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "not_a_socket"
            file_path.touch()

            checker = HealthChecker(socket_path=file_path)
            result = await checker.check_socket_exists()

            assert result.passed is False
            assert "not a socket" in result.message


# =============================================================================
# HTTP Health Check Tests
# =============================================================================


class TestCheckHttpHealth:
    """Tests for check_http_health method."""

    @pytest.mark.asyncio
    async def test_http_health_success(self) -> None:
        """Test successful HTTP health check."""
        checker = HealthChecker(http_port=8080)

        # Mock httpx client
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await checker.check_http_health()

            assert result.passed is True
            assert result.details["status_code"] == 200

    @pytest.mark.asyncio
    async def test_http_health_non_200(self) -> None:
        """Test HTTP health check with non-200 response."""
        checker = HealthChecker()

        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await checker.check_http_health()

            assert result.passed is False
            assert "503" in result.message

    @pytest.mark.asyncio
    async def test_http_health_connection_error(self) -> None:
        """Test HTTP health check with connection error."""
        checker = HealthChecker()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await checker.check_http_health()

            assert result.passed is False
            assert "failed" in result.message.lower()


# =============================================================================
# Tool Call Check Tests
# =============================================================================


class TestCheckBasicToolCall:
    """Tests for check_basic_tool_call method."""

    @pytest.mark.asyncio
    async def test_tool_call_success(self) -> None:
        """Test successful tool call check."""
        checker = HealthChecker()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.call = AsyncMock(return_value={"hostname": "test-pi"})

        with patch("mcp_raspi.ipc.client.IPCClient", return_value=mock_client):
            result = await checker.check_basic_tool_call(timeout=5.0)

            assert result.passed is True
            assert result.details["hostname"] == "test-pi"

    @pytest.mark.asyncio
    async def test_tool_call_timeout(self) -> None:
        """Test tool call check with timeout."""
        checker = HealthChecker()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=TimeoutError())

        with patch("mcp_raspi.ipc.client.IPCClient", return_value=mock_client):
            result = await checker.check_basic_tool_call(timeout=0.1)

            assert result.passed is False
            assert "timed out" in result.message or "failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_tool_call_unexpected_response(self) -> None:
        """Test tool call with unexpected response."""
        checker = HealthChecker()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.call = AsyncMock(return_value=None)  # Unexpected response

        with patch("mcp_raspi.ipc.client.IPCClient", return_value=mock_client):
            result = await checker.check_basic_tool_call()

            assert result.passed is False
            assert "Unexpected" in result.message


# =============================================================================
# Run All Checks Tests
# =============================================================================


class TestRunAllChecks:
    """Tests for run_all_checks method."""

    @pytest.mark.asyncio
    async def test_run_all_checks_returns_list(self) -> None:
        """Test that run_all_checks returns a list of results."""
        checker = HealthChecker()

        # Mock all the individual checks
        with (
            patch.object(
                checker,
                "check_service_running",
                return_value=HealthCheckResult(
                    name="service", passed=True, message="OK"
                ),
            ),
            patch.object(
                checker,
                "check_socket_exists",
                return_value=HealthCheckResult(
                    name="socket", passed=True, message="OK"
                ),
            ),
            patch.object(
                checker,
                "check_http_health",
                return_value=HealthCheckResult(name="http", passed=True, message="OK"),
            ),
            patch.object(
                checker,
                "check_basic_tool_call",
                return_value=HealthCheckResult(name="tool", passed=True, message="OK"),
            ),
        ):
            results = await checker.run_all_checks()

            assert isinstance(results, list)
            assert len(results) >= 3  # At least service checks + socket

    @pytest.mark.asyncio
    async def test_run_all_checks_skip_http(self) -> None:
        """Test that run_all_checks can skip HTTP check."""
        checker = HealthChecker()

        with (
            patch.object(
                checker,
                "check_service_running",
                return_value=HealthCheckResult(
                    name="service", passed=True, message="OK"
                ),
            ),
            patch.object(
                checker,
                "check_socket_exists",
                return_value=HealthCheckResult(
                    name="socket", passed=True, message="OK"
                ),
            ),
            patch.object(checker, "check_http_health") as mock_http,
            patch.object(
                checker,
                "check_basic_tool_call",
                return_value=HealthCheckResult(name="tool", passed=True, message="OK"),
            ),
        ):
            await checker.run_all_checks(skip_http=True)

            mock_http.assert_not_called()


# =============================================================================
# Run Health Check Tests
# =============================================================================


class TestRunHealthCheck:
    """Tests for run_health_check method."""

    @pytest.mark.asyncio
    async def test_run_health_check_success(self) -> None:
        """Test successful health check run."""
        checker = HealthChecker()

        with patch.object(
            checker,
            "run_all_checks",
            return_value=[
                HealthCheckResult(
                    name="service_mcp-raspi-server",
                    passed=True,
                    message="Service running",
                ),
            ],
        ):
            result = await checker.run_health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_run_health_check_failure(self) -> None:
        """Test health check failure."""
        from mcp_raspi.errors import FailedPreconditionError

        checker = HealthChecker()

        with patch.object(
            checker,
            "run_all_checks",
            return_value=[
                HealthCheckResult(
                    name="service_mcp-raspi-server",
                    passed=False,
                    message="Service not running",
                ),
            ],
        ):
            with pytest.raises(FailedPreconditionError) as exc_info:
                await checker.run_health_check()

            assert "Health checks failed" in exc_info.value.message


# =============================================================================
# wait_for_service_healthy Tests
# =============================================================================


class TestWaitForServiceHealthy:
    """Tests for wait_for_service_healthy function."""

    @pytest.mark.asyncio
    async def test_wait_returns_true_when_service_active(self) -> None:
        """Test that wait returns True when service becomes active."""
        with patch(
            "mcp_raspi.updates.health_check.HealthChecker.check_service_running",
            return_value=HealthCheckResult(
                name="service_test", passed=True, message="active"
            ),
        ):
            result = await wait_for_service_healthy(
                "test-service",
                timeout_seconds=5.0,
                check_interval_seconds=0.1,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_wait_returns_false_on_timeout(self) -> None:
        """Test that wait returns False on timeout."""
        with patch(
            "mcp_raspi.updates.health_check.HealthChecker.check_service_running",
            return_value=HealthCheckResult(
                name="service_test", passed=False, message="inactive"
            ),
        ):
            result = await wait_for_service_healthy(
                "test-service",
                timeout_seconds=0.2,
                check_interval_seconds=0.1,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_wait_retries_until_active(self) -> None:
        """Test that wait retries until service becomes active."""
        call_count = 0

        async def mock_check(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return HealthCheckResult(
                    name="service_test", passed=False, message="inactive"
                )
            return HealthCheckResult(
                name="service_test", passed=True, message="active"
            )

        with patch(
            "mcp_raspi.updates.health_check.HealthChecker.check_service_running",
            side_effect=mock_check,
        ):
            result = await wait_for_service_healthy(
                "test-service",
                timeout_seconds=5.0,
                check_interval_seconds=0.1,
            )

            assert result is True
            assert call_count >= 3
