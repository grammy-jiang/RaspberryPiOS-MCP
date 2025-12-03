"""
IPC Protocol handling for the Privileged Agent.

This module implements the server-side IPC protocol handling for the
privileged operations agent. It handles reading requests from and writing
responses to clients over the Unix domain socket.

Design follows Doc 02 §6 (Privileged Agent) and §12 (IPC Robustness).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp_raspi.ipc.protocol import (
    MAX_MESSAGE_SIZE,
    IPCProtocolError,
    IPCRequest,
    IPCResponse,
)
from mcp_raspi.logging import get_logger

logger = get_logger(__name__)


class IPCServerProtocol:
    """
    Server-side IPC protocol handler.

    Handles reading requests from and writing responses to clients over
    Unix domain sockets using length-prefixed JSON messages.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Initialize the protocol handler.

        Args:
            reader: Stream reader for incoming data.
            writer: Stream writer for outgoing data.
        """
        self.reader = reader
        self.writer = writer
        self._closed = False

    async def read_request(self) -> IPCRequest | None:
        """
        Read a request from the client.

        Returns:
            The parsed request, or None if connection closed.

        Raises:
            IPCProtocolError: If the request is invalid.
        """
        try:
            # Read length prefix (4 bytes big-endian)
            length_bytes = await self.reader.readexactly(4)
            length = int.from_bytes(length_bytes, byteorder="big")

            # Validate length
            if length > MAX_MESSAGE_SIZE:
                raise IPCProtocolError(
                    f"Request too large: {length} bytes",
                    details={"max_size": MAX_MESSAGE_SIZE},
                )

            if length == 0:
                raise IPCProtocolError("Empty request")

            # Read message
            message_bytes = await self.reader.readexactly(length)
            message_json = message_bytes.decode("utf-8")

            # Parse request
            try:
                request = IPCRequest.from_json(message_json)
            except json.JSONDecodeError as e:
                raise IPCProtocolError(
                    f"Invalid JSON request: {e}",
                    details={"raw": message_json[:100]},
                ) from e

            logger.debug(
                "IPC request received",
                extra={
                    "request_id": request.id,
                    "operation": request.operation,
                    "size": length,
                },
            )

            return request

        except asyncio.IncompleteReadError:
            # Connection closed
            return None

        except ConnectionResetError:
            # Client disconnected
            return None

    async def write_response(self, response: IPCResponse) -> None:
        """
        Write a response to the client.

        Args:
            response: The response to send.

        Raises:
            IPCProtocolError: If the response is too large.
        """
        if self._closed:
            return

        # Serialize to JSON
        message_bytes = response.to_json().encode("utf-8")

        # Check size
        if len(message_bytes) > MAX_MESSAGE_SIZE:
            raise IPCProtocolError(
                f"Response too large: {len(message_bytes)} bytes",
                details={"max_size": MAX_MESSAGE_SIZE},
            )

        # Write length prefix + message
        length_prefix = len(message_bytes).to_bytes(4, byteorder="big")

        try:
            self.writer.write(length_prefix + message_bytes)
            await self.writer.drain()

            logger.debug(
                "IPC response sent",
                extra={
                    "request_id": response.id,
                    "status": response.status,
                    "size": len(message_bytes),
                },
            )
        except (ConnectionResetError, BrokenPipeError):
            # Client disconnected
            self._closed = True

    async def write_error_response(
        self,
        request_id: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Write an error response.

        Args:
            request_id: The request ID to respond to.
            code: Error code.
            message: Error message.
            details: Optional error details.
        """
        response = IPCResponse.create_error(
            request_id=request_id,
            code=code,
            message=message,
            details=details,
        )
        await self.write_response(response)

    async def write_success_response(
        self,
        request_id: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Write a success response.

        Args:
            request_id: The request ID to respond to.
            data: Response data.
        """
        response = IPCResponse.success(request_id=request_id, data=data)
        await self.write_response(response)

    async def close(self) -> None:
        """Close the protocol connection."""
        if self._closed:
            return

        self._closed = True
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
