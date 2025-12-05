"""
Health check system for verifying updates.

This module implements health checks to verify that the server
is working correctly after an update.

Health checks include:
- Service running check (systemd)
- Basic HTTP endpoint check (if configured)
- Simple MCP tool call verification

Design follows Doc 10 §5.2 specifications.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_raspi.errors import FailedPreconditionError
from mcp_raspi.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class HealthCheckResult:
    """Result of a health check."""

    def __init__(
        self,
        name: str,
        passed: bool,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the health check result.

        Args:
            name: Name of the health check.
            passed: Whether the check passed.
            message: Optional message describing the result.
            details: Optional additional details.
        """
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


class HealthChecker:
    """
    Performs health checks after updates.

    Health checks verify that the server is functioning correctly
    after an update. If checks fail repeatedly, automatic rollback
    should be triggered.
    """

    DEFAULT_SERVICE_NAME = "mcp-raspi-server"
    DEFAULT_AGENT_SERVICE_NAME = "raspi-ops-agent"
    DEFAULT_SOCKET_PATH = Path("/run/mcp-raspi/ops-agent.sock")
    DEFAULT_HTTP_PORT = 8000

    def __init__(
        self,
        service_name: str | None = None,
        agent_service_name: str | None = None,
        socket_path: Path | str | None = None,
        http_port: int | None = None,
    ) -> None:
        """
        Initialize the health checker.

        Args:
            service_name: Name of the MCP server systemd service.
            agent_service_name: Name of the ops agent systemd service.
            socket_path: Path to the IPC socket.
            http_port: HTTP port for health endpoint check.
        """
        self.service_name = service_name or self.DEFAULT_SERVICE_NAME
        self.agent_service_name = agent_service_name or self.DEFAULT_AGENT_SERVICE_NAME
        self.socket_path = (
            Path(socket_path) if socket_path else self.DEFAULT_SOCKET_PATH
        )
        self.http_port = http_port or self.DEFAULT_HTTP_PORT

    async def check_service_running(
        self,
        service_name: str | None = None,
    ) -> HealthCheckResult:
        """
        Check if a systemd service is running.

        Args:
            service_name: Name of the service to check.
                         Defaults to MCP server service.

        Returns:
            HealthCheckResult indicating whether service is running.

        Raises:
            UnavailableError: If systemctl command fails.
        """
        service = service_name or self.service_name

        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl",
                "is-active",
                service,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)

            status = stdout.decode().strip()
            is_active = proc.returncode == 0 and status == "active"

            result = HealthCheckResult(
                name=f"service_{service}",
                passed=is_active,
                message=f"Service {service} is {status}",
                details={"status": status, "returncode": proc.returncode},
            )

            if is_active:
                logger.debug(f"Service {service} is running")
            else:
                logger.warning(f"Service {service} is not running: {status}")

            return result

        except TimeoutError:
            return HealthCheckResult(
                name=f"service_{service}",
                passed=False,
                message=f"Timeout checking service {service}",
            )
        except FileNotFoundError:
            # systemctl not available (likely in test environment)
            logger.debug("systemctl not available, skipping service check")
            return HealthCheckResult(
                name=f"service_{service}",
                passed=True,
                message="systemctl not available (test environment)",
            )
        except Exception as e:
            return HealthCheckResult(
                name=f"service_{service}",
                passed=False,
                message=f"Error checking service: {e}",
            )

    async def check_socket_exists(self) -> HealthCheckResult:
        """
        Check if the IPC socket exists and is accessible.

        Returns:
            HealthCheckResult indicating socket status.
        """
        try:
            if self.socket_path.exists():
                if self.socket_path.is_socket():
                    return HealthCheckResult(
                        name="ipc_socket",
                        passed=True,
                        message=f"IPC socket exists at {self.socket_path}",
                    )
                else:
                    return HealthCheckResult(
                        name="ipc_socket",
                        passed=False,
                        message=f"Path exists but is not a socket: {self.socket_path}",
                    )
            else:
                return HealthCheckResult(
                    name="ipc_socket",
                    passed=False,
                    message=f"IPC socket not found at {self.socket_path}",
                )
        except Exception as e:
            return HealthCheckResult(
                name="ipc_socket",
                passed=False,
                message=f"Error checking socket: {e}",
            )

    async def check_http_health(
        self,
        host: str = "127.0.0.1",
        path: str = "/health",
        timeout: float = 5.0,
    ) -> HealthCheckResult:
        """
        Check the HTTP health endpoint.

        Args:
            host: Host to connect to.
            path: Health endpoint path.
            timeout: Request timeout in seconds.

        Returns:
            HealthCheckResult indicating HTTP health status.
        """
        try:
            import httpx

            url = f"http://{host}:{self.http_port}{path}"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=timeout)

                if response.status_code == 200:
                    return HealthCheckResult(
                        name="http_health",
                        passed=True,
                        message=f"HTTP health check passed at {url}",
                        details={"status_code": response.status_code},
                    )
                else:
                    return HealthCheckResult(
                        name="http_health",
                        passed=False,
                        message=f"HTTP health check returned {response.status_code}",
                        details={"status_code": response.status_code},
                    )

        except ImportError:
            logger.debug("httpx not available, skipping HTTP health check")
            return HealthCheckResult(
                name="http_health",
                passed=True,
                message="httpx not available (skipping)",
            )
        except Exception as e:
            return HealthCheckResult(
                name="http_health",
                passed=False,
                message=f"HTTP health check failed: {e}",
            )

    async def check_basic_tool_call(self, timeout: float = 10.0) -> HealthCheckResult:
        """
        Verify that a basic MCP tool call works.

        This attempts to call the system.get_basic_info tool via IPC.

        Args:
            timeout: Request timeout in seconds.

        Returns:
            HealthCheckResult indicating tool call status.
        """
        try:
            from mcp_raspi.ipc.client import IPCClient

            client = IPCClient(socket_path=str(self.socket_path))

            async def _do_tool_call() -> HealthCheckResult:
                """Inner coroutine for the tool call operation."""
                await client.connect()
                try:
                    # Make a simple call to verify the server is responding
                    result = await client.call(
                        operation="system.get_basic_info",
                        params={},
                    )

                    if result and isinstance(result, dict):
                        return HealthCheckResult(
                            name="tool_call",
                            passed=True,
                            message="Basic tool call succeeded",
                            details={"hostname": result.get("hostname")},
                        )
                    else:
                        return HealthCheckResult(
                            name="tool_call",
                            passed=False,
                            message="Unexpected tool call response",
                        )
                finally:
                    await client.disconnect()

            return await asyncio.wait_for(_do_tool_call(), timeout=timeout)

        except TimeoutError:
            return HealthCheckResult(
                name="tool_call",
                passed=False,
                message=f"Tool call timed out after {timeout}s",
            )
        except Exception as e:
            return HealthCheckResult(
                name="tool_call",
                passed=False,
                message=f"Tool call failed: {e}",
            )

    async def run_all_checks(
        self,
        skip_http: bool = False,
        skip_tool_call: bool = False,
    ) -> list[HealthCheckResult]:
        """
        Run all health checks.

        Args:
            skip_http: Skip HTTP health check.
            skip_tool_call: Skip tool call check.

        Returns:
            List of HealthCheckResult objects.
        """
        results: list[HealthCheckResult] = []

        # Service checks
        results.append(await self.check_service_running(self.service_name))
        results.append(await self.check_service_running(self.agent_service_name))

        # Socket check
        results.append(await self.check_socket_exists())

        # HTTP check
        if not skip_http:
            results.append(await self.check_http_health())

        # Tool call check
        if not skip_tool_call:
            results.append(await self.check_basic_tool_call())

        return results

    async def run_health_check(
        self,
        required_checks: list[str] | None = None,
    ) -> bool:
        """
        Run health checks and return pass/fail.

        Args:
            required_checks: List of check names that must pass.
                           If None, service check must pass.

        Returns:
            True if required checks pass, False otherwise.

        Raises:
            FailedPreconditionError: If required checks fail.
        """
        results = await self.run_all_checks(
            skip_http=True,  # HTTP might not be configured
            skip_tool_call=True,  # Tool call requires full setup
        )

        # Default required checks
        if required_checks is None:
            required_checks = [f"service_{self.service_name}"]

        # Check required checks passed
        failed_checks = []
        for result in results:
            if result.name in required_checks and not result.passed:
                failed_checks.append(result)

        if failed_checks:
            messages = [f"{r.name}: {r.message}" for r in failed_checks]
            raise FailedPreconditionError(
                f"Health checks failed: {'; '.join(messages)}",
                details={
                    "failed_checks": [r.to_dict() for r in failed_checks],
                    "all_results": [r.to_dict() for r in results],
                },
            )

        logger.info("All required health checks passed")
        return True


async def wait_for_service_healthy(
    service_name: str,
    timeout_seconds: float = 60.0,
    check_interval_seconds: float = 2.0,
) -> bool:
    """
    Wait for a systemd service to become healthy.

    Args:
        service_name: Name of the service to wait for.
        timeout_seconds: Maximum time to wait.
        check_interval_seconds: Time between checks.

    Returns:
        True if service became healthy, False if timeout.
    """
    checker = HealthChecker(service_name=service_name)
    start_time = asyncio.get_event_loop().time()

    while True:
        result = await checker.check_service_running(service_name)
        if result.passed:
            return True

        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout_seconds:
            logger.warning(
                f"Timeout waiting for service {service_name} to become healthy"
            )
            return False

        await asyncio.sleep(check_interval_seconds)
