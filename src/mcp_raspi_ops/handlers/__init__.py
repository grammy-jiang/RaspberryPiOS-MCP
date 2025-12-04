"""
Privileged Agent Operation Handlers.

This package contains handlers for privileged operations executed by
the raspi-ops-agent. Each module corresponds to a namespace of operations.

Modules:
- system: System power operations (reboot, shutdown)
- gpio: GPIO device control operations (read, write, configure, PWM)
- i2c: I2C bus operations (scan, read, write)
- service: Systemd service management (list, status, control, enable/disable)
- process: Process monitoring (list, info)

Re-exports all base classes from handlers_core for backward compatibility.
"""

from __future__ import annotations

# Import and re-export GPIO handlers
from mcp_raspi_ops.handlers.gpio import (
    handle_gpio_configure,
    handle_gpio_get_all_states,
    handle_gpio_pwm,
    handle_gpio_read,
    handle_gpio_write,
    register_gpio_handlers,
)

# Import and re-export I2C handlers
from mcp_raspi_ops.handlers.i2c import (
    handle_i2c_read,
    handle_i2c_scan,
    handle_i2c_write,
    register_i2c_handlers,
)

# Import and re-export process handlers
from mcp_raspi_ops.handlers.process import (
    handle_process_get_info,
    handle_process_list_processes,
    register_process_handlers,
)

# Import and re-export service handlers
from mcp_raspi_ops.handlers.service import (
    handle_service_control_service,
    handle_service_get_status,
    handle_service_list_services,
    handle_service_set_enabled,
    register_service_handlers,
)

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
    # GPIO handlers
    "handle_gpio_read",
    "handle_gpio_write",
    "handle_gpio_configure",
    "handle_gpio_pwm",
    "handle_gpio_get_all_states",
    "register_gpio_handlers",
    # I2C handlers
    "handle_i2c_scan",
    "handle_i2c_read",
    "handle_i2c_write",
    "register_i2c_handlers",
    # Service handlers
    "handle_service_list_services",
    "handle_service_get_status",
    "handle_service_control_service",
    "handle_service_set_enabled",
    "register_service_handlers",
    # Process handlers
    "handle_process_list_processes",
    "handle_process_get_info",
    "register_process_handlers",
]
