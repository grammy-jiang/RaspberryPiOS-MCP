"""
Raspberry Pi MCP Server - Privileged Operations Agent.

This package implements the privileged agent (raspi-ops-agent) that runs as root
or a dedicated privileged user. It exposes a local IPC interface over a Unix
domain socket and executes privileged operations through a fixed set of operation types.
"""

__version__ = "0.1.0"
