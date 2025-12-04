"""
Tests for I2C agent handlers.

This test module validates the I2C handlers in the privileged agent:
- i2c.scan: Scan I2C bus for devices
- i2c.read: Read bytes from I2C device
- i2c.write: Write bytes to I2C device

These tests use mocked smbus2 to avoid hardware dependencies.
"""

from __future__ import annotations

import pytest

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi_ops.handlers.i2c import (
    handle_i2c_read,
    handle_i2c_scan,
    handle_i2c_write,
    register_i2c_handlers,
)
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

# =============================================================================
# Tests for i2c.scan Handler
# =============================================================================


class TestI2cScanHandler:
    """Tests for i2c.scan handler."""

    @pytest.mark.asyncio
    async def test_scan_valid_bus(self) -> None:
        """Test scanning a valid bus."""
        request = IPCRequest.create(
            operation="i2c.scan",
            params={"bus": 1},
        )
        result = await handle_i2c_scan(request)
        assert result["bus"] == 1
        assert isinstance(result["addresses"], list)

    @pytest.mark.asyncio
    async def test_scan_invalid_bus(self) -> None:
        """Test scanning an invalid bus number."""
        request = IPCRequest.create(
            operation="i2c.scan",
            params={"bus": 99},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_scan(request)
        assert exc_info.value.code == "invalid_argument"
        assert "Bus number must be between 0 and 10" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_scan_missing_bus(self) -> None:
        """Test scanning without bus parameter."""
        request = IPCRequest.create(
            operation="i2c.scan",
            params={},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_scan(request)
        assert exc_info.value.code == "invalid_argument"
        assert "bus" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_scan_string_bus_converted(self) -> None:
        """Test that string bus numbers are converted."""
        request = IPCRequest.create(
            operation="i2c.scan",
            params={"bus": "1"},
        )
        result = await handle_i2c_scan(request)
        assert result["bus"] == 1


# =============================================================================
# Tests for i2c.read Handler
# =============================================================================


class TestI2cReadHandler:
    """Tests for i2c.read handler."""

    @pytest.mark.asyncio
    async def test_read_valid_request(self) -> None:
        """Test reading from a valid address."""
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x76, "length": 4},
        )
        result = await handle_i2c_read(request)
        assert result["bus"] == 1
        assert result["address"] == 0x76
        assert isinstance(result["data"], list)

    @pytest.mark.asyncio
    async def test_read_with_register(self) -> None:
        """Test reading with register address."""
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x76, "register": 0xD0, "length": 1},
        )
        result = await handle_i2c_read(request)
        assert result["register"] == 0xD0

    @pytest.mark.asyncio
    async def test_read_reserved_address_blocked(self) -> None:
        """Test that reserved addresses are blocked."""
        # Address 0x00 is reserved
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x00, "length": 1},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_read(request)
        assert exc_info.value.code == "permission_denied"
        assert "reserved" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_read_reserved_high_address_blocked(self) -> None:
        """Test that high reserved addresses are blocked."""
        # Address 0x78-0x7F are reserved
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x78, "length": 1},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_read(request)
        assert exc_info.value.code == "permission_denied"

    @pytest.mark.asyncio
    async def test_read_invalid_address(self) -> None:
        """Test reading from invalid address."""
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x100, "length": 1},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_read(request)
        assert exc_info.value.code == "invalid_argument"
        assert "Address must be between" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_read_hex_string_address(self) -> None:
        """Test reading with hex string address."""
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": "0x76", "length": 1},
        )
        result = await handle_i2c_read(request)
        assert result["address"] == 0x76

    @pytest.mark.asyncio
    async def test_read_length_validation(self) -> None:
        """Test length parameter validation."""
        # Length too large
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x76, "length": 100},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_read(request)
        assert exc_info.value.code == "invalid_argument"
        assert "Length must be between 1 and 32" in exc_info.value.message

        # Length zero
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x76, "length": 0},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_read(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_read_missing_length(self) -> None:
        """Test reading without length parameter."""
        request = IPCRequest.create(
            operation="i2c.read",
            params={"bus": 1, "address": 0x76},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_read(request)
        assert exc_info.value.code == "invalid_argument"
        assert "length" in exc_info.value.message.lower()


# =============================================================================
# Tests for i2c.write Handler
# =============================================================================


class TestI2cWriteHandler:
    """Tests for i2c.write handler."""

    @pytest.mark.asyncio
    async def test_write_valid_request(self) -> None:
        """Test writing to a valid address."""
        request = IPCRequest.create(
            operation="i2c.write",
            params={"bus": 1, "address": 0x76, "data": [0x01, 0x02]},
        )
        result = await handle_i2c_write(request)
        assert result["bus"] == 1
        assert result["address"] == 0x76
        assert result["bytes_written"] == 2

    @pytest.mark.asyncio
    async def test_write_with_register(self) -> None:
        """Test writing with register address."""
        request = IPCRequest.create(
            operation="i2c.write",
            params={
                "bus": 1,
                "address": 0x76,
                "register": 0xF4,
                "data": [0x2E],
            },
        )
        result = await handle_i2c_write(request)
        assert result["register"] == 0xF4

    @pytest.mark.asyncio
    async def test_write_reserved_address_blocked(self) -> None:
        """Test that reserved addresses are blocked for writes."""
        request = IPCRequest.create(
            operation="i2c.write",
            params={"bus": 1, "address": 0x00, "data": [0x01]},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_write(request)
        assert exc_info.value.code == "permission_denied"

    @pytest.mark.asyncio
    async def test_write_data_validation(self) -> None:
        """Test data parameter validation."""
        # Empty data
        request = IPCRequest.create(
            operation="i2c.write",
            params={"bus": 1, "address": 0x76, "data": []},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_write(request)
        assert exc_info.value.code == "invalid_argument"
        assert "Data length must be between" in exc_info.value.message

        # Data too long
        request = IPCRequest.create(
            operation="i2c.write",
            params={"bus": 1, "address": 0x76, "data": [0x00] * 100},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_write(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_write_invalid_byte_value(self) -> None:
        """Test writing with invalid byte value."""
        request = IPCRequest.create(
            operation="i2c.write",
            params={"bus": 1, "address": 0x76, "data": [256]},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_write(request)
        assert exc_info.value.code == "invalid_argument"
        assert "must be between 0 and 255" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_write_negative_byte_value(self) -> None:
        """Test writing with negative byte value."""
        request = IPCRequest.create(
            operation="i2c.write",
            params={"bus": 1, "address": 0x76, "data": [-1]},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_write(request)
        assert exc_info.value.code == "invalid_argument"

    @pytest.mark.asyncio
    async def test_write_missing_data(self) -> None:
        """Test writing without data parameter."""
        request = IPCRequest.create(
            operation="i2c.write",
            params={"bus": 1, "address": 0x76},
        )
        with pytest.raises(HandlerError) as exc_info:
            await handle_i2c_write(request)
        assert exc_info.value.code == "invalid_argument"
        assert "data" in exc_info.value.message.lower()


# =============================================================================
# Tests for Handler Registration
# =============================================================================


class TestI2cHandlerRegistration:
    """Tests for I2C handler registration."""

    def test_register_i2c_handlers(self) -> None:
        """Test that I2C handlers are registered correctly."""
        registry = HandlerRegistry()
        register_i2c_handlers(registry)

        assert registry.has_handler("i2c.scan")
        assert registry.has_handler("i2c.read")
        assert registry.has_handler("i2c.write")

    @pytest.mark.asyncio
    async def test_dispatch_i2c_scan(self) -> None:
        """Test dispatching i2c.scan through registry."""
        registry = HandlerRegistry()
        register_i2c_handlers(registry)

        request = IPCRequest.create(
            operation="i2c.scan",
            params={"bus": 1},
        )
        result = await registry.dispatch(request)
        assert result["bus"] == 1

        request = IPCRequest.create(
            operation="i2c.scan",
            params={"bus": 1},
        )
        result = await registry.dispatch(request)
        assert result["bus"] == 1
