"""
System namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `system.*` namespace:
- system.get_basic_info: Return basic hardware and software information

Design follows Doc 05 §3.1 (system.get_basic_info specification).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp_raspi.context import ToolContext


async def handle_system_get_basic_info(
    _ctx: ToolContext,
    _params: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle the system.get_basic_info tool call.

    Returns basic hardware and software information about the device.
    This is a stub implementation that returns mock data for development
    and testing purposes.

    Args:
        _ctx: The ToolContext for this request (unused in this stub).
        _params: Request parameters (unused; empty for this tool).

    Returns:
        Dictionary with system information:
        - hostname: Device hostname
        - model: Raspberry Pi model
        - cpu_arch: CPU architecture
        - cpu_cores: Number of CPU cores
        - memory_total_bytes: Total system memory
        - os_name: Operating system name
        - os_version: OS version string
        - kernel_version: Linux kernel version
        - uptime_seconds: System uptime in seconds
        - timestamp: Current timestamp (ISO 8601)

    Example:
        >>> result = await handle_system_get_basic_info(ctx, {})
        >>> print(result["hostname"])
        raspberrypi
    """
    # In a real implementation, this would query actual system info
    # using psutil, /proc, /sys, etc. This is a stub with mock data.
    return {
        "hostname": "raspberrypi",
        "model": "Raspberry Pi 4 Model B Rev 1.4",
        "cpu_arch": "aarch64",
        "cpu_cores": 4,
        "memory_total_bytes": 4294967296,  # 4 GB
        "os_name": "Raspberry Pi OS",
        "os_version": "12 (bookworm)",
        "kernel_version": "6.1.21-v8+",
        "uptime_seconds": 86400,  # 1 day
        "timestamp": datetime.now(UTC).isoformat(),
    }
