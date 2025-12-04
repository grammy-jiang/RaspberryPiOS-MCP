"""
IPC module for communication between MCP Server and Privileged Agent.

This module provides the IPC client and protocol for communicating with
the privileged agent over Unix domain sockets.
"""

from mcp_raspi.ipc.client import IPCClient, IPCConnectionState
from mcp_raspi.ipc.protocol import (
    IPCError,
    IPCProtocolError,
    IPCRequest,
    IPCResponse,
    IPCTimeoutError,
    IPCUnavailableError,
)

__all__ = [
    "IPCClient",
    "IPCConnectionState",
    "IPCError",
    "IPCProtocolError",
    "IPCRequest",
    "IPCResponse",
    "IPCTimeoutError",
    "IPCUnavailableError",
]
