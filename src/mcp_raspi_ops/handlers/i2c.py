"""
I2C device handlers for the Privileged Agent.

This module implements handlers for I2C operations using smbus2:
- i2c.scan: Scan I2C bus for devices
- i2c.read: Read bytes from I2C device
- i2c.write: Write bytes to I2C device

These handlers run with elevated privileges and execute actual hardware operations.

Design follows Doc 08 §4 (I2C Design).
"""

from __future__ import annotations

from typing import Any

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

logger = get_logger(__name__)

# Try to import smbus2 for actual hardware access
try:
    import smbus2

    SMBUS2_AVAILABLE = True
except ImportError:  # pragma: no cover
    SMBUS2_AVAILABLE = False
    logger.warning("smbus2 not available - I2C operations will be mocked")


# =============================================================================
# Constants
# =============================================================================

# Reserved I2C addresses (blocked by default)
RESERVED_ADDRESSES = list(range(0x00, 0x08)) + list(range(0x78, 0x80))


# =============================================================================
# Helper Functions
# =============================================================================


def _validate_bus(bus: Any) -> int:
    """
    Validate and convert bus number.

    Args:
        bus: Raw bus value from request params.

    Returns:
        Validated bus number as integer.

    Raises:
        HandlerError: If bus is invalid.
    """
    if bus is None:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'bus' is required",
            details={"parameter": "bus"},
        )

    if not isinstance(bus, int):
        try:
            bus = int(bus)
        except (ValueError, TypeError) as e:
            raise HandlerError(
                code="invalid_argument",
                message=f"Invalid bus number: {bus}",
                details={"parameter": "bus", "value": bus},
            ) from e

    if bus < 0 or bus > 10:
        raise HandlerError(
            code="invalid_argument",
            message=f"Bus number must be between 0 and 10, got {bus}",
            details={"parameter": "bus", "value": bus, "min": 0, "max": 10},
        )

    return bus


def _validate_address(address: Any) -> int:
    """
    Validate and convert I2C address.

    Args:
        address: Raw address value from request params.

    Returns:
        Validated address as integer.

    Raises:
        HandlerError: If address is invalid.
    """
    if address is None:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'address' is required",
            details={"parameter": "address"},
        )

    if not isinstance(address, int):
        try:
            # Support hex strings
            if isinstance(address, str) and address.lower().startswith("0x"):
                address = int(address, 16)
            else:
                address = int(address)
        except (ValueError, TypeError) as e:
            raise HandlerError(
                code="invalid_argument",
                message=f"Invalid address: {address}",
                details={"parameter": "address", "value": address},
            ) from e

    if address < 0x00 or address > 0x7F:
        raise HandlerError(
            code="invalid_argument",
            message=f"Address must be between 0x00 and 0x7F, got {address:#04x}",
            details={"parameter": "address", "value": address, "min": 0, "max": 0x7F},
        )

    # Check reserved addresses
    if address in RESERVED_ADDRESSES:
        raise HandlerError(
            code="permission_denied",
            message=f"Address {address:#04x} is a reserved I2C address",
            details={"parameter": "address", "value": address, "reserved": True},
        )

    return address


def _validate_register(register: Any) -> int | None:
    """
    Validate optional register value.

    Args:
        register: Raw register value from request params.

    Returns:
        Validated register as integer, or None if not provided.

    Raises:
        HandlerError: If register is invalid.
    """
    if register is None:
        return None

    if not isinstance(register, int):
        try:
            if isinstance(register, str) and register.lower().startswith("0x"):
                register = int(register, 16)
            else:
                register = int(register)
        except (ValueError, TypeError) as e:
            raise HandlerError(
                code="invalid_argument",
                message=f"Invalid register: {register}",
                details={"parameter": "register", "value": register},
            ) from e

    if register < 0x00 or register > 0xFF:
        raise HandlerError(
            code="invalid_argument",
            message=f"Register must be between 0x00 and 0xFF, got {register:#04x}",
            details={"parameter": "register", "value": register, "min": 0, "max": 0xFF},
        )

    return register


def _validate_length(length: Any) -> int:
    """
    Validate data length.

    Args:
        length: Raw length value from request params.

    Returns:
        Validated length as integer.

    Raises:
        HandlerError: If length is invalid.
    """
    if length is None:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'length' is required",
            details={"parameter": "length"},
        )

    if not isinstance(length, int):
        try:
            length = int(length)
        except (ValueError, TypeError) as e:
            raise HandlerError(
                code="invalid_argument",
                message=f"Invalid length: {length}",
                details={"parameter": "length", "value": length},
            ) from e

    if length < 1 or length > 32:
        raise HandlerError(
            code="invalid_argument",
            message=f"Length must be between 1 and 32, got {length}",
            details={"parameter": "length", "value": length, "min": 1, "max": 32},
        )

    return length


