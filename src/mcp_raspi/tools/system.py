"""
System namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `system.*` namespace:
- system.get_basic_info: Return basic hardware and software information
- system.get_health_snapshot: Return current health metrics (CPU, memory, disk, temp)
- system.get_network_info: Return network interface information
- system.reboot: Schedule a safe system reboot
- system.shutdown: Schedule a safe system shutdown

Design follows Doc 05 §3 (system namespace specification).
"""

from __future__ import annotations

import platform
import socket
from datetime import UTC, datetime
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Any

import psutil

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import UnavailableError
from mcp_raspi.logging import get_logger
from mcp_raspi.security.audit_logger import get_audit_logger
from mcp_raspi.security.rbac import require_role

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)


# =============================================================================
# Helper Functions for System Data Collection
# =============================================================================


def _get_raspberry_pi_model() -> str:
    """
    Get the Raspberry Pi model string.

    Reads from /proc/device-tree/model (Raspberry Pi specific).
    Falls back to generic platform info if not available.

    Returns:
        Model string (e.g., "Raspberry Pi 4 Model B Rev 1.4").
    """
    model_path = Path("/proc/device-tree/model")
    try:
        if model_path.exists():
            model = model_path.read_text().strip().rstrip("\x00")
            return model
    except (OSError, PermissionError):
        pass

    # Fallback to platform info
    return f"{platform.system()} {platform.machine()}"


def _get_os_info() -> tuple[str, str]:
    """
    Get OS name and version.

    Reads from /etc/os-release for Linux systems.

    Returns:
        Tuple of (os_name, os_version).
    """
    os_release_path = Path("/etc/os-release")
    os_name = platform.system()
    os_version = platform.release()

    try:
        if os_release_path.exists():
            content = os_release_path.read_text()
            for line in content.splitlines():
                if line.startswith("NAME="):
                    os_name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION="):
                    os_version = line.split("=", 1)[1].strip().strip('"')
    except (OSError, PermissionError):
        # Ignore errors reading /etc/os-release; fall back to platform info.
        pass

    return os_name, os_version


def _get_cpu_temperature() -> float | None:
    """
    Get CPU temperature in Celsius.

    Reads from /sys/class/thermal/thermal_zone*/temp (Linux).
    Falls back to psutil sensors_temperatures if available.

    Returns:
        Temperature in Celsius, or None if unavailable.
    """
    # Try thermal zone first (most common on Raspberry Pi)
    thermal_zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    for temp_path in thermal_zones:
        try:
            temp_milli_c = int(temp_path.read_text().strip())
            return temp_milli_c / 1000.0
        except (OSError, ValueError, PermissionError):
            continue

    # Fallback to psutil
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            # Try common sensor names
            for sensor_name in ["cpu_thermal", "coretemp", "k10temp", "acpitz"]:
                if sensor_name in temps and temps[sensor_name]:
                    return temps[sensor_name][0].current
            # Return first available sensor
            first_sensor = list(temps.values())[0]
            if first_sensor:
                return first_sensor[0].current
    except (AttributeError, KeyError) as e:
        # psutil.sensors_temperatures() not available or no sensors found; ignore and return None
        logger.debug("Could not read CPU temperature from psutil: %r", e)

    return None


def _get_all_thermal_zones() -> list[dict[str, Any]]:
    """
    Get temperature readings from all thermal zones.

    Returns:
        List of thermal zone info dicts with type and temperature.
    """
    zones = []
    thermal_base = Path("/sys/class/thermal")

    if not thermal_base.exists():
        return zones

    for zone_path in sorted(thermal_base.glob("thermal_zone*")):
        try:
            zone_name = zone_path.name
            temp_path = zone_path / "temp"
            type_path = zone_path / "type"

            if not temp_path.exists():
                continue

            temp_milli_c = int(temp_path.read_text().strip())
            zone_type = "unknown"
            if type_path.exists():
                zone_type = type_path.read_text().strip()

            zones.append(
                {
                    "zone": zone_name,
                    "type": zone_type,
                    "temperature_celsius": temp_milli_c / 1000.0,
                }
            )
        except (OSError, ValueError, PermissionError):
            continue

    return zones


