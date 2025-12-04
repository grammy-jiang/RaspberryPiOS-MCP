"""
Integration tests for the IPC system.

Tests the full MCP Server -> IPC Client -> Agent -> IPC Server flow.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path
from typing import Any

import pytest

from mcp_raspi.ipc.client import IPCClient
from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi_ops.agent import OpsAgent
from mcp_raspi_ops.handlers import HandlerError, HandlerRegistry


async def _stop_agent(agent: OpsAgent, task: asyncio.Task[None]) -> None:
    """Stop an agent and its task cleanly."""
    await agent.stop()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.integration
class TestIPCIntegration:
    """Integration tests for the complete IPC flow."""

    async def test_ping_command_end_to_end(self) -> None:
        """Test ping command works end-to-end through IPC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                client = IPCClient(
                    socket_path=socket_path,
                    reconnect_enabled=False,
                )
                connected = await client.connect()
                assert connected is True

                result = await client.call("ping", {})
                assert result == {"pong": True}

                await client.disconnect()
            finally:
                await _stop_agent(agent, agent_task)

    async def test_echo_command_end_to_end(self) -> None:
        """Test echo command works end-to-end through IPC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                async with IPCClient(socket_path=socket_path) as client:
                    result = await client.call("echo", {"message": "Hello, World!"})
                    assert result == {"echo": "Hello, World!"}
            finally:
                await _stop_agent(agent, agent_task)

    async def test_get_info_command_end_to_end(self) -> None:
        """Test get_info command works end-to-end through IPC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                async with IPCClient(socket_path=socket_path) as client:
                    result = await client.call("get_info", {})

                    assert result["name"] == "raspi-ops-agent"
                    assert "version" in result
                    assert result["status"] == "running"
            finally:
                await _stop_agent(agent, agent_task)

    async def test_error_propagation(self) -> None:
        """Test that agent errors propagate correctly to client."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                async with IPCClient(socket_path=socket_path) as client:
                    from mcp_raspi.ipc.protocol import IPCProtocolError

                    with pytest.raises(IPCProtocolError) as exc_info:
                        await client.call("unknown.operation", {})

                    assert (
                        "unknown.operation" in str(exc_info.value).lower()
                        or "unknown"
                        in str(exc_info.value.details.get("code", "")).lower()
                    )
            finally:
                await _stop_agent(agent, agent_task)

    async def test_client_reconnection_after_agent_restart(self) -> None:
        """Test client reconnects after agent restarts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            # Start agent
            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            # Create client with fast reconnection
            client = IPCClient(
                socket_path=socket_path,
                reconnect_enabled=True,
                reconnect_delay=0.1,
                reconnect_max_delay=0.5,
                reconnect_max_attempts=5,
            )

            try:
                # Connect and make a call
                await client.connect()
                result = await client.call("ping", {})
                assert result == {"pong": True}

                # Stop agent
                await _stop_agent(agent, agent_task)

                # Start new agent
                agent = OpsAgent(socket_path=socket_path)
                agent_task = asyncio.create_task(agent.start())
                await asyncio.sleep(0.2)

                # Client should reconnect and work
                result = await client.call("ping", {})
                assert result == {"pong": True}
            finally:
                await client.disconnect()
                await _stop_agent(agent, agent_task)

    async def test_multiple_sequential_requests(self) -> None:
        """Test multiple sequential requests work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                async with IPCClient(socket_path=socket_path) as client:
                    for i in range(10):
                        result = await client.call("echo", {"message": f"msg-{i}"})
                        assert result == {"echo": f"msg-{i}"}
            finally:
                await _stop_agent(agent, agent_task)

    async def test_health_check(self) -> None:
        """Test health check functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                client = IPCClient(socket_path=socket_path)
                await client.connect()

                is_healthy = await client.health_check()
                assert is_healthy is True

                await client.disconnect()
            finally:
                await _stop_agent(agent, agent_task)

    async def test_custom_handler_registration(self) -> None:
        """Test registering and using custom handlers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            # Create custom registry with custom handler
            registry = HandlerRegistry()

            async def custom_multiply(request: IPCRequest) -> dict[str, Any]:
                a = request.params.get("a", 0)
                b = request.params.get("b", 0)
                return {"result": a * b}

            async def ping_handler(_request: IPCRequest) -> dict[str, Any]:
                return {"pong": True}

            registry.register("math.multiply", custom_multiply)
            registry.register("ping", ping_handler)

            agent = OpsAgent(socket_path=socket_path, registry=registry)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                async with IPCClient(socket_path=socket_path) as client:
                    result = await client.call("math.multiply", {"a": 6, "b": 7})
                    assert result == {"result": 42}
            finally:
                await _stop_agent(agent, agent_task)

    async def test_handler_error_propagation(self) -> None:
        """Test that handler errors propagate with correct codes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            # Create registry with failing handler
            registry = HandlerRegistry()

            async def failing_handler(_request: IPCRequest) -> dict[str, Any]:
                raise HandlerError(
                    code="test_failure",
                    message="This is a test failure",
                    details={"reason": "testing"},
                )

            registry.register("test.fail", failing_handler)

            agent = OpsAgent(socket_path=socket_path, registry=registry)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                async with IPCClient(socket_path=socket_path) as client:
                    from mcp_raspi.ipc.protocol import IPCProtocolError

                    with pytest.raises(IPCProtocolError) as exc_info:
                        await client.call("test.fail", {})

                    assert "test failure" in str(exc_info.value).lower()
            finally:
                await _stop_agent(agent, agent_task)

    async def test_concurrent_clients(self) -> None:
        """Test multiple clients making requests concurrently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:

                async def make_requests(client_id: int) -> list[dict[str, Any]]:
                    client = IPCClient(socket_path=socket_path)
                    await client.connect()
                    results = []
                    for i in range(5):
                        result = await client.call(
                            "echo",
                            {"message": f"client-{client_id}-msg-{i}"},
                        )
                        results.append(result)
                    await client.disconnect()
                    return results

                all_results = await asyncio.gather(
                    make_requests(0),
                    make_requests(1),
                    make_requests(2),
                )

                for client_id, results in enumerate(all_results):
                    for i, result in enumerate(results):
                        assert result == {"echo": f"client-{client_id}-msg-{i}"}
            finally:
                await _stop_agent(agent, agent_task)

    async def test_large_payload(self) -> None:
        """Test handling of larger payloads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                async with IPCClient(socket_path=socket_path) as client:
                    large_message = "x" * 100000
                    result = await client.call("echo", {"message": large_message})
                    assert result == {"echo": large_message}
            finally:
                await _stop_agent(agent, agent_task)


