"""
Tests for the IPC client module.

Tests the IPCClient class and its connection management.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_raspi.ipc.client import IPCClient, IPCConnectionState, OpsAgentClient
from mcp_raspi.ipc.protocol import (
    IPCProtocolError,
    IPCResponse,
    IPCTimeoutError,
    IPCUnavailableError,
)

# =============================================================================
# IPCConnectionState Tests
# =============================================================================


class TestIPCConnectionState:
    """Tests for IPCConnectionState enum."""

    def test_connection_states_exist(self) -> None:
        """Test that all expected states exist."""
        assert IPCConnectionState.DISCONNECTED.value == "disconnected"
        assert IPCConnectionState.CONNECTING.value == "connecting"
        assert IPCConnectionState.CONNECTED.value == "connected"
        assert IPCConnectionState.RECONNECTING.value == "reconnecting"
        assert IPCConnectionState.FAILED.value == "failed"


# =============================================================================
# IPCClient Initialization Tests
# =============================================================================


class TestIPCClientInit:
    """Tests for IPCClient initialization."""

    def test_default_initialization(self) -> None:
        """Test client initialization with defaults."""
        client = IPCClient()
        assert client.socket_path == "/run/mcp-raspi/ops-agent.sock"
        assert client.default_timeout == 30.0
        assert client.state == IPCConnectionState.DISCONNECTED
        assert client.reconnect_enabled is True
        assert client.reconnect_max_attempts == 10

    def test_custom_initialization(self) -> None:
        """Test client initialization with custom values."""
        client = IPCClient(
            socket_path="/tmp/test.sock",
            timeout=60.0,
            reconnect_enabled=False,
            reconnect_delay=2.0,
            reconnect_max_delay=60.0,
            reconnect_backoff_multiplier=3.0,
            reconnect_max_attempts=5,
        )
        assert client.socket_path == "/tmp/test.sock"
        assert client.default_timeout == 60.0
        assert client.reconnect_enabled is False
        assert client.reconnect_delay == 2.0
        assert client.reconnect_max_delay == 60.0
        assert client.reconnect_backoff_multiplier == 3.0
        assert client.reconnect_max_attempts == 5

    def test_from_config(self) -> None:
        """Test client creation from config."""
        # Create a mock config
        config = MagicMock()
        config.socket_path = "/test/socket.sock"
        config.request_timeout_seconds = 45

        client = IPCClient.from_config(config)
        assert client.socket_path == "/test/socket.sock"
        assert client.default_timeout == 45.0


# =============================================================================
# IPCClient Connection Tests
# =============================================================================


class TestIPCClientConnection:
    """Tests for IPCClient connection handling."""

    async def test_connect_socket_not_found(self) -> None:
        """Test connection failure when socket doesn't exist."""
        client = IPCClient(socket_path="/nonexistent/socket.sock")
        result = await client.connect()
        assert result is False
        assert client.state == IPCConnectionState.DISCONNECTED

    async def test_connect_success_with_mock(self) -> None:
        """Test successful connection with mocked socket."""
        client = IPCClient(socket_path="/tmp/test.sock")

        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)

        with patch("asyncio.open_unix_connection") as mock_connect:
            mock_connect.return_value = (mock_reader, mock_writer)

            result = await client.connect()

            assert result is True
            assert client.state == IPCConnectionState.CONNECTED
            assert client._reader is mock_reader
            assert client._writer is mock_writer
            mock_connect.assert_called_once_with("/tmp/test.sock")

    async def test_connect_already_connected(self) -> None:
        """Test that calling connect when already connected returns True."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED

        result = await client.connect()
        assert result is True

    async def test_disconnect(self) -> None:
        """Test disconnect."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED
        mock_writer = AsyncMock()
        client._writer = mock_writer

        await client.disconnect()

        assert client.state == IPCConnectionState.DISCONNECTED
        assert client._reader is None
        assert client._writer is None
        mock_writer.close.assert_called_once()

    async def test_disconnect_when_not_connected(self) -> None:
        """Test disconnect when not connected does nothing."""
        client = IPCClient()
        assert client.state == IPCConnectionState.DISCONNECTED

        # Should not raise
        await client.disconnect()
        assert client.state == IPCConnectionState.DISCONNECTED


# =============================================================================
# IPCClient ensure_connected Tests
# =============================================================================


