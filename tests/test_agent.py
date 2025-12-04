"""
Tests for the privileged agent module.

Tests the OpsAgent, HandlerRegistry, and handlers.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_raspi.ipc.protocol import IPCRequest, IPCResponse
from mcp_raspi_ops.agent import OpsAgent
from mcp_raspi_ops.handlers import (
    HandlerError,
    HandlerRegistry,
    get_default_registry,
    handle_echo,
    handle_get_info,
    handle_ping,
)
from mcp_raspi_ops.ipc_protocol import IPCServerProtocol

# =============================================================================
# HandlerError Tests
# =============================================================================


class TestHandlerError:
    """Tests for HandlerError."""

    def test_handler_error_creation(self) -> None:
        """Test basic error creation."""
        error = HandlerError(
            code="invalid_argument",
            message="Invalid parameter",
            details={"param": "pin"},
        )
        assert error.code == "invalid_argument"
        assert error.message == "Invalid parameter"
        assert error.details == {"param": "pin"}
        assert str(error) == "Invalid parameter"

    def test_handler_error_default_details(self) -> None:
        """Test error with default empty details."""
        error = HandlerError(code="test", message="Test error")
        assert error.details == {}


# =============================================================================
# HandlerRegistry Tests
# =============================================================================


class TestHandlerRegistry:
    """Tests for HandlerRegistry."""

    def test_register_handler(self) -> None:
        """Test registering a handler."""
        registry = HandlerRegistry()

        async def test_handler(_request: IPCRequest) -> dict[str, Any]:
            return {"test": True}

        registry.register("test.operation", test_handler)
        assert registry.has_handler("test.operation")

    def test_unregister_handler(self) -> None:
        """Test unregistering a handler."""
        registry = HandlerRegistry()

        async def test_handler(_request: IPCRequest) -> dict[str, Any]:
            return {}

        registry.register("test.op", test_handler)
        assert registry.has_handler("test.op")

        registry.unregister("test.op")
        assert not registry.has_handler("test.op")

    def test_unregister_nonexistent(self) -> None:
        """Test unregistering a nonexistent handler doesn't raise."""
        registry = HandlerRegistry()
        # Should not raise
        registry.unregister("nonexistent")

    def test_get_operations(self) -> None:
        """Test getting list of registered operations."""
        registry = HandlerRegistry()

        async def handler1(_request: IPCRequest) -> dict[str, Any]:
            return {}

        async def handler2(_request: IPCRequest) -> dict[str, Any]:
            return {}

        registry.register("op1", handler1)
        registry.register("op2", handler2)

        ops = registry.get_operations()
        assert "op1" in ops
        assert "op2" in ops

    async def test_dispatch_success(self) -> None:
        """Test successful dispatch."""
        registry = HandlerRegistry()

        async def test_handler(request: IPCRequest) -> dict:
            return {"param_value": request.params.get("key")}

        registry.register("test.op", test_handler)

        request = IPCRequest.create("test.op", params={"key": "value"})
        result = await registry.dispatch(request)

        assert result == {"param_value": "value"}

    async def test_dispatch_unknown_operation(self) -> None:
        """Test dispatch with unknown operation."""
        registry = HandlerRegistry()

        request = IPCRequest.create("unknown.op")

        with pytest.raises(HandlerError) as exc_info:
            await registry.dispatch(request)

        assert exc_info.value.code == "unknown_operation"
        assert "unknown.op" in exc_info.value.message

    async def test_dispatch_handler_error(self) -> None:
        """Test dispatch when handler raises HandlerError."""
        registry = HandlerRegistry()

        async def failing_handler(_request: IPCRequest) -> dict[str, Any]:
            raise HandlerError(code="test_error", message="Handler failed")

        registry.register("failing.op", failing_handler)

        request = IPCRequest.create("failing.op")

        with pytest.raises(HandlerError) as exc_info:
            await registry.dispatch(request)

        assert exc_info.value.code == "test_error"

    async def test_dispatch_unexpected_exception(self) -> None:
        """Test dispatch when handler raises unexpected exception."""
        registry = HandlerRegistry()

        async def bad_handler(_request: IPCRequest) -> dict[str, Any]:
            raise ValueError("Unexpected error")

        registry.register("bad.op", bad_handler)

        request = IPCRequest.create("bad.op")

        with pytest.raises(HandlerError) as exc_info:
            await registry.dispatch(request)

        assert exc_info.value.code == "internal"
        assert "ValueError" in exc_info.value.message


# =============================================================================
# Built-in Handler Tests
# =============================================================================


