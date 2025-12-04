"""
MCP Tools package for the Raspberry Pi MCP Server.

This package contains tool implementations organized by namespace.

Modules:
- system: System information and power operations
- gpio: GPIO device control operations
- i2c: I2C bus operations
- service: Systemd service management
- process: Process monitoring
"""

# GPIO tools
from mcp_raspi.tools.gpio import (
    handle_gpio_configure_pin,
    handle_gpio_get_all_states,
    handle_gpio_read_pin,
    handle_gpio_set_pwm,
    handle_gpio_write_pin,
)

# I2C tools
from mcp_raspi.tools.i2c import (
    handle_i2c_read,
    handle_i2c_scan_bus,
    handle_i2c_write,
)

# Process tools
from mcp_raspi.tools.process import (
    handle_process_get_info,
    handle_process_list_processes,
)

# Service tools
from mcp_raspi.tools.service import (
    handle_service_control_service,
    handle_service_get_status,
    handle_service_list_services,
    handle_service_set_enabled,
)

# System tools
from mcp_raspi.tools.system import handle_system_get_basic_info

__all__ = [
    # System tools
    "handle_system_get_basic_info",
    # GPIO tools
    "handle_gpio_read_pin",
    "handle_gpio_write_pin",
    "handle_gpio_configure_pin",
    "handle_gpio_set_pwm",
    "handle_gpio_get_all_states",
    # I2C tools
    "handle_i2c_scan_bus",
    "handle_i2c_read",
    "handle_i2c_write",
    # Service tools
    "handle_service_list_services",
    "handle_service_get_status",
    "handle_service_control_service",
    "handle_service_set_enabled",
    # Process tools
    "handle_process_list_processes",
    "handle_process_get_info",
]