def _get_throttling_flags() -> dict[str, bool]:
    """
    Get Raspberry Pi throttling flags.

    On non-Raspberry Pi systems, returns default values.

    Returns:
        Dict with under_voltage, freq_capped, throttled flags.
    """
    # Default values for non-Raspberry Pi systems
    flags = {
        "under_voltage": False,
        "freq_capped": False,
        "throttled": False,
    }

    # Try to read vcgencmd output (Raspberry Pi specific)
    try:
        import subprocess

        result = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            # Output format: throttled=0x0
            if "throttled=" in output:
                hex_val = output.split("=")[1]
                throttle_bits = int(hex_val, 16)
                # Bit 0: under-voltage detected
                # Bit 1: arm frequency capped
                # Bit 2: currently throttled
                flags["under_voltage"] = bool(throttle_bits & 0x1)
                flags["freq_capped"] = bool(throttle_bits & 0x2)
                flags["throttled"] = bool(throttle_bits & 0x4)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        # Expected on non-Raspberry Pi systems or if vcgencmd is unavailable; return default flags.

    return flags


# =============================================================================
# system.get_basic_info
# =============================================================================


async def handle_system_get_basic_info(
    _ctx: ToolContext,
    _params: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle the system.get_basic_info tool call.

    Returns basic hardware and software information about the device.

    Args:
        _ctx: The ToolContext for this request.
        _params: Request parameters (empty for this tool).

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
    """
    os_name, os_version = _get_os_info()
    boot_time = psutil.boot_time()
    uptime_seconds = int(time() - boot_time)

    return {
        "hostname": socket.gethostname(),
        "model": _get_raspberry_pi_model(),
        "cpu_arch": platform.machine(),
        "cpu_cores": psutil.cpu_count(logical=True) or 1,
        "memory_total_bytes": psutil.virtual_memory().total,
        "os_name": os_name,
        "os_version": os_version,
        "kernel_version": platform.release(),
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# system.get_health_snapshot
# =============================================================================


async def handle_system_get_health_snapshot(
    _ctx: ToolContext,
    _params: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle the system.get_health_snapshot tool call.

    Returns a one-shot health snapshot including CPU, memory, disk,
    temperature, and throttling status.

    Args:
        _ctx: The ToolContext for this request.
        _params: Request parameters (empty for this tool).

    Returns:
        Dictionary with health metrics:
        - timestamp: Current timestamp (ISO 8601)
        - cpu_usage_percent: CPU usage percentage
        - memory_used_bytes: Used memory in bytes
        - memory_total_bytes: Total memory in bytes
        - disk_used_bytes: Used disk space in bytes
        - disk_total_bytes: Total disk space in bytes
        - cpu_temperature_celsius: CPU temperature (or null)
        - thermal_zones: List of all thermal zone readings
        - throttling_flags: Throttling status
    """
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_temp = _get_cpu_temperature()

    result: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "cpu_usage_percent": psutil.cpu_percent(interval=0.1),
        "memory_used_bytes": memory.used,
        "memory_total_bytes": memory.total,
        "disk_used_bytes": disk.used,
        "disk_total_bytes": disk.total,
        "throttling_flags": _get_throttling_flags(),
    }

    # Temperature can be null if unavailable
    if cpu_temp is not None:
        result["cpu_temperature_celsius"] = round(cpu_temp, 1)
    else:
        result["cpu_temperature_celsius"] = None

    # Include all thermal zones
    result["thermal_zones"] = _get_all_thermal_zones()

    return result


# =============================================================================
# system.get_network_info
# =============================================================================