def _validate_data(data: Any) -> list[int]:
    """
    Validate data bytes for write operations.

    Args:
        data: Raw data value from request params.

    Returns:
        Validated list of bytes.

    Raises:
        HandlerError: If data is invalid.
    """
    if data is None:
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'data' is required",
            details={"parameter": "data"},
        )

    if not isinstance(data, list):
        raise HandlerError(
            code="invalid_argument",
            message="Parameter 'data' must be an array of integers",
            details={"parameter": "data", "type": type(data).__name__},
        )

    if len(data) < 1 or len(data) > 32:
        raise HandlerError(
            code="invalid_argument",
            message=f"Data length must be between 1 and 32, got {len(data)}",
            details={"parameter": "data", "length": len(data), "min": 1, "max": 32},
        )

    validated_data = []
    for i, byte_val in enumerate(data):
        if not isinstance(byte_val, int):
            try:
                byte_val = int(byte_val)
            except (ValueError, TypeError) as e:
                raise HandlerError(
                    code="invalid_argument",
                    message=f"Invalid byte value at index {i}: {byte_val}",
                    details={"parameter": "data", "index": i, "value": byte_val},
                ) from e

        if byte_val < 0 or byte_val > 255:
            raise HandlerError(
                code="invalid_argument",
                message=f"Byte value at index {i} must be between 0 and 255",
                details={"parameter": "data", "index": i, "value": byte_val},
            )

        validated_data.append(byte_val)

    return validated_data


# =============================================================================
# i2c.scan Handler
# =============================================================================


