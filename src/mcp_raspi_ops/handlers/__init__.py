"""
Privileged Agent Operation Handlers.

This package contains handlers for privileged operations executed by
the raspi-ops-agent. Each module corresponds to a namespace of operations.

Modules:
- system: System power operations (reboot, shutdown)

Re-exports all base classes from handlers_core for backward compatibility.
"""

from __future__ import annotations

# Import and re-export system handlers
from mcp_raspi_ops.handlers.system import (
    handle_system_reboot,
    handle_system_shutdown,
    register_system_handlers,
)

# Re-export base classes from handlers_core module for backward compatibility
from mcp_raspi_ops.handlers_core import (
    HandlerError,
    HandlerFunc,
    HandlerRegistry,
    get_default_registry,
    handle_echo,
    handle_get_info,
    handle_ping,
)

__all__ = [
    # Base classes from handlers_core
    "HandlerError",
    "HandlerFunc",
    "HandlerRegistry",
    "get_default_registry",
    "handle_echo",
    "handle_get_info",
    "handle_ping",
    # System handlers
    "handle_system_reboot",
    "handle_system_shutdown",
    "register_system_handlers",
]