class TestBuiltinHandlers:
    """Tests for built-in handlers."""

    async def test_handle_ping(self) -> None:
        """Test ping handler."""
        request = IPCRequest.create("ping")
        result = await handle_ping(request)
        assert result == {"pong": True}

    async def test_handle_echo(self) -> None:
        """Test echo handler."""
        request = IPCRequest.create("echo", params={"message": "hello"})
        result = await handle_echo(request)
        assert result == {"echo": "hello"}

    async def test_handle_echo_empty_message(self) -> None:
        """Test echo handler with no message."""
        request = IPCRequest.create("echo")
        result = await handle_echo(request)
        assert result == {"echo": ""}

    async def test_handle_get_info(self) -> None:
        """Test get_info handler."""
        request = IPCRequest.create("get_info")
        result = await handle_get_info(request)

        assert result["name"] == "raspi-ops-agent"
        assert "version" in result
        assert result["status"] == "running"


class TestDefaultRegistry:
    """Tests for default registry creation."""

    def test_get_default_registry(self) -> None:
        """Test default registry has expected handlers."""
        registry = get_default_registry()

        assert registry.has_handler("ping")
        assert registry.has_handler("echo")
        assert registry.has_handler("get_info")

    async def test_default_registry_handlers_work(self) -> None:
        """Test that default registry handlers work."""
        registry = get_default_registry()

        ping_request = IPCRequest.create("ping")
        result = await registry.dispatch(ping_request)
        assert result == {"pong": True}


# =============================================================================
# IPCServerProtocol Tests
# =============================================================================


class TestIPCServerProtocol:
    """Tests for IPCServerProtocol."""

    async def test_read_request_success(self) -> None:
        """Test successful request reading."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()

        request = IPCRequest.create("test.op", params={"key": "value"})
        request_bytes = request.to_json().encode("utf-8")
        length_prefix = len(request_bytes).to_bytes(4, byteorder="big")

        mock_reader.readexactly = AsyncMock(side_effect=[length_prefix, request_bytes])

        protocol = IPCServerProtocol(mock_reader, mock_writer)
        result = await protocol.read_request()

        assert result is not None
        assert result.id == request.id
        assert result.operation == request.operation

    async def test_read_request_connection_closed(self) -> None:
        """Test read when connection is closed."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()

        mock_reader.readexactly = AsyncMock(
            side_effect=asyncio.IncompleteReadError(b"", 4)
        )

        protocol = IPCServerProtocol(mock_reader, mock_writer)
        result = await protocol.read_request()

        assert result is None

    async def test_write_success_response(self) -> None:
        """Test writing a success response."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()

        protocol = IPCServerProtocol(mock_reader, mock_writer)
        await protocol.write_success_response("req-123", {"result": True})

        mock_writer.write.assert_called_once()
        mock_writer.drain.assert_called_once()

        # Verify the written data
        written_data = mock_writer.write.call_args[0][0]
        _ = int.from_bytes(written_data[:4], byteorder="big")  # length prefix
        response_json = written_data[4:].decode("utf-8")
        response = IPCResponse.from_json(response_json)

        assert response.id == "req-123"
        assert response.status == "ok"
        assert response.data == {"result": True}

    async def test_write_error_response(self) -> None:
        """Test writing an error response."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()

        protocol = IPCServerProtocol(mock_reader, mock_writer)
        await protocol.write_error_response(
            request_id="req-456",
            code="test_error",
            message="Something went wrong",
            details={"key": "value"},
        )

        mock_writer.write.assert_called_once()

        # Verify the written data
        written_data = mock_writer.write.call_args[0][0]
        response_json = written_data[4:].decode("utf-8")
        response = IPCResponse.from_json(response_json)

        assert response.id == "req-456"
        assert response.status == "error"
        assert response.error is not None
        assert response.error.code == "test_error"

    async def test_close(self) -> None:
        """Test closing the protocol."""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()

        protocol = IPCServerProtocol(mock_reader, mock_writer)
        await protocol.close()

        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()


# =============================================================================
# OpsAgent Tests
# =============================================================================


class TestOpsAgent:
    """Tests for OpsAgent."""

    def test_agent_initialization(self) -> None:
        """Test agent initialization."""
        agent = OpsAgent(socket_path="/tmp/test.sock")

        assert agent.socket_path == "/tmp/test.sock"
        assert agent.running is False
        assert agent.registry is not None
        assert agent.registry.has_handler("ping")

    def test_agent_with_custom_registry(self) -> None:
        """Test agent with custom registry."""
        registry = HandlerRegistry()

        async def custom_handler(_request: IPCRequest) -> dict[str, Any]:
            return {"custom": True}

        registry.register("custom.op", custom_handler)

        agent = OpsAgent(registry=registry)
        assert agent.registry.has_handler("custom.op")
        assert not agent.registry.has_handler("ping")

    def test_agent_from_config(self) -> None:
        """Test agent creation from config."""
        config = MagicMock()
        config.socket_path = "/test/config.sock"

        agent = OpsAgent.from_config(config)
        assert agent.socket_path == "/test/config.sock"

    def test_get_stats(self) -> None:
        """Test getting agent stats."""
        agent = OpsAgent(socket_path="/tmp/test.sock")
        stats = agent.get_stats()

        assert stats["running"] is False
        assert stats["socket_path"] == "/tmp/test.sock"
        assert stats["active_connections"] == 0
        assert "ping" in stats["registered_operations"]


