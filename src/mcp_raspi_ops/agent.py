"""
Privileged Operations Agent for the Raspberry Pi MCP Server.

This module implements the main agent process that runs as root or a
privileged user and handles requests from the MCP server over a Unix
domain socket.

Design follows Doc 02 §6 (Privileged Agent), §7 (IPC Protocol),
and §12 (IPC Robustness).

The agent:
- Listens on a Unix domain socket
- Accepts connections from the MCP server
- Dispatches requests to registered handlers
- Returns structured responses

Example:
    >>> agent = OpsAgent("/run/mcp-raspi/ops-agent.sock")
    >>> await agent.start()
"""

from __future__ import annotations

import asyncio
import contextlib
import grp
import os
import pwd
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_raspi.ipc.protocol import (
    DEFAULT_SOCKET_PATH,
    IPCProtocolError,
)
from mcp_raspi.logging import get_logger
from mcp_raspi_ops.handlers import HandlerError, HandlerRegistry, get_default_registry
from mcp_raspi_ops.ipc_protocol import IPCServerProtocol

if TYPE_CHECKING:
    from mcp_raspi.config import IPCConfig

logger = get_logger(__name__)


class OpsAgent:
    """
    Privileged Operations Agent.

    This agent runs as a separate process with elevated privileges and
    handles requests from the MCP server over a Unix domain socket.

    Attributes:
        socket_path: Path to the Unix domain socket.
        registry: Handler registry for dispatching requests.
        running: Whether the agent is currently running.

    Example:
        >>> agent = OpsAgent()
        >>> agent.registry.register("custom.op", custom_handler)
        >>> await agent.start()
    """

    def __init__(
        self,
        socket_path: str | None = None,
        registry: HandlerRegistry | None = None,
        socket_owner: str | None = None,
        socket_group: str | None = None,
        socket_mode: int = 0o660,
    ) -> None:
        """
        Initialize the operations agent.

        Args:
            socket_path: Path to the Unix domain socket.
            registry: Handler registry (uses default if not provided).
            socket_owner: Optional socket file owner username.
            socket_group: Optional socket file group name.
            socket_mode: Socket file permissions (default 0o660).
        """
        self.socket_path = socket_path or DEFAULT_SOCKET_PATH
        self.registry = registry if registry is not None else get_default_registry()
        self.socket_owner = socket_owner
        self.socket_group = socket_group
        self.socket_mode = socket_mode

        self.running = False
        self._server: asyncio.AbstractServer | None = None
        self._active_connections: set[IPCServerProtocol] = set()

    @classmethod
    def from_config(cls, config: IPCConfig) -> OpsAgent:
        """
        Create an agent from configuration.

        Args:
            config: IPC configuration from AppConfig.

        Returns:
            Configured OpsAgent instance.
        """
        return cls(socket_path=config.socket_path)

    async def start(self) -> None:
        """
        Start the agent and listen for connections.

        This method creates the Unix domain socket and starts accepting
        connections. It runs until stop() is called.
        """
        # Ensure socket directory exists
        socket_dir = Path(self.socket_path).parent
        socket_dir.mkdir(parents=True, exist_ok=True)

        # Remove existing socket file if it exists
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            socket_file.unlink()

        # Start the server
        self._server = await asyncio.start_unix_server(
            self._handle_connection,
            path=self.socket_path,
        )

        # Set socket permissions
        self._set_socket_permissions()

        self.running = True
        logger.info(
            "Privileged agent started",
            extra={
                "socket_path": self.socket_path,
                "handlers": self.registry.get_operations(),
            },
        )

        # Serve until stopped
        try:
            async with self._server:
                await self._server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            logger.info("Privileged agent stopped")

    def _set_socket_permissions(self) -> None:
        """Set socket file ownership and permissions."""
        socket_file = Path(self.socket_path)

        try:
            # Set permissions
            socket_file.chmod(self.socket_mode)

            # Set ownership if specified
            uid = -1
            gid = -1

            if self.socket_owner:
                try:
                    uid = pwd.getpwnam(self.socket_owner).pw_uid
                except KeyError:
                    logger.warning(
                        "Socket owner user not found",
                        extra={"user": self.socket_owner},
                    )

            if self.socket_group:
                try:
                    gid = grp.getgrnam(self.socket_group).gr_gid
                except KeyError:
                    logger.warning(
                        "Socket owner group not found",
                        extra={"group": self.socket_group},
                    )

            if uid != -1 or gid != -1:
                os.chown(self.socket_path, uid, gid)

            logger.debug(
                "Socket permissions set",
                extra={
                    "mode": oct(self.socket_mode),
                    "owner": self.socket_owner,
                    "group": self.socket_group,
                },
            )

        except OSError as e:
            logger.warning(
                "Failed to set socket permissions",
                extra={"error": str(e)},
            )

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handle a client connection.

        Args:
            reader: Stream reader for incoming data.
            writer: Stream writer for outgoing data.
        """
        protocol = IPCServerProtocol(reader, writer)
        self._active_connections.add(protocol)

        peer_info = writer.get_extra_info("peername") or "unknown"
        logger.info("Client connected", extra={"peer": str(peer_info)})

        try:
            while self.running:
                # Read request
                request = await protocol.read_request()
                if request is None:
                    # Client disconnected
                    break

                # Dispatch and respond
                try:
                    result = await self.registry.dispatch(request)
                    await protocol.write_success_response(request.id, result)

                except HandlerError as e:
                    logger.warning(
                        "Handler error",
                        extra={
                            "request_id": request.id,
                            "operation": request.operation,
                            "code": e.code,
                            "error_message": e.message,
                        },
                    )
                    await protocol.write_error_response(
                        request_id=request.id,
                        code=e.code,
                        message=e.message,
                        details=e.details,
                    )

                except IPCProtocolError as e:
                    logger.error(
                        "Protocol error",
                        extra={
                            "request_id": request.id,
                            "error": str(e),
                        },
                    )
                    await protocol.write_error_response(
                        request_id=request.id,
                        code="protocol_error",
                        message=str(e),
                        details=e.details,
                    )

                except Exception as e:
                    logger.exception(
                        "Unexpected error handling request",
                        extra={
                            "request_id": request.id,
                            "operation": request.operation,
                            "error": str(e),
                        },
                    )
                    await protocol.write_error_response(
                        request_id=request.id,
                        code="internal",
                        message=f"Internal error: {type(e).__name__}",
                    )

        except Exception as e:
            logger.exception(
                "Connection error",
                extra={"error": str(e)},
            )

        finally:
            self._active_connections.discard(protocol)
            await protocol.close()
            logger.info("Client disconnected", extra={"peer": str(peer_info)})

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        if not self.running:
            return

        self.running = False

        # Close all active connections
        for protocol in list(self._active_connections):
            await protocol.close()
        self._active_connections.clear()

        # Stop the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Clean up socket file
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            with contextlib.suppress(OSError):
                socket_file.unlink()

        logger.info("Privileged agent stopped")

    def get_stats(self) -> dict[str, Any]:
        """
        Get agent statistics.

        Returns:
            Dict with agent statistics.
        """
        return {
            "running": self.running,
            "socket_path": self.socket_path,
            "active_connections": len(self._active_connections),
            "registered_operations": self.registry.get_operations(),
        }


async def run_agent(
    socket_path: str | None = None,
    registry: HandlerRegistry | None = None,
) -> None:
    """
    Run the privileged agent.

    This is a convenience function for running the agent. It handles
    signal setup and graceful shutdown.

    Args:
        socket_path: Path to the Unix domain socket.
        registry: Optional handler registry.
    """
    agent = OpsAgent(socket_path=socket_path, registry=registry)

    # Set up signal handling
    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        asyncio.create_task(agent.stop())

    try:
        import signal

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    except (ValueError, NotImplementedError):
        # Signal handling not supported on this platform
        pass

    await agent.start()