async def handle_system_get_network_info(
    _ctx: ToolContext,
    _params: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle the system.get_network_info tool call.

    Returns network interface information including IP addresses,
    MAC addresses, and interface statistics.

    Args:
        _ctx: The ToolContext for this request.
        _params: Request parameters (empty for this tool).

    Returns:
        Dictionary with network information:
        - interfaces: List of network interface details
        - dns_servers: List of DNS servers (if available)
    """
    interfaces = []
    net_if_addrs = psutil.net_if_addrs()
    net_if_stats = psutil.net_if_stats()
    net_io = psutil.net_io_counters(pernic=True)

    for iface_name, addrs in net_if_addrs.items():
        iface_info: dict[str, Any] = {
            "name": iface_name,
            "mac_address": None,
            "mtu": None,
            "state": "unknown",
            "ipv4_addresses": [],
            "ipv6_addresses": [],
            "statistics": None,
        }

        # Get interface stats
        if iface_name in net_if_stats:
            stats = net_if_stats[iface_name]
            iface_info["mtu"] = stats.mtu
            iface_info["state"] = "up" if stats.isup else "down"

        # Parse addresses
        for addr in addrs:
            if addr.family == socket.AF_INET:
                # IPv4
                iface_info["ipv4_addresses"].append(
                    {
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast,
                    }
                )
            elif addr.family == socket.AF_INET6:
                # IPv6
                iface_info["ipv6_addresses"].append(
                    {
                        "address": addr.address,
                        "netmask": addr.netmask,
                    }
                )
            elif addr.family == psutil.AF_LINK:
                # MAC address
                iface_info["mac_address"] = addr.address

        # Get I/O statistics
        if iface_name in net_io:
            io = net_io[iface_name]
            iface_info["statistics"] = {
                "bytes_sent": io.bytes_sent,
                "bytes_recv": io.bytes_recv,
                "packets_sent": io.packets_sent,
                "packets_recv": io.packets_recv,
                "errors_in": io.errin,
                "errors_out": io.errout,
                "drops_in": io.dropin,
                "drops_out": io.dropout,
            }

        interfaces.append(iface_info)

    # Get DNS servers from /etc/resolv.conf
    dns_servers = []
    try:
        resolv_conf = Path("/etc/resolv.conf")
        if resolv_conf.exists():
            for line in resolv_conf.read_text().splitlines():
                line = line.strip()
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) >= 2:
                        dns_servers.append(parts[1])
    except (OSError, PermissionError):
        pass

    return {
        "interfaces": interfaces,
        "dns_servers": dns_servers,
    }


# =============================================================================
# system.reboot
# =============================================================================


@require_role("admin")
async def handle_system_reboot(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the system.reboot tool call.

    Schedules a safe reboot of the device with optional delay.
    Requires admin role. Logs to audit log.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - reason: Optional reason for reboot (max 200 chars)
            - delay_seconds: Delay before reboot (0-600, default 5)
        config: Optional AppConfig for sandbox mode check.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - scheduled: Whether reboot was scheduled
        - effective_after_seconds: Delay before reboot
        - sandbox_mode: Current sandbox mode (for transparency)

    Raises:
        PermissionDeniedError: If caller lacks admin role.
        UnavailableError: If privileged agent is unavailable.
    """
    reason = params.get("reason", "")
    if reason and len(reason) > 200:
        reason = reason[:200]
    delay_seconds = params.get("delay_seconds", 5)
    if not isinstance(delay_seconds, int):
        delay_seconds = 5
    delay_seconds = max(0, min(600, delay_seconds))

    # Determine sandbox mode
    sandbox_mode = "partial"  # Default
    if config is not None:
        sandbox_mode = config.testing.sandbox_mode

    audit = get_audit_logger()

    # Log the reboot request
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"reason": reason, "delay_seconds": delay_seconds},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "Reboot requested",
        extra={
            "user": ctx.caller.user_id,
            "reason": reason,
            "delay_seconds": delay_seconds,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        # Full sandbox: mock success without executing
        logger.info("Sandbox mode 'full': Mocking reboot (not executing)")
        return {
            "scheduled": True,
            "effective_after_seconds": delay_seconds,
            "sandbox_mode": sandbox_mode,
            "mocked": True,
        }

    elif sandbox_mode == "partial":
        # Partial sandbox: log only, don't execute
        logger.warning("Sandbox mode 'partial': Logging reboot request (not executing)")
        return {
            "scheduled": False,
            "effective_after_seconds": delay_seconds,
            "sandbox_mode": sandbox_mode,
            "logged_only": True,
        }

    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for reboot operation",
                details={"operation": "system.reboot"},
            )

        try:
            result = await ipc_client.call(
                "system.reboot",
                {
                    "reason": reason,
                    "delay_seconds": delay_seconds,
                    "caller": ctx.caller.to_dict(),
                },
            )
            return {
                "scheduled": True,
                "effective_after_seconds": delay_seconds,
                "sandbox_mode": sandbox_mode,
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to execute reboot via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"reason": reason, "delay_seconds": delay_seconds},
            )
            raise UnavailableError(
                f"Failed to execute reboot: {e}",
                details={"operation": "system.reboot"},
            ) from e