# =============================================================================
# OpsAgent Integration Tests
# =============================================================================


class TestOpsAgentIntegration:
    """Integration tests for OpsAgent with real socket."""

    @pytest.mark.integration
    async def test_agent_start_and_stop(self) -> None:
        """Test agent starts and stops cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")
            agent = OpsAgent(socket_path=socket_path)

            # Start agent in background
            start_task = asyncio.create_task(agent.start())

            # Give it time to start
            await asyncio.sleep(0.1)

            assert agent.running is True
            assert Path(socket_path).exists()

            # Stop agent
            await agent.stop()

            # Wait for start task to complete
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(start_task, timeout=1.0)

            assert agent.running is False

    @pytest.mark.integration
    async def test_agent_handles_ping_request(self) -> None:
        """Test agent handles ping request end-to-end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")
            agent = OpsAgent(socket_path=socket_path)

            # Start agent in background
            start_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                # Connect as client
                reader, writer = await asyncio.open_unix_connection(socket_path)

                # Send ping request
                request = IPCRequest.create("ping")
                request_bytes = request.to_json().encode("utf-8")
                length_prefix = len(request_bytes).to_bytes(4, byteorder="big")

                writer.write(length_prefix + request_bytes)
                await writer.drain()

                # Read response
                resp_length_bytes = await reader.readexactly(4)
                resp_length = int.from_bytes(resp_length_bytes, byteorder="big")
                resp_bytes = await reader.readexactly(resp_length)
                resp_json = resp_bytes.decode("utf-8")
                response = IPCResponse.from_json(resp_json)

                assert response.id == request.id
                assert response.status == "ok"
                assert response.data == {"pong": True}

                writer.close()
                await writer.wait_closed()

            finally:
                await agent.stop()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(start_task, timeout=1.0)

    @pytest.mark.integration
    async def test_agent_handles_unknown_operation(self) -> None:
        """Test agent returns error for unknown operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")
            agent = OpsAgent(socket_path=socket_path)

            start_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                reader, writer = await asyncio.open_unix_connection(socket_path)

                # Send unknown operation
                request = IPCRequest.create("unknown.operation")
                request_bytes = request.to_json().encode("utf-8")
                length_prefix = len(request_bytes).to_bytes(4, byteorder="big")

                writer.write(length_prefix + request_bytes)
                await writer.drain()

                # Read response
                resp_length_bytes = await reader.readexactly(4)
                resp_length = int.from_bytes(resp_length_bytes, byteorder="big")
                resp_bytes = await reader.readexactly(resp_length)
                response = IPCResponse.from_json(resp_bytes.decode("utf-8"))

                assert response.status == "error"
                assert response.error is not None
                assert response.error.code == "unknown_operation"

                writer.close()
                await writer.wait_closed()

            finally:
                await agent.stop()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(start_task, timeout=1.0)

    @pytest.mark.integration
    async def test_agent_handles_multiple_clients(self) -> None:
        """Test agent handles multiple simultaneous clients."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")
            agent = OpsAgent(socket_path=socket_path)

            start_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                # Create multiple clients
                clients = []
                for _ in range(3):
                    reader, writer = await asyncio.open_unix_connection(socket_path)
                    clients.append((reader, writer))

                # Each client sends a request
                async def client_request(
                    reader: asyncio.StreamReader,
                    writer: asyncio.StreamWriter,
                    msg: str,
                ) -> str:
                    request = IPCRequest.create("echo", params={"message": msg})
                    request_bytes = request.to_json().encode("utf-8")
                    length_prefix = len(request_bytes).to_bytes(4, byteorder="big")

                    writer.write(length_prefix + request_bytes)
                    await writer.drain()

                    resp_length_bytes = await reader.readexactly(4)
                    resp_length = int.from_bytes(resp_length_bytes, byteorder="big")
                    resp_bytes = await reader.readexactly(resp_length)
                    response = IPCResponse.from_json(resp_bytes.decode("utf-8"))
                    return response.data.get("echo", "")  # type: ignore

                # Run requests concurrently
                results = await asyncio.gather(
                    client_request(clients[0][0], clients[0][1], "msg0"),
                    client_request(clients[1][0], clients[1][1], "msg1"),
                    client_request(clients[2][0], clients[2][1], "msg2"),
                )

                assert set(results) == {"msg0", "msg1", "msg2"}

                # Clean up clients
                for _, writer in clients:
                    writer.close()
                    await writer.wait_closed()

            finally:
                await agent.stop()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(start_task, timeout=1.0)