class TestIPCClientEnsureConnected:
    """Tests for ensure_connected method."""

    async def test_ensure_connected_already_connected(self) -> None:
        """Test ensure_connected when already connected."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED

        # Should not raise or try to connect
        await client.ensure_connected()

    async def test_ensure_connected_without_reconnect(self) -> None:
        """Test ensure_connected without reconnect enabled."""
        client = IPCClient(
            socket_path="/nonexistent.sock",
            reconnect_enabled=False,
        )

        with pytest.raises(IPCUnavailableError) as exc_info:
            await client.ensure_connected()

        assert "unavailable" in str(exc_info.value).lower()

    async def test_ensure_connected_reconnect_fails(self) -> None:
        """Test ensure_connected when reconnection fails."""
        client = IPCClient(
            socket_path="/nonexistent.sock",
            reconnect_enabled=True,
            reconnect_delay=0.01,  # Fast for testing
            reconnect_max_attempts=2,
        )

        with pytest.raises(IPCUnavailableError) as exc_info:
            await client.ensure_connected()

        assert "unavailable" in str(exc_info.value).lower()


# =============================================================================
# IPCClient Call Tests
# =============================================================================


class TestIPCClientCall:
    """Tests for the call method."""

    async def test_call_not_connected_raises(self) -> None:
        """Test that call raises when not connected and cannot reconnect."""
        client = IPCClient(
            socket_path="/nonexistent.sock",
            reconnect_enabled=False,
        )

        with pytest.raises(IPCUnavailableError):
            await client.call("ping", {})

    async def test_call_success_with_mock(self) -> None:
        """Test successful call with mocked connection."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED

        # Mock reader/writer
        mock_writer = AsyncMock()
        mock_reader = AsyncMock()

        # Create a valid response
        response = IPCResponse.success("test-id", {"pong": True})
        response_bytes = response.to_json().encode("utf-8")
        length_prefix = len(response_bytes).to_bytes(4, byteorder="big")

        mock_reader.readexactly = AsyncMock(side_effect=[length_prefix, response_bytes])

        client._reader = mock_reader
        client._writer = mock_writer

        # Patch the ID generator to return a known ID
        client._id_generator.generate = MagicMock(return_value="test-id")

        result = await client.call("ping", {})

        assert result == {"pong": True}
        mock_writer.write.assert_called_once()
        mock_writer.drain.assert_called_once()

    async def test_call_with_error_response(self) -> None:
        """Test call that receives an error response."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED

        mock_writer = AsyncMock()
        mock_reader = AsyncMock()

        # Create an error response
        response = IPCResponse.create_error(
            request_id="test-id",
            code="invalid_argument",
            message="Bad parameter",
        )
        response_bytes = response.to_json().encode("utf-8")
        length_prefix = len(response_bytes).to_bytes(4, byteorder="big")

        mock_reader.readexactly = AsyncMock(side_effect=[length_prefix, response_bytes])

        client._reader = mock_reader
        client._writer = mock_writer
        client._id_generator.generate = MagicMock(return_value="test-id")

        with pytest.raises(IPCProtocolError) as exc_info:
            await client.call("test", {})

        assert "Bad parameter" in str(exc_info.value)

    async def test_call_timeout(self) -> None:
        """Test call timeout."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED
        client.reconnect_enabled = False

        mock_writer = AsyncMock()
        mock_reader = AsyncMock()

        # Make reader hang forever
        async def hang_forever(
            *_args: object,
            **_kwargs: object,  # noqa: ARG001
        ) -> bytes:
            await asyncio.sleep(100)
            return b""

        mock_reader.readexactly = hang_forever

        client._reader = mock_reader
        client._writer = mock_writer

        with pytest.raises(IPCTimeoutError):
            await client.call("ping", {}, timeout=0.1)


# =============================================================================
# IPCClient Health Check Tests
# =============================================================================


class TestIPCClientHealthCheck:
    """Tests for health check functionality."""

    async def test_health_check_not_connected(self) -> None:
        """Test health check when not connected."""
        client = IPCClient()
        result = await client.health_check()
        assert result is False

    async def test_health_check_success(self) -> None:
        """Test successful health check."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED

        # Mock the call method
        client.call = AsyncMock(return_value={"pong": True})

        result = await client.health_check()

        assert result is True
        client.call.assert_called_once_with("ping", {}, timeout=5.0)

    async def test_health_check_failure(self) -> None:
        """Test health check failure."""
        client = IPCClient()
        client.state = IPCConnectionState.CONNECTED

        # Mock the call method to raise
        client.call = AsyncMock(side_effect=IPCTimeoutError("timeout"))

        result = await client.health_check()
        assert result is False


# =============================================================================
# IPCClient Context Manager Tests
# =============================================================================


class TestIPCClientContextManager:
    """Tests for context manager interface."""

    async def test_context_manager_connect(self) -> None:
        """Test context manager entry connects."""
        client = IPCClient(socket_path="/tmp/test.sock")

        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)

        with patch("asyncio.open_unix_connection") as mock_connect:
            mock_connect.return_value = (mock_reader, mock_writer)

            async with client as connected_client:
                assert connected_client is client
                assert client.state == IPCConnectionState.CONNECTED

    async def test_context_manager_disconnect_on_exit(self) -> None:
        """Test context manager exit disconnects."""
        client = IPCClient(socket_path="/tmp/test.sock")

        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)

        with patch("asyncio.open_unix_connection") as mock_connect:
            mock_connect.return_value = (mock_reader, mock_writer)

            async with client:
                assert client.state == IPCConnectionState.CONNECTED

            # After context exit
            assert client.state == IPCConnectionState.DISCONNECTED


# =============================================================================
# OpsAgentClient Alias Tests
# =============================================================================


class TestOpsAgentClientAlias:
    """Tests for OpsAgentClient alias."""

    def test_ops_agent_client_is_ipc_client(self) -> None:
        """Test that OpsAgentClient is an alias for IPCClient."""
        assert OpsAgentClient is IPCClient