# =============================================================================
# system.shutdown
# =============================================================================


@require_role("admin")
async def handle_system_shutdown(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the system.shutdown tool call.

    Schedules a safe shutdown of the device with optional delay.
    This is a high-risk operation requiring admin role.
    Logs to audit log.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - reason: Optional reason for shutdown (max 200 chars)
            - delay_seconds: Delay before shutdown (0-600, default 5)
        config: Optional AppConfig for sandbox mode check.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - scheduled: Whether shutdown was scheduled
        - effective_after_seconds: Delay before shutdown
        - sandbox_mode: Current sandbox mode (for transparency)

    Raises:
        PermissionDeniedError: If caller lacks admin role.
        FailedPreconditionError: If shutdown is disabled in config.
        UnavailableError: If privileged agent is unavailable.
    """
    reason = params.get("reason", "")
    if reason and len(reason) > 200:
        reason = reason[:200]
    delay_seconds = params.get("delay_seconds", 5)
    if not isinstance(delay_seconds, int):
        delay_seconds = 5
    delay_seconds = max(0, min(600, delay_seconds))

    # Determine sandbox mode
    sandbox_mode = "partial"  # Default
    if config is not None:
        sandbox_mode = config.testing.sandbox_mode

    audit = get_audit_logger()

    # Log the shutdown request
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"reason": reason, "delay_seconds": delay_seconds},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.warning(
        "Shutdown requested",
        extra={
            "user": ctx.caller.user_id,
            "reason": reason,
            "delay_seconds": delay_seconds,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        # Full sandbox: mock success without executing
        logger.info("Sandbox mode 'full': Mocking shutdown (not executing)")
        return {
            "scheduled": True,
            "effective_after_seconds": delay_seconds,
            "sandbox_mode": sandbox_mode,
            "mocked": True,
        }

    elif sandbox_mode == "partial":
        # Partial sandbox: log only, don't execute
        logger.warning(
            "Sandbox mode 'partial': Logging shutdown request (not executing)"
        )
        return {
            "scheduled": False,
            "effective_after_seconds": delay_seconds,
            "sandbox_mode": sandbox_mode,
            "logged_only": True,
        }

    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for shutdown operation",
                details={"operation": "system.shutdown"},
            )

        try:
            result = await ipc_client.call(
                "system.shutdown",
                {
                    "reason": reason,
                    "delay_seconds": delay_seconds,
                    "caller": ctx.caller.to_dict(),
                },
            )
            return {
                "scheduled": True,
                "effective_after_seconds": delay_seconds,
                "sandbox_mode": sandbox_mode,
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to execute shutdown via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"reason": reason, "delay_seconds": delay_seconds},
            )
            raise UnavailableError(
                f"Failed to execute shutdown: {e}",
                details={"operation": "system.shutdown"},
            ) from e
