"""
Tests for the MCP Server.

This test module validates:
- MCPServer reads from stdin and writes to stdout
- Valid requests route to correct handler
- Invalid requests return proper error responses
- Integration testing of the full request/response cycle
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.routing import ToolRegistry
from mcp_raspi.server import MCPServer, process_request

# =============================================================================
# Helper Functions and Fixtures
# =============================================================================


async def mock_basic_info_handler(
    _ctx: ToolContext, _params: dict[str, Any]
) -> dict[str, Any]:
    """Mock handler for system.get_basic_info."""
    return {
        "hostname": "raspberrypi",
        "model": "Raspberry Pi 4 Model B",
        "cpu_arch": "aarch64",
        "cpu_cores": 4,
        "memory_total_bytes": 4294967296,
        "os_name": "Raspberry Pi OS",
        "os_version": "12",
        "kernel_version": "6.1.21",
        "uptime_seconds": 3600,
    }


async def mock_echo_handler(
    _ctx: ToolContext, params: dict[str, Any]
) -> dict[str, Any]:
    """Mock handler that echoes parameters."""
    return {"echo": params}


async def mock_error_handler(
    _ctx: ToolContext, params: dict[str, Any]
) -> dict[str, Any]:
    """Mock handler that raises an error."""
    raise InvalidArgumentError(
        message="Invalid parameter",
        details={"param": params.get("bad_param")},
    )


@pytest.fixture
def registry() -> ToolRegistry:
    """Create a test registry with mock handlers."""
    reg = ToolRegistry()
    reg.register("system.get_basic_info", mock_basic_info_handler)
    reg.register("system.echo", mock_echo_handler)
    reg.register("system.error", mock_error_handler)
    return reg


# =============================================================================
# Tests for process_request Function
# =============================================================================


class TestProcessRequest:
    """Tests for the process_request function."""

    @pytest.mark.asyncio
    async def test_valid_request(self, registry: ToolRegistry) -> None:
        """Test processing a valid request."""
        request_json = json.dumps({
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "system.get_basic_info",
            "params": {},
        })

        response = await process_request(request_json, registry)
        parsed = json.loads(response)

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "req-1"
        assert "result" in parsed
        assert parsed["result"]["hostname"] == "raspberrypi"

    @pytest.mark.asyncio
    async def test_request_with_params(self, registry: ToolRegistry) -> None:
        """Test processing a request with parameters."""
        request_json = json.dumps({
            "jsonrpc": "2.0",
            "id": "req-2",
            "method": "system.echo",
            "params": {"message": "hello"},
        })

        response = await process_request(request_json, registry)
        parsed = json.loads(response)

        assert parsed["result"]["echo"]["message"] == "hello"

    @pytest.mark.asyncio
    async def test_malformed_json(self, registry: ToolRegistry) -> None:
        """Test handling malformed JSON."""
        response = await process_request("{invalid json", registry)
        parsed = json.loads(response)

        assert "error" in parsed
        assert parsed["error"]["code"] == -32700  # Parse error
        assert parsed["id"] is None

    @pytest.mark.asyncio
    async def test_missing_jsonrpc_version(self, registry: ToolRegistry) -> None:
        """Test handling request without jsonrpc field."""
        request_json = json.dumps({
            "id": "req-3",
            "method": "system.get_basic_info",
            "params": {},
        })

        response = await process_request(request_json, registry)
        parsed = json.loads(response)

        assert "error" in parsed
        assert parsed["error"]["code"] == -32600  # Invalid Request

    @pytest.mark.asyncio
    async def test_tool_not_found(self, registry: ToolRegistry) -> None:
        """Test handling request for unknown tool."""
        request_json = json.dumps({
            "jsonrpc": "2.0",
            "id": "req-4",
            "method": "unknown.tool",
            "params": {},
        })

        response = await process_request(request_json, registry)
        parsed = json.loads(response)

        assert "error" in parsed
        assert parsed["error"]["code"] == -32003  # Not found
        assert parsed["error"]["data"]["error_code"] == "not_found"

    @pytest.mark.asyncio
    async def test_tool_error_mapping(self, registry: ToolRegistry) -> None:
        """Test that ToolError is mapped to JSON-RPC error."""
        request_json = json.dumps({
            "jsonrpc": "2.0",
            "id": "req-5",
            "method": "system.error",
            "params": {"bad_param": "value"},
        })

        response = await process_request(request_json, registry)
        parsed = json.loads(response)

        assert "error" in parsed
        assert parsed["error"]["code"] == -32602  # Invalid params
        assert parsed["error"]["data"]["error_code"] == "invalid_argument"

    @pytest.mark.asyncio
    async def test_numeric_request_id(self, registry: ToolRegistry) -> None:
        """Test handling request with numeric ID."""
        request_json = json.dumps({
            "jsonrpc": "2.0",
            "id": 42,
            "method": "system.get_basic_info",
            "params": {},
        })

        response = await process_request(request_json, registry)
        parsed = json.loads(response)

        assert parsed["id"] == 42
        assert "result" in parsed

    @pytest.mark.asyncio
    async def test_notification_no_response(self, registry: ToolRegistry) -> None:
        """Test that notifications (no id) return None (no response per JSON-RPC spec)."""
        request_json = json.dumps({
            "jsonrpc": "2.0",
            "method": "system.get_basic_info",
            "params": {},
        })

        response = await process_request(request_json, registry)

        # Notifications must return None per JSON-RPC 2.0 spec
        assert response is None


# =============================================================================
# Tests for MCPServer Class
# =============================================================================


class TestMCPServer:
    """Tests for MCPServer class."""

    def test_server_creation(self, registry: ToolRegistry) -> None:
        """Test creating an MCPServer instance."""
        server = MCPServer(registry=registry)

        assert server.registry is registry
        assert server.running is False

    def test_server_with_default_registry(self) -> None:
        """Test creating server with default registry."""
        server = MCPServer()

        assert server.registry is not None

    @pytest.mark.asyncio
    async def test_handle_single_request(self, registry: ToolRegistry) -> None:
        """Test handling a single request."""
        server = MCPServer(registry=registry)

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": "single-1",
            "method": "system.get_basic_info",
            "params": {},
        })

        response = await server.handle_request(request)
        parsed = json.loads(response)

        assert parsed["id"] == "single-1"
        assert "result" in parsed

    @pytest.mark.asyncio
    async def test_handle_multiple_requests(self, registry: ToolRegistry) -> None:
        """Test handling multiple sequential requests."""
        server = MCPServer(registry=registry)

        for i in range(3):
            request = json.dumps({
                "jsonrpc": "2.0",
                "id": f"multi-{i}",
                "method": "system.echo",
                "params": {"count": i},
            })

            response = await server.handle_request(request)
            parsed = json.loads(response)

            assert parsed["id"] == f"multi-{i}"
            assert parsed["result"]["echo"]["count"] == i


# =============================================================================
# Integration Tests
# =============================================================================


class TestServerIntegration:
    """Integration tests for the full request/response cycle."""

    @pytest.mark.asyncio
    async def test_full_cycle_success(self, registry: ToolRegistry) -> None:
        """Test complete request/response cycle for success case."""
        server = MCPServer(registry=registry)

        # Build request
        request = {
            "jsonrpc": "2.0",
            "id": "integration-1",
            "method": "system.get_basic_info",
            "params": {},
        }
        request_json = json.dumps(request)

        # Process request
        response_json = await server.handle_request(request_json)
        response = json.loads(response_json)

        # Validate response structure
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "integration-1"
        assert "result" in response
        assert "error" not in response

        # Validate result content
        result = response["result"]
        assert "hostname" in result
        assert "model" in result
        assert isinstance(result["cpu_cores"], int)

    @pytest.mark.asyncio
    async def test_full_cycle_error(self, registry: ToolRegistry) -> None:
        """Test complete request/response cycle for error case."""
        server = MCPServer(registry=registry)

        # Build invalid request
        request = {
            "jsonrpc": "2.0",
            "id": "integration-2",
            "method": "nonexistent.tool",
            "params": {},
        }
        request_json = json.dumps(request)

        # Process request
        response_json = await server.handle_request(request_json)
        response = json.loads(response_json)

        # Validate error response structure
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "integration-2"
        assert "error" in response
        assert "result" not in response

        # Validate error content
        error = response["error"]
        assert error["code"] == -32003
        assert "data" in error
        assert error["data"]["error_code"] == "not_found"

    @pytest.mark.asyncio
    async def test_parse_error_response(self, registry: ToolRegistry) -> None:
        """Test that parse errors produce valid error responses."""
        server = MCPServer(registry=registry)

        # Send completely invalid JSON
        response_json = await server.handle_request("not valid json at all {{{")
        response = json.loads(response_json)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] is None  # Parse errors have null id
        assert response["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, registry: ToolRegistry) -> None:
        """Test handling multiple concurrent requests."""
        server = MCPServer(registry=registry)

        # Create multiple requests
        requests = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": f"concurrent-{i}",
                "method": "system.echo",
                "params": {"index": i},
            })
            for i in range(10)
        ]

        # Process concurrently
        tasks = [server.handle_request(req) for req in requests]
        responses = await asyncio.gather(*tasks)

        # Validate all responses
        for i, response_json in enumerate(responses):
            response = json.loads(response_json)
            assert response["id"] == f"concurrent-{i}"
            assert response["result"]["echo"]["index"] == i
