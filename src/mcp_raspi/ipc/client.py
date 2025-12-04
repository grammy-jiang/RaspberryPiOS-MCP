"""
IPC Client for communication with the Privileged Agent.

This module implements the OpsAgentClient (IPCClient) class that handles
communication with the privileged operations agent over Unix domain sockets.

Design follows Doc 02 §6 (Privileged Agent), §7 (IPC Protocol), and
§12 (IPC Robustness).

Features:
- Automatic reconnection with exponential backoff
- Request timeout handling
- Connection state management
- Health checks
"""

from __future__ import annotations

import asyncio
import json
from enum import Enum
from typing import TYPE_CHECKING, Any

from mcp_raspi.ipc.protocol import (
    DEFAULT_SOCKET_PATH,
    DEFAULT_TIMEOUT,
    MAX_MESSAGE_SIZE,
    IPCConnectionError,
    IPCProtocolError,
    IPCRequest,
    IPCResponse,
    IPCTimeoutError,
    IPCUnavailableError,
    RequestIDGenerator,
)
from mcp_raspi.logging import get_logger

if TYPE_CHECKING:
    from mcp_raspi.config import IPCConfig

logger = get_logger(__name__)


class IPCConnectionState(Enum):
    """IPC connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class IPCClient:
    """
    IPC client for communication with the privileged agent.

    This client manages the connection to the privileged agent over a Unix
    domain socket and handles automatic reconnection on failure.

    Attributes:
        socket_path: Path to the Unix domain socket.
        state: Current connection state.

    Example:
        >>> client = IPCClient("/run/mcp-raspi/ops-agent.sock")
        >>> await client.connect()
        >>> result = await client.call("ping", {})
        >>> print(result)
        {"status": "ok", "data": {"pong": True}}
    """

    def __init__(
        self,
        socket_path: str | None = None,
        timeout: float | None = None,
        reconnect_enabled: bool = True,
        reconnect_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
        reconnect_backoff_multiplier: float = 2.0,
        reconnect_max_attempts: int = 10,
    ) -> None:
        """
        Initialize the IPC client.

        Args:
            socket_path: Path to the Unix domain socket.
            timeout: Default request timeout in seconds.
            reconnect_enabled: Whether to auto-reconnect on failure.
            reconnect_delay: Initial delay before reconnection attempts.
            reconnect_max_delay: Maximum delay between reconnection attempts.
            reconnect_backoff_multiplier: Multiplier for exponential backoff.
            reconnect_max_attempts: Maximum reconnection attempts (0 = infinite).
        """
        self.socket_path = socket_path or DEFAULT_SOCKET_PATH
        self.default_timeout = timeout or DEFAULT_TIMEOUT
        self.state = IPCConnectionState.DISCONNECTED

        # Reconnection settings
        self.reconnect_enabled = reconnect_enabled
        self.reconnect_delay = reconnect_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.reconnect_backoff_multiplier = reconnect_backoff_multiplier
        self.reconnect_max_attempts = reconnect_max_attempts

        # Connection tracking
        self.connection_attempts = 0
        self.connected_at: float | None = None
        self.disconnected_at: float | None = None

        # Stream objects
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

        # Request ID generator
        self._id_generator = RequestIDGenerator()

        # Lock for connection operations
        self._connect_lock = asyncio.Lock()

        # Pending requests
        self._pending_requests: dict[str, asyncio.Future[IPCResponse]] = {}

    @classmethod
    def from_config(cls, config: IPCConfig) -> IPCClient:
        """
        Create an IPC client from configuration.

        Args:
            config: IPC configuration from AppConfig.

        Returns:
            Configured IPCClient instance.
        """
        return cls(
            socket_path=config.socket_path,
            timeout=float(config.request_timeout_seconds),
        )

    async def connect(self) -> bool:
        """
        Connect to the privileged agent.

        Returns:
            True if connected successfully, False otherwise.
        """
        async with self._connect_lock:
            if self.state == IPCConnectionState.CONNECTED:
                return True

            self.state = IPCConnectionState.CONNECTING
            self.connection_attempts += 1

            try:
                # Open Unix domain socket connection
                self._reader, self._writer = await asyncio.open_unix_connection(
                    self.socket_path
                )

                self.state = IPCConnectionState.CONNECTED
                self.connected_at = asyncio.get_event_loop().time()
                self.connection_attempts = 0

                logger.info(
                    "IPC connected to privileged agent",
                    extra={"socket_path": self.socket_path},
                )
                return True

            except FileNotFoundError:
                logger.error(
                    "IPC socket not found",
                    extra={
                        "socket_path": self.socket_path,
                        "attempt": self.connection_attempts,
                    },
                )
                self.state = IPCConnectionState.DISCONNECTED
                return False

            except PermissionError:
                logger.error(
                    "IPC socket permission denied",
                    extra={
                        "socket_path": self.socket_path,
                        "attempt": self.connection_attempts,
                    },
                )
                self.state = IPCConnectionState.DISCONNECTED
                return False

            except Exception as e:
                logger.error(
                    "IPC connection failed",
                    extra={
                        "error": str(e),
                        "socket_path": self.socket_path,
                        "attempt": self.connection_attempts,
                    },
                )
                self.state = IPCConnectionState.DISCONNECTED
                return False

    async def ensure_connected(self) -> None:
        """
        Ensure connection is active, reconnect if necessary.

        Raises:
            IPCUnavailableError: If connection cannot be established.
        """
        if self.state == IPCConnectionState.CONNECTED:
            return

        if self.reconnect_enabled:
            success = await self._reconnect_with_backoff()
            if not success:
                raise IPCUnavailableError(
                    f"Privileged agent unavailable after {self.connection_attempts} attempts",
                    details={"socket_path": self.socket_path},
                )
        else:
            if not await self.connect():
                raise IPCUnavailableError(
                    "Privileged agent unavailable",
                    details={"socket_path": self.socket_path},
                )

    async def _reconnect_with_backoff(self) -> bool:
        """
        Reconnect with exponential backoff.

        Returns:
            True if reconnected successfully, False if max attempts exceeded.
        """
        self.state = IPCConnectionState.RECONNECTING
        delay = self.reconnect_delay

        while True:
            # Check max attempts
            if (
                self.reconnect_max_attempts > 0
                and self.connection_attempts >= self.reconnect_max_attempts
            ):
                logger.error(
                    "IPC reconnection failed - max attempts exceeded",
                    extra={"max_attempts": self.reconnect_max_attempts},
                )
                self.state = IPCConnectionState.FAILED
                return False

            # Wait before retry
            logger.info(
                "IPC reconnecting",
                extra={
                    "delay_seconds": delay,
                    "attempt": self.connection_attempts + 1,
                },
            )
            await asyncio.sleep(delay)

            # Attempt connection
            if await self.connect():
                logger.info("IPC reconnection successful")
                return True

            # Exponential backoff
            delay = min(
                delay * self.reconnect_backoff_multiplier,
                self.reconnect_max_delay,
            )

    async def call(
        self,
        operation: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Call a privileged agent operation.

        Args:
            operation: Operation name (e.g., "gpio.write", "ping").
            params: Operation parameters.
            timeout: Request timeout in seconds (uses default if not provided).

        Returns:
            Operation result data.

        Raises:
            IPCUnavailableError: Agent unavailable.
            IPCTimeoutError: Request timed out.
            IPCProtocolError: Protocol error.
            IPCError: Other IPC errors.
        """
        timeout = timeout or self.default_timeout
        params = params or {}

        # Ensure connected
        await self.ensure_connected()

        # Generate request
        request_id = self._id_generator.generate()
        request = IPCRequest.create(
            operation=operation,
            params=params,
            request_id=request_id,
        )

        try:
            # Send request
            await self._send(request)

            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(
                    self._receive(request_id),
                    timeout=timeout,
                )

                # Handle response
                if response.is_success:
                    return response.data or {}
                else:
                    error = response.error
                    if error:
                        raise IPCProtocolError(
                            error.message,
                            details={"code": error.code, **error.details},
                        )
                    else:
                        raise IPCProtocolError("Unknown error from agent")

            except TimeoutError:
                logger.error(
                    "IPC request timeout",
                    extra={
                        "operation": operation,
                        "request_id": request_id,
                        "timeout": timeout,
                    },
                )
                # Mark connection as potentially dead
                await self._mark_connection_dead()
                raise IPCTimeoutError(
                    f"IPC request timed out after {timeout}s",
                    details={"operation": operation, "request_id": request_id},
                ) from None

        except (ConnectionError, BrokenPipeError, OSError) as e:
            logger.warning("IPC connection lost", extra={"error": str(e)})
            await self._mark_connection_dead()

            # Retry once after reconnection (non-recursive to prevent infinite recursion)
            if self.reconnect_enabled and await self._reconnect_with_backoff():
                logger.info("Retrying IPC request after reconnection")
                # Re-send the request without recursive call protection
                # to avoid stack overflow on repeated failures
                await self.ensure_connected()
                new_request_id = self._id_generator.generate()
                new_request = IPCRequest.create(
                    operation=operation,
                    params=params,
                    request_id=new_request_id,
                )
                try:
                    await self._send(new_request)
                    response = await asyncio.wait_for(
                        self._receive(new_request_id),
                        timeout=timeout,
                    )
                    if response.is_success:
                        return response.data or {}
                    else:
                        error = response.error
                        if error:
                            raise IPCProtocolError(
                                error.message,
                                details={"code": error.code, **error.details},
                            )
                        else:
                            raise IPCProtocolError("Unknown error from agent")
                finally:
                    self._id_generator.mark_completed(new_request_id)

            raise IPCUnavailableError(
                "Privileged agent unavailable",
                details={"socket_path": self.socket_path},
            ) from e

        finally:
            # Clean up request ID tracking
            self._id_generator.mark_completed(request_id)

    async def _send(self, request: IPCRequest) -> None:
        """
        Send a request to the agent.

        Args:
            request: The request to send.

        Raises:
            IPCConnectionError: If not connected or send fails.
        """
        if self._writer is None:
            raise IPCConnectionError("Not connected to agent")

        # Serialize to JSON
        message_bytes = request.to_json().encode("utf-8")

        # Check size
        if len(message_bytes) > MAX_MESSAGE_SIZE:
            raise IPCProtocolError(
                f"Request too large: {len(message_bytes)} bytes",
                details={"max_size": MAX_MESSAGE_SIZE},
            )

        # Write length prefix (4 bytes big-endian) + message
        length_prefix = len(message_bytes).to_bytes(4, byteorder="big")
        self._writer.write(length_prefix + message_bytes)
        await self._writer.drain()

        logger.debug(
            "IPC request sent",
            extra={
                "request_id": request.id,
                "operation": request.operation,
                "size": len(message_bytes),
            },
        )

    async def _receive(self, request_id: str) -> IPCResponse:
        """
        Receive a response from the agent.

        Args:
            request_id: Expected request ID.

        Returns:
            The response from the agent.

        Raises:
            IPCConnectionError: If not connected or receive fails.
            IPCProtocolError: If response is invalid.
        """
        if self._reader is None:
            raise IPCConnectionError("Not connected to agent")

        # Read length prefix
        length_bytes = await self._reader.readexactly(4)
        length = int.from_bytes(length_bytes, byteorder="big")

        # Validate length
        if length > MAX_MESSAGE_SIZE:
            raise IPCProtocolError(
                f"Response too large: {length} bytes",
                details={"max_size": MAX_MESSAGE_SIZE},
            )

        # Read message
        message_bytes = await self._reader.readexactly(length)
        message_json = message_bytes.decode("utf-8")

        # Parse response
        try:
            response = IPCResponse.from_json(message_json)
        except json.JSONDecodeError as e:
            raise IPCProtocolError(
                f"Invalid JSON response: {e}",
                details={"raw": message_json[:100]},
            ) from e

        # Validate request ID
        if response.id != request_id:
            raise IPCProtocolError(
                f"Response ID mismatch: expected {request_id}, got {response.id}"
            )

        logger.debug(
            "IPC response received",
            extra={
                "request_id": response.id,
                "status": response.status,
                "size": len(message_bytes),
            },
        )

        return response

    async def _mark_connection_dead(self) -> None:
        """Mark connection as dead and clean up."""
        self.state = IPCConnectionState.DISCONNECTED
        self.disconnected_at = asyncio.get_event_loop().time()

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                # Ignore exceptions during cleanup, but log for diagnostics.
                logger.warning(
                    "Exception during IPC connection cleanup (ignored)",
                    extra={"error": str(e)},
                )

        self._reader = None
        self._writer = None

    async def disconnect(self) -> None:
        """Gracefully disconnect from the agent."""
        if self.state != IPCConnectionState.CONNECTED:
            return

        await self._mark_connection_dead()
        logger.info("IPC disconnected from privileged agent")

    async def health_check(self) -> bool:
        """
        Check if IPC connection is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        if self.state != IPCConnectionState.CONNECTED:
            return False

        try:
            result = await self.call("ping", {}, timeout=5.0)
            return result.get("pong", False) is True
        except Exception as e:
            logger.warning("IPC health check failed", extra={"error": str(e)})
            return False

    async def __aenter__(self) -> IPCClient:
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        await self.disconnect()


# Alias for backward compatibility with design docs
OpsAgentClient = IPCClient
