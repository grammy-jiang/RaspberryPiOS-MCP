"""
Raspberry Pi MCP Server - Privileged Operations Agent.

This package implements the privileged agent (raspi-ops-agent) that runs as root
or a dedicated privileged user. It exposes a local IPC interface over a Unix
domain socket and executes privileged operations through a fixed set of operation types.
"""

from mcp_raspi_ops.agent import OpsAgent, run_agent
from mcp_raspi_ops.handlers import (
    HandlerError,
    HandlerRegistry,
    get_default_registry,
    handle_echo,
    handle_get_info,
    handle_ping,
)
from mcp_raspi_ops.ipc_protocol import IPCServerProtocol

__version__ = "0.1.0"

__all__ = [
    "OpsAgent",
    "run_agent",
    "HandlerError",
    "HandlerRegistry",
    "get_default_registry",
    "handle_ping",
    "handle_echo",
    "handle_get_info",
    "IPCServerProtocol",
]