async def handle_i2c_scan(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the i2c.scan operation.

    Scans an I2C bus for connected devices.

    Args:
        request: IPC request with params:
            - bus: I2C bus number to scan

    Returns:
        Dict with bus number and list of detected addresses.

    Raises:
        HandlerError: If scan fails.
    """
    params = request.params
    bus = _validate_bus(params.get("bus"))
    caller = params.get("caller", {})

    logger.info(
        "I2C scan request",
        extra={
            "request_id": request.id,
            "bus": bus,
            "caller_user_id": caller.get("user_id"),
        },
    )

    if not SMBUS2_AVAILABLE:
        # Mock mode - return common sensor addresses for bus 1
        logger.info(f"I2C scan (mocked): bus={bus}")
        mock_addresses = [0x76, 0x77] if bus == 1 else []
        return {
            "bus": bus,
            "addresses": mock_addresses,
            "mocked": True,
        }

    detected_addresses = []

    try:
        with smbus2.SMBus(bus) as i2c_bus:
            # Scan all non-reserved addresses
            for addr in range(0x08, 0x78):
                try:
                    # Try to read one byte from the address
                    i2c_bus.read_byte(addr)
                    detected_addresses.append(addr)
                except OSError:
                    # No device at this address
                    pass

        logger.info(
            f"I2C scan completed: bus={bus}, found {len(detected_addresses)} devices"
        )

        return {
            "bus": bus,
            "addresses": detected_addresses,
        }

    except FileNotFoundError as e:
        raise HandlerError(
            code="unavailable",
            message=f"I2C bus {bus} not found (device file missing)",
            details={"bus": bus, "error": str(e)},
        ) from e
    except PermissionError as e:
        raise HandlerError(
            code="permission_denied",
            message=f"Permission denied accessing I2C bus {bus}",
            details={"bus": bus, "error": str(e)},
        ) from e
    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to scan I2C bus {bus}: {e}",
            details={"bus": bus, "error": str(e)},
        ) from e


# =============================================================================
# i2c.read Handler
# =============================================================================


async def handle_i2c_read(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the i2c.read operation.

    Reads bytes from an I2C device.

    Args:
        request: IPC request with params:
            - bus: I2C bus number
            - address: Device address (0x08-0x77)
            - register: Optional starting register
            - length: Number of bytes to read (1-32)

    Returns:
        Dict with read data.

    Raises:
        HandlerError: If read fails.
    """
    params = request.params
    bus = _validate_bus(params.get("bus"))
    address = _validate_address(params.get("address"))
    register = _validate_register(params.get("register"))
    length = _validate_length(params.get("length"))
    caller = params.get("caller", {})

    logger.info(
        "I2C read request",
        extra={
            "request_id": request.id,
            "bus": bus,
            "address": f"{address:#04x}",
            "register": f"{register:#04x}" if register is not None else None,
            "length": length,
            "caller_user_id": caller.get("user_id"),
        },
    )

    if not SMBUS2_AVAILABLE:
        # Mock mode - return zeros
        logger.info(f"I2C read (mocked): bus={bus}, addr={address:#04x}, len={length}")
        return {
            "bus": bus,
            "address": address,
            "register": register,
            "data": [0x00] * length,
            "mocked": True,
        }

    try:
        with smbus2.SMBus(bus) as i2c_bus:
            if register is not None:
                # Read with register address
                if length == 1:
                    data = [i2c_bus.read_byte_data(address, register)]
                else:
                    # Read block of data starting at register
                    data = i2c_bus.read_i2c_block_data(address, register, length)
            else:
                # Read without register
                if length == 1:
                    data = [i2c_bus.read_byte(address)]
                else:
                    # Read multiple bytes
                    data = []
                    for _ in range(length):
                        data.append(i2c_bus.read_byte(address))

        logger.debug(f"I2C read completed: {len(data)} bytes from {address:#04x}")

        return {
            "bus": bus,
            "address": address,
            "register": register,
            "data": data,
        }

    except FileNotFoundError as e:
        raise HandlerError(
            code="unavailable",
            message=f"I2C bus {bus} not found",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e
    except PermissionError as e:
        raise HandlerError(
            code="permission_denied",
            message=f"Permission denied accessing I2C bus {bus}",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e
    except OSError as e:
        raise HandlerError(
            code="failed_precondition",
            message=f"I2C read failed (device may not be responding): {e}",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e
    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to read from I2C device: {e}",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e


# =============================================================================
# i2c.write Handler
# =============================================================================


async def handle_i2c_write(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the i2c.write operation.

    Writes bytes to an I2C device.

    Args:
        request: IPC request with params:
            - bus: I2C bus number
            - address: Device address (0x08-0x77)
            - register: Optional starting register
            - data: List of bytes to write (1-32)

    Returns:
        Dict with write confirmation.

    Raises:
        HandlerError: If write fails.
    """
    params = request.params
    bus = _validate_bus(params.get("bus"))
    address = _validate_address(params.get("address"))
    register = _validate_register(params.get("register"))
    data = _validate_data(params.get("data"))
    caller = params.get("caller", {})

    logger.info(
        "I2C write request",
        extra={
            "request_id": request.id,
            "bus": bus,
            "address": f"{address:#04x}",
            "register": f"{register:#04x}" if register is not None else None,
            "data_length": len(data),
            "caller_user_id": caller.get("user_id"),
        },
    )

    if not SMBUS2_AVAILABLE:
        # Mock mode
        logger.info(
            f"I2C write (mocked): bus={bus}, addr={address:#04x}, len={len(data)}"
        )
        return {
            "bus": bus,
            "address": address,
            "register": register,
            "bytes_written": len(data),
            "mocked": True,
        }

    try:
        with smbus2.SMBus(bus) as i2c_bus:
            if register is not None:
                # Write with register address
                if len(data) == 1:
                    i2c_bus.write_byte_data(address, register, data[0])
                else:
                    # Write block of data starting at register
                    i2c_bus.write_i2c_block_data(address, register, data)
            else:
                # Write without register
                if len(data) == 1:
                    i2c_bus.write_byte(address, data[0])
                else:
                    # Write multiple bytes
                    for byte_val in data:
                        i2c_bus.write_byte(address, byte_val)

        logger.debug(f"I2C write completed: {len(data)} bytes to {address:#04x}")

        return {
            "bus": bus,
            "address": address,
            "register": register,
            "bytes_written": len(data),
        }

    except FileNotFoundError as e:
        raise HandlerError(
            code="unavailable",
            message=f"I2C bus {bus} not found",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e
    except PermissionError as e:
        raise HandlerError(
            code="permission_denied",
            message=f"Permission denied accessing I2C bus {bus}",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e
    except OSError as e:
        raise HandlerError(
            code="failed_precondition",
            message=f"I2C write failed (device may not be responding): {e}",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e
    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to write to I2C device: {e}",
            details={"bus": bus, "address": address, "error": str(e)},
        ) from e


# =============================================================================
# Handler Registration
# =============================================================================


def register_i2c_handlers(registry: HandlerRegistry) -> None:
    """
    Register I2C handlers with the handler registry.

    Args:
        registry: The handler registry to register with.
    """
    registry.register("i2c.scan", handle_i2c_scan)
    registry.register("i2c.read", handle_i2c_read)
    registry.register("i2c.write", handle_i2c_write)
    logger.debug("Registered I2C handlers")
