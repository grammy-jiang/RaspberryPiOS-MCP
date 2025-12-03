"""
MCP Server implementation for the Raspberry Pi MCP Server.

This module implements the main MCPServer class that communicates via JSON-RPC 2.0
over stdio (stdin/stdout), processes requests, and dispatches to tool handlers.

Design follows Doc 02 §5 (Request Flow) and Doc 05 (MCP Tools Interface).
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, TextIO

from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import ToolError
from mcp_raspi.logging import get_logger
from mcp_raspi.protocol import (
    JSONRPCError,
    create_internal_error,
    format_error_response,
    format_success_response,
    parse_request,
    tool_error_to_jsonrpc_error,
)
from mcp_raspi.routing import ToolRegistry, get_default_registry

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


async def process_request(
    request_json: str,
    registry: ToolRegistry,
    caller: CallerInfo | None = None,
) -> str | None:
    """
    Process a single JSON-RPC request and return the response.

    This function handles the complete request lifecycle:
    1. Parse the JSON-RPC request
    2. Create a ToolContext
    3. Dispatch to the appropriate handler
    4. Format the response (success or error)

    Args:
        request_json: Raw JSON string containing the request.
        registry: ToolRegistry with registered handlers.
        caller: Optional CallerInfo for the request.

    Returns:
        JSON string containing the response, or None for notifications.
    """
    request_id: str | int | None = None

    try:
        # Parse the request
        request = parse_request(request_json)
        request_id = request.id

        # Check if this is a notification (no id means no response)
        if request.is_notification:
            # Process the notification but don't return a response
            ctx = ToolContext.from_request(request, caller=caller)
            try:
                await registry.invoke(request.method, ctx, request.params)
            except Exception as e:
                # Log notification errors but don't return them
                logger.warning(
                    "Error processing notification",
                    extra={
                        "method": request.method,
                        "error": str(e),
                    },
                )
            return None

        # Create context and dispatch
        ctx = ToolContext.from_request(request, caller=caller)
        result = await registry.invoke(request.method, ctx, request.params)

        # Format success response
        response = format_success_response(request_id, result)
        return response.to_json()

    except JSONRPCError as e:
        # JSON-RPC protocol errors (parse error, invalid request, etc.)
        response = format_error_response(request_id, e)
        return response.to_json()

    except ToolError as e:
        # Tool errors are mapped to JSON-RPC errors
        jsonrpc_error = tool_error_to_jsonrpc_error(e)
        response = format_error_response(request_id, jsonrpc_error)
        return response.to_json()

    except Exception as e:
        # Unexpected exceptions
        logger.exception(
            "Unexpected error processing request",
            extra={"request_id": request_id, "error": str(e)},
        )
        jsonrpc_error = create_internal_error(
            message=f"Internal server error: {type(e).__name__}",
            details={"exception": str(e)},
        )
        response = format_error_response(request_id, jsonrpc_error)
        return response.to_json()


class MCPServer:
    """
    MCP Server that communicates via JSON-RPC 2.0 over stdio.

    The server reads JSON-RPC requests from stdin, dispatches them to
    registered tool handlers, and writes responses to stdout.

    Example:
        >>> server = MCPServer()
        >>> server.registry.register("system.ping", ping_handler)
        >>> await server.run()

    Attributes:
        registry: ToolRegistry with registered handlers.
        running: Whether the server is currently running.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
    ) -> None:
        """
        Initialize the MCP Server.

        Args:
            registry: Optional ToolRegistry. Uses default if not provided.
            stdin: Optional stdin stream. Uses sys.stdin if not provided.
            stdout: Optional stdout stream. Uses sys.stdout if not provided.
        """
        self.registry = registry if registry is not None else get_default_registry()
        self._stdin = stdin if stdin is not None else sys.stdin
        self._stdout = stdout if stdout is not None else sys.stdout
        self.running = False
        self._caller: CallerInfo | None = None

    async def handle_request(self, request_json: str) -> str | None:
        """
        Handle a single JSON-RPC request.

        Args:
            request_json: Raw JSON string containing the request.

        Returns:
            JSON string containing the response, or None for notifications.
        """
        return await process_request(request_json, self.registry, self._caller)

    async def run(self) -> None:
        """
        Run the server, reading from stdin and writing to stdout.

        The server runs until stdin is closed or stop() is called.
        Each line from stdin is treated as a JSON-RPC request.
        """
        self.running = True
        logger.info("MCP Server starting", extra={"tools_count": len(self.registry)})

        try:
            # Use asyncio for non-blocking stdin reading
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)

            await loop.connect_read_pipe(lambda: protocol, self._stdin)

            while self.running:
                try:
                    # Read a line from stdin
                    line = await reader.readline()
                    if not line:
                        # EOF reached
                        break

                    # Decode with error handling for non-UTF-8 input
                    try:
                        request_json = line.decode("utf-8").strip()
                    except UnicodeDecodeError as e:
                        logger.warning(
                            "Invalid UTF-8 encoding in request",
                            extra={"error": str(e)},
                        )
                        error = create_internal_error(
                            "Invalid request encoding: UTF-8 required"
                        )
                        error_response = format_error_response(None, error)
                        self._write_response(error_response.to_json())
                        continue

                    if not request_json:
                        continue

                    # Process the request
                    response = await self.handle_request(request_json)

                    # Write response to stdout (if not a notification)
                    if response:
                        self._write_response(response)

                except Exception as e:
                    logger.exception(
                        "Error in server loop",
                        extra={"error": str(e)},
                    )
                    # Send internal error response
                    error = create_internal_error(str(e))
                    error_response = format_error_response(None, error)
                    self._write_response(error_response.to_json())

        finally:
            self.running = False
            logger.info("MCP Server stopped")

    def stop(self) -> None:
        """Stop the server gracefully."""
        self.running = False

    def _write_response(self, response_json: str) -> None:
        """Write a response to stdout."""
        self._stdout.write(response_json + "\n")
        self._stdout.flush()

    def set_caller(self, caller: CallerInfo) -> None:
        """
        Set the caller identity for requests.

        In production, this would be extracted from authentication headers.

        Args:
            caller: CallerInfo to use for subsequent requests.
        """
        self._caller = caller


def create_server(registry: ToolRegistry | None = None) -> MCPServer:
    """
    Create and configure an MCP Server instance.

    This is the main entry point for creating a server with the default
    tool registry and registered handlers.

    Args:
        registry: Optional custom registry. Creates default if not provided.

    Returns:
        Configured MCPServer instance.

    Example:
        >>> from mcp_raspi.tools.system import handle_system_get_basic_info
        >>> server = create_server()
        >>> server.registry.register("system.get_basic_info", handle_system_get_basic_info)
        >>> asyncio.run(server.run())
    """
    return MCPServer(registry=registry)