@pytest.mark.integration
class TestIPCRobustness:
    """Tests for IPC robustness and edge cases."""

    async def test_client_disconnects_gracefully(self) -> None:
        """Test agent handles client disconnect gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                for _ in range(3):
                    client = IPCClient(socket_path=socket_path)
                    await client.connect()
                    result = await client.call("ping", {})
                    assert result == {"pong": True}
                    await client.disconnect()

                assert agent.running is True

                client = IPCClient(socket_path=socket_path)
                await client.connect()
                result = await client.call("ping", {})
                assert result == {"pong": True}
                await client.disconnect()
            finally:
                await _stop_agent(agent, agent_task)

    async def test_timeout_handling(self) -> None:
        """Test request timeout is handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            # Create registry with slow handler
            registry = HandlerRegistry()

            async def slow_handler(_request: IPCRequest) -> dict[str, Any]:
                await asyncio.sleep(5.0)  # Longer than timeout
                return {"done": True}

            registry.register("slow.op", slow_handler)

            agent = OpsAgent(socket_path=socket_path, registry=registry)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                client = IPCClient(
                    socket_path=socket_path,
                    reconnect_enabled=False,
                )
                await client.connect()

                from mcp_raspi.ipc.protocol import IPCTimeoutError

                with pytest.raises(IPCTimeoutError):
                    await client.call("slow.op", {}, timeout=0.5)

                await client.disconnect()
            finally:
                await _stop_agent(agent, agent_task)

    async def test_agent_stats_tracking(self) -> None:
        """Test agent tracks connection statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = str(Path(tmpdir) / "test.sock")

            agent = OpsAgent(socket_path=socket_path)
            agent_task = asyncio.create_task(agent.start())
            await asyncio.sleep(0.1)

            try:
                stats = agent.get_stats()
                assert stats["running"] is True
                assert stats["active_connections"] == 0

                client = IPCClient(socket_path=socket_path)
                await client.connect()
                await asyncio.sleep(0.1)

                stats = agent.get_stats()
                assert stats["active_connections"] == 1

                await client.disconnect()
                await asyncio.sleep(0.1)

                stats = agent.get_stats()
                assert stats["active_connections"] == 0
            finally:
                await _stop_agent(agent, agent_task)
