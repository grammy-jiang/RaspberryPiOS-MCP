"""
I2C namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `i2c.*` namespace:
- i2c.scan_bus: Detect devices on I2C bus
- i2c.read: Read bytes from I2C device with address whitelist
- i2c.write: Write bytes to I2C device with address whitelist

Design follows Doc 05 §6 (i2c namespace specification) and Doc 08 §4 (I2C design).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import (
    FailedPreconditionError,
    InvalidArgumentError,
    UnavailableError,
)
from mcp_raspi.logging import get_logger
from mcp_raspi.security.audit_logger import get_audit_logger
from mcp_raspi.security.rbac import PermissionDeniedError, require_role

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig, I2CBusConfig

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Valid I2C bus range
MIN_BUS_NUMBER = 0
MAX_BUS_NUMBER = 10

# Valid I2C address range (7-bit addressing)
MIN_I2C_ADDRESS = 0x00
MAX_I2C_ADDRESS = 0x7F

# Reserved I2C addresses (should be blocked by default)
# 0x00-0x07: Reserved for special purposes
# 0x78-0x7F: Reserved for 10-bit addressing and other uses
RESERVED_I2C_ADDRESSES = (
    list(range(0x00, 0x08)) + list(range(0x78, 0x80))
)

# Valid I2C register range
MIN_REGISTER = 0x00
MAX_REGISTER = 0xFF

# Maximum bytes per I2C read/write operation
MIN_DATA_LENGTH = 1
MAX_DATA_LENGTH = 32


# =============================================================================
# Validation Helpers
# =============================================================================


def _validate_bus_number(bus: Any) -> int:
    """
    Validate I2C bus number.

    Args:
        bus: Raw bus value from params.

    Returns:
        Validated bus number as integer.

    Raises:
        InvalidArgumentError: If bus number is invalid.
    """
    if bus is None:
        raise InvalidArgumentError(
            "Parameter 'bus' is required",
            details={"parameter": "bus"},
        )

    if not isinstance(bus, int):
        try:
            bus = int(bus)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid bus number: {bus}",
                details={"parameter": "bus", "value": bus},
            ) from e

    if bus < MIN_BUS_NUMBER or bus > MAX_BUS_NUMBER:
        raise InvalidArgumentError(
            f"Bus number must be between {MIN_BUS_NUMBER} and {MAX_BUS_NUMBER}",
            details={
                "parameter": "bus",
                "value": bus,
                "min": MIN_BUS_NUMBER,
                "max": MAX_BUS_NUMBER,
            },
        )

    return bus


def _validate_i2c_address(address: Any) -> int:
    """
    Validate I2C device address.

    Args:
        address: Raw address value from params.

    Returns:
        Validated address as integer.

    Raises:
        InvalidArgumentError: If address is invalid.
    """
    if address is None:
        raise InvalidArgumentError(
            "Parameter 'address' is required",
            details={"parameter": "address"},
        )

    if not isinstance(address, int):
        try:
            # Support hex strings like "0x76"
            if isinstance(address, str) and address.lower().startswith("0x"):
                address = int(address, 16)
            else:
                address = int(address)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid I2C address: {address}",
                details={"parameter": "address", "value": address},
            ) from e

    if address < MIN_I2C_ADDRESS or address > MAX_I2C_ADDRESS:
        raise InvalidArgumentError(
            f"I2C address must be between {MIN_I2C_ADDRESS:#04x} and {MAX_I2C_ADDRESS:#04x}",
            details={
                "parameter": "address",
                "value": address,
                "min": MIN_I2C_ADDRESS,
                "max": MAX_I2C_ADDRESS,
            },
        )

    return address


def _validate_register(register: Any) -> int | None:
    """
    Validate optional I2C register.

    Args:
        register: Raw register value from params.

    Returns:
        Validated register as integer, or None if not provided.

    Raises:
        InvalidArgumentError: If register is invalid.
    """
    if register is None:
        return None

    if not isinstance(register, int):
        try:
            # Support hex strings like "0x00"
            if isinstance(register, str) and register.lower().startswith("0x"):
                register = int(register, 16)
            else:
                register = int(register)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid register: {register}",
                details={"parameter": "register", "value": register},
            ) from e

    if register < MIN_REGISTER or register > MAX_REGISTER:
        raise InvalidArgumentError(
            f"Register must be between {MIN_REGISTER:#04x} and {MAX_REGISTER:#04x}",
            details={
                "parameter": "register",
                "value": register,
                "min": MIN_REGISTER,
                "max": MAX_REGISTER,
            },
        )

    return register


def _validate_data_length(length: Any) -> int:
    """
    Validate data length for read operations.

    Args:
        length: Raw length value from params.

    Returns:
        Validated length as integer.

    Raises:
        InvalidArgumentError: If length is invalid.
    """
    if length is None:
        raise InvalidArgumentError(
            "Parameter 'length' is required",
            details={"parameter": "length"},
        )

    if not isinstance(length, int):
        try:
            length = int(length)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid length: {length}",
                details={"parameter": "length", "value": length},
            ) from e

    if length < MIN_DATA_LENGTH or length > MAX_DATA_LENGTH:
        raise InvalidArgumentError(
            f"Length must be between {MIN_DATA_LENGTH} and {MAX_DATA_LENGTH}",
            details={
                "parameter": "length",
                "value": length,
                "min": MIN_DATA_LENGTH,
                "max": MAX_DATA_LENGTH,
            },
        )

    return length


def _validate_data_bytes(data: Any) -> list[int]:
    """
    Validate data bytes for write operations.

    Args:
        data: Raw data value from params (list of integers 0-255).

    Returns:
        Validated list of bytes.

    Raises:
        InvalidArgumentError: If data is invalid.
    """
    if data is None:
        raise InvalidArgumentError(
            "Parameter 'data' is required",
            details={"parameter": "data"},
        )

    if not isinstance(data, list):
        raise InvalidArgumentError(
            "Parameter 'data' must be an array of integers",
            details={"parameter": "data", "type": type(data).__name__},
        )

    if len(data) < MIN_DATA_LENGTH or len(data) > MAX_DATA_LENGTH:
        raise InvalidArgumentError(
            f"Data length must be between {MIN_DATA_LENGTH} and {MAX_DATA_LENGTH}",
            details={
                "parameter": "data",
                "length": len(data),
                "min": MIN_DATA_LENGTH,
                "max": MAX_DATA_LENGTH,
            },
        )

    validated_data = []
    for i, byte_val in enumerate(data):
        if not isinstance(byte_val, int):
            try:
                byte_val = int(byte_val)
            except (ValueError, TypeError) as e:
                raise InvalidArgumentError(
                    f"Invalid byte value at index {i}: {byte_val}",
                    details={"parameter": "data", "index": i, "value": byte_val},
                ) from e

        if byte_val < 0 or byte_val > 255:
            raise InvalidArgumentError(
                f"Byte value at index {i} must be between 0 and 255",
                details={
                    "parameter": "data",
                    "index": i,
                    "value": byte_val,
                    "min": 0,
                    "max": 255,
                },
            )

        validated_data.append(byte_val)

    return validated_data


def _get_bus_config(config: AppConfig | None, bus: int) -> I2CBusConfig | None:
    """
    Get I2C bus configuration for a specific bus.

    Args:
        config: Optional AppConfig instance.
        bus: Bus number.

    Returns:
        I2CBusConfig if found, None otherwise.
    """
    if config is None:
        return None

    for bus_config in config.i2c.buses:
        if bus_config.bus == bus:
            return bus_config

    return None


def _is_address_allowed(
    address: int,
    bus_config: I2CBusConfig | None,
    operation: str,
) -> tuple[bool, str | None]:
    """
    Check if an I2C address is allowed for the operation.

    Args:
        address: I2C device address.
        bus_config: Bus configuration with whitelist/blacklist.
        operation: Operation type for mode check.

    Returns:
        Tuple of (is_allowed, reason_if_denied).
    """
    # Check reserved addresses
    if address in RESERVED_I2C_ADDRESSES:
        return False, f"Address {address:#04x} is a reserved I2C address"

    # If no bus config, deny by default
    if bus_config is None:
        return False, "No I2C bus configuration found"

    # Check bus mode
    if bus_config.mode == "disabled":
        return False, "I2C bus is disabled"

    if bus_config.mode == "read_only" and operation == "write":
        return False, "I2C bus is configured as read-only"

    # Check deny list (blacklist)
    if address in bus_config.deny_addresses:
        return False, f"Address {address:#04x} is in the deny list"

    # Check allow list (whitelist)
    # If allow list is not empty, address must be in it
    if bus_config.allow_addresses and address not in bus_config.allow_addresses:
        return False, f"Address {address:#04x} is not in the allow list"

    return True, None


def _get_sandbox_mode(config: AppConfig | None) -> str:
    """
    Get sandbox mode from configuration.

    Args:
        config: Optional AppConfig instance.

    Returns:
        Sandbox mode string.
    """
    if config is None:
        return "partial"
    return config.testing.sandbox_mode


# =============================================================================
# i2c.scan_bus
# =============================================================================


@require_role("operator")
async def handle_i2c_scan_bus(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the i2c.scan_bus tool call.

    Scans an I2C bus and returns detected device addresses.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - bus: I2C bus number to scan
        config: Optional AppConfig for sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - bus: The bus number scanned
        - addresses: List of detected device addresses
        - timestamp: ISO 8601 timestamp

    Raises:
        PermissionDeniedError: If caller lacks operator role.
        InvalidArgumentError: If bus number is invalid.
        UnavailableError: If privileged agent is unavailable.
    """
    bus = _validate_bus_number(params.get("bus"))
    sandbox_mode = _get_sandbox_mode(config)
    bus_config = _get_bus_config(config, bus)

    # Check if bus is disabled
    if bus_config and bus_config.mode == "disabled":
        raise FailedPreconditionError(
            f"I2C bus {bus} is disabled",
            details={"bus": bus, "mode": "disabled"},
        )

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"bus": bus},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "I2C scan_bus requested",
        extra={
            "user": ctx.caller.user_id,
            "bus": bus,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking I2C scan")
        # Return mock detected addresses
        mock_addresses = [0x76, 0x77] if bus == 1 else []
        return {
            "bus": bus,
            "addresses": mock_addresses,
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging I2C scan (not executing)")
        return {
            "bus": bus,
            "addresses": [],
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for I2C scan operation",
                details={"operation": "i2c.scan_bus", "bus": bus},
            )

        try:
            result = await ipc_client.call(
                "i2c.scan",
                {"bus": bus, "caller": ctx.caller.to_dict()},
            )
            return {
                "bus": bus,
                "addresses": result.get("addresses", []),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to scan I2C bus via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"bus": bus},
            )
            raise UnavailableError(
                f"Failed to scan I2C bus: {e}",
                details={"operation": "i2c.scan_bus", "bus": bus},
            ) from e


# =============================================================================
# i2c.read
# =============================================================================


@require_role("operator")
async def handle_i2c_read(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the i2c.read tool call.

    Reads bytes from an I2C device with address whitelist enforcement.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - bus: I2C bus number
            - address: I2C device address (0-127)
            - register: Optional starting register address
            - length: Number of bytes to read (1-32)
        config: Optional AppConfig for whitelist and sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - bus: The bus number
        - address: The device address
        - register: The register (if specified)
        - data: List of bytes read
        - timestamp: ISO 8601 timestamp

    Raises:
        PermissionDeniedError: If caller lacks operator role or address not whitelisted.
        InvalidArgumentError: If parameters are invalid.
        UnavailableError: If privileged agent is unavailable.
    """
    bus = _validate_bus_number(params.get("bus"))
    address = _validate_i2c_address(params.get("address"))
    register = _validate_register(params.get("register"))
    length = _validate_data_length(params.get("length"))
    sandbox_mode = _get_sandbox_mode(config)
    bus_config = _get_bus_config(config, bus)

    # Check address whitelist
    allowed, reason = _is_address_allowed(address, bus_config, "read")
    if not allowed:
        raise PermissionDeniedError(
            f"I2C address {address:#04x} is not allowed: {reason}",
            details={
                "bus": bus,
                "address": address,
                "operation": "i2c.read",
                "reason": reason,
            },
        )

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"bus": bus, "address": address, "register": register, "length": length},
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "I2C read requested",
        extra={
            "user": ctx.caller.user_id,
            "bus": bus,
            "address": address,
            "register": register,
            "length": length,
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking I2C read")
        mock_data = [0x00] * length
        return {
            "bus": bus,
            "address": address,
            "register": register,
            "data": mock_data,
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging I2C read (not executing)")
        return {
            "bus": bus,
            "address": address,
            "register": register,
            "data": [],
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for I2C read operation",
                details={"operation": "i2c.read", "bus": bus, "address": address},
            )

        try:
            result = await ipc_client.call(
                "i2c.read",
                {
                    "bus": bus,
                    "address": address,
                    "register": register,
                    "length": length,
                    "caller": ctx.caller.to_dict(),
                },
            )
            return {
                "bus": bus,
                "address": address,
                "register": register,
                "data": result.get("data", []),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to read from I2C device via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"bus": bus, "address": address},
            )
            raise UnavailableError(
                f"Failed to read from I2C device: {e}",
                details={"operation": "i2c.read", "bus": bus, "address": address},
            ) from e


# =============================================================================
# i2c.write
# =============================================================================


@require_role("operator")
async def handle_i2c_write(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
    ipc_client: Any | None = None,
) -> dict[str, Any]:
    """
    Handle the i2c.write tool call.

    Writes bytes to an I2C device with address whitelist enforcement.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - bus: I2C bus number
            - address: I2C device address (0-127)
            - register: Optional starting register address
            - data: List of bytes to write (1-32 bytes)
        config: Optional AppConfig for whitelist and sandbox mode.
        ipc_client: Optional IPC client for agent communication.

    Returns:
        Dictionary with:
        - bus: The bus number
        - address: The device address
        - register: The register (if specified)
        - bytes_written: Number of bytes written
        - timestamp: ISO 8601 timestamp

    Raises:
        PermissionDeniedError: If caller lacks operator role or address not whitelisted.
        InvalidArgumentError: If parameters are invalid.
        UnavailableError: If privileged agent is unavailable.
    """
    bus = _validate_bus_number(params.get("bus"))
    address = _validate_i2c_address(params.get("address"))
    register = _validate_register(params.get("register"))
    data = _validate_data_bytes(params.get("data"))
    sandbox_mode = _get_sandbox_mode(config)
    bus_config = _get_bus_config(config, bus)

    # Check address whitelist for write
    allowed, reason = _is_address_allowed(address, bus_config, "write")
    if not allowed:
        raise PermissionDeniedError(
            f"I2C write to address {address:#04x} is not allowed: {reason}",
            details={
                "bus": bus,
                "address": address,
                "operation": "i2c.write",
                "reason": reason,
            },
        )

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={
            "bus": bus,
            "address": address,
            "register": register,
            "data_length": len(data),
        },
        extra={"sandbox_mode": sandbox_mode},
    )

    logger.info(
        "I2C write requested",
        extra={
            "user": ctx.caller.user_id,
            "bus": bus,
            "address": address,
            "register": register,
            "data_length": len(data),
            "sandbox_mode": sandbox_mode,
        },
    )

    # Handle based on sandbox mode
    if sandbox_mode == "full":
        logger.info("Sandbox mode 'full': Mocking I2C write")
        return {
            "bus": bus,
            "address": address,
            "register": register,
            "bytes_written": len(data),
            "timestamp": datetime.now(UTC).isoformat(),
            "mocked": True,
        }
    elif sandbox_mode == "partial":
        logger.warning("Sandbox mode 'partial': Logging I2C write (not executing)")
        return {
            "bus": bus,
            "address": address,
            "register": register,
            "bytes_written": 0,
            "timestamp": datetime.now(UTC).isoformat(),
            "logged_only": True,
        }
    else:
        # Disabled sandbox: execute via agent
        if ipc_client is None:
            raise UnavailableError(
                "Privileged agent not available for I2C write operation",
                details={"operation": "i2c.write", "bus": bus, "address": address},
            )

        try:
            result = await ipc_client.call(
                "i2c.write",
                {
                    "bus": bus,
                    "address": address,
                    "register": register,
                    "data": data,
                    "caller": ctx.caller.to_dict(),
                },
            )
            return {
                "bus": bus,
                "address": address,
                "register": register,
                "bytes_written": result.get("bytes_written", len(data)),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to write to I2C device via agent: {e}")
            audit.log_tool_call(
                ctx=ctx,
                status="error",
                error_code="unavailable",
                params={"bus": bus, "address": address},
            )
            raise UnavailableError(
                f"Failed to write to I2C device: {e}",
                details={"operation": "i2c.write", "bus": bus, "address": address},
            ) from e
