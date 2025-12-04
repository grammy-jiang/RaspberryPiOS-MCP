"""
Tests for the JSON-RPC 2.0 protocol module.

This test module validates:
- JSON-RPC request parsing and validation
- JSON-RPC response formatting (success and error)
- Error code mapping from ToolError to JSON-RPC errors
- Edge cases: malformed JSON, missing fields, invalid values
"""

from __future__ import annotations

import json

import pytest

from mcp_raspi.errors import (
    FailedPreconditionError,
    InternalError,
    InvalidArgumentError,
    PermissionDeniedError,
    ToolError,
    UnavailableError,
)
from mcp_raspi.protocol import (
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    format_error_response,
    format_success_response,
    parse_request,
    tool_error_to_jsonrpc_error,
)

# =============================================================================
# Tests for JSONRPCRequest Parsing
# =============================================================================


class TestParseRequest:
    """Tests for JSON-RPC request parsing."""

    def test_parse_valid_request(self) -> None:
        """Test parsing a valid JSON-RPC 2.0 request."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "req-1",
                "method": "system.get_basic_info",
                "params": {},
            }
        )

        request = parse_request(request_json)

        assert request.jsonrpc == "2.0"
        assert request.id == "req-1"
        assert request.method == "system.get_basic_info"
        assert request.params == {}

    def test_parse_request_with_params(self) -> None:
        """Test parsing a request with parameters."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "req-2",
                "method": "gpio.write_pin",
                "params": {"pin": 17, "value": "high"},
            }
        )

        request = parse_request(request_json)

        assert request.params == {"pin": 17, "value": "high"}

    def test_parse_request_with_numeric_id(self) -> None:
        """Test parsing a request with numeric ID."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "system.get_basic_info",
                "params": {},
            }
        )

        request = parse_request(request_json)

        assert request.id == 42

    def test_parse_request_without_params(self) -> None:
        """Test parsing a request without params field (optional)."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "req-3",
                "method": "system.get_basic_info",
            }
        )

        request = parse_request(request_json)

        assert request.params == {}

    def test_parse_notification_without_id(self) -> None:
        """Test parsing a notification (request without id)."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "system.notify",
                "params": {},
            }
        )

        request = parse_request(request_json)

        assert request.id is None
        assert request.method == "system.notify"

    def test_parse_malformed_json(self) -> None:
        """Test handling malformed JSON."""
        malformed_json = "{not valid json"

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(malformed_json)

        error = exc_info.value
        assert error.code == -32700  # Parse error
        assert "Parse error" in error.message

    def test_parse_missing_jsonrpc_field(self) -> None:
        """Test handling request without jsonrpc field."""
        request_json = json.dumps(
            {
                "id": "req-1",
                "method": "system.get_basic_info",
                "params": {},
            }
        )

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(request_json)

        error = exc_info.value
        assert error.code == -32600  # Invalid Request
        assert "jsonrpc" in error.message.lower()

    def test_parse_wrong_jsonrpc_version(self) -> None:
        """Test handling request with wrong jsonrpc version."""
        request_json = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "req-1",
                "method": "system.get_basic_info",
                "params": {},
            }
        )

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(request_json)

        error = exc_info.value
        assert error.code == -32600  # Invalid Request
        assert "2.0" in error.message

    def test_parse_missing_method_field(self) -> None:
        """Test handling request without method field."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "req-1",
                "params": {},
            }
        )

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(request_json)

        error = exc_info.value
        assert error.code == -32600  # Invalid Request
        assert "method" in error.message.lower()

    def test_parse_empty_method(self) -> None:
        """Test handling request with empty method."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "req-1",
                "method": "",
                "params": {},
            }
        )

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(request_json)

        error = exc_info.value
        assert error.code == -32600  # Invalid Request

    def test_parse_invalid_params_type(self) -> None:
        """Test handling request with invalid params type (not object/array)."""
        request_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "req-1",
                "method": "system.get_basic_info",
                "params": "invalid_string",
            }
        )

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(request_json)

        error = exc_info.value
        assert error.code == -32602  # Invalid params

    def test_parse_non_object_request(self) -> None:
        """Test handling request that is not an object."""
        request_json = json.dumps([1, 2, 3])

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(request_json)

        error = exc_info.value
        assert error.code == -32600  # Invalid Request

    def test_parse_null_request(self) -> None:
        """Test handling null request."""
        request_json = json.dumps(None)

        with pytest.raises(JSONRPCError) as exc_info:
            parse_request(request_json)

        error = exc_info.value
        assert error.code == -32600  # Invalid Request


# =============================================================================
# Tests for Response Formatting
# =============================================================================


class TestFormatSuccessResponse:
    """Tests for success response formatting."""

    def test_format_success_with_dict_result(self) -> None:
        """Test formatting success response with dict result."""
        result = {"hostname": "raspberrypi", "uptime_seconds": 3600}

        response = format_success_response(request_id="req-1", result=result)

        assert response.jsonrpc == "2.0"
        assert response.id == "req-1"
        assert response.result == result
        assert response.error is None

    def test_format_success_with_numeric_id(self) -> None:
        """Test formatting success response with numeric ID."""
        response = format_success_response(request_id=42, result={"status": "ok"})

        assert response.id == 42

    def test_format_success_serialization(self) -> None:
        """Test success response serializes to valid JSON."""
        response = format_success_response(request_id="req-1", result={"key": "value"})

        json_str = response.to_json()
        parsed = json.loads(json_str)

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "req-1"
        assert parsed["result"] == {"key": "value"}
        assert "error" not in parsed

    def test_format_success_with_complex_result(self) -> None:
        """Test success response with complex nested result."""
        result = {
            "hostname": "raspberrypi",
            "metrics": {
                "cpu": {"usage": 25.5, "cores": 4},
                "memory": {"used": 1024, "total": 4096},
            },
            "interfaces": ["eth0", "wlan0"],
        }

        response = format_success_response(request_id="req-1", result=result)
        parsed = json.loads(response.to_json())

        assert parsed["result"] == result


class TestFormatErrorResponse:
    """Tests for error response formatting."""

    def test_format_error_response(self) -> None:
        """Test formatting error response."""
        error = JSONRPCError(
            code=-32600,
            message="Invalid Request",
            data={"error_code": "invalid_argument", "details": {}},
        )

        response = format_error_response(request_id="req-1", error=error)

        assert response.jsonrpc == "2.0"
        assert response.id == "req-1"
        assert response.result is None
        assert response.error.code == -32600
        assert response.error.message == "Invalid Request"

    def test_format_error_with_null_id(self) -> None:
        """Test formatting error response with null ID (for parse errors)."""
        error = JSONRPCError(code=-32700, message="Parse error")

        response = format_error_response(request_id=None, error=error)

        assert response.id is None

    def test_format_error_serialization(self) -> None:
        """Test error response serializes correctly."""
        error = JSONRPCError(
            code=-32001,
            message="Permission denied",
            data={
                "error_code": "permission_denied",
                "message": "Access not allowed",
                "details": {"user": "alice"},
            },
        )

        response = format_error_response(request_id="req-1", error=error)
        json_str = response.to_json()
        parsed = json.loads(json_str)

        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "req-1"
        assert parsed["error"]["code"] == -32001
        assert parsed["error"]["message"] == "Permission denied"
        assert parsed["error"]["data"]["error_code"] == "permission_denied"
        assert "result" not in parsed


# =============================================================================
# Tests for ToolError to JSON-RPC Error Mapping
# =============================================================================


class TestToolErrorToJSONRPCError:
    """Tests for ToolError to JSON-RPC error code mapping."""

    def test_invalid_argument_error_mapping(self) -> None:
        """Test InvalidArgumentError maps to correct code."""
        tool_error = InvalidArgumentError(
            message="Pin must be between 1 and 40",
            details={"pin": 50},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32602  # Invalid params
        assert jsonrpc_error.data["error_code"] == "invalid_argument"
        assert jsonrpc_error.data["details"]["pin"] == 50

    def test_permission_denied_error_mapping(self) -> None:
        """Test PermissionDeniedError maps to correct code."""
        tool_error = PermissionDeniedError(
            message="User lacks admin role",
            details={"required_role": "admin"},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32001  # Permission denied
        assert jsonrpc_error.data["error_code"] == "permission_denied"

    def test_unavailable_error_mapping(self) -> None:
        """Test UnavailableError maps to correct code."""
        tool_error = UnavailableError(
            message="Privileged agent offline",
            details={"socket": "/run/mcp-raspi/ops-agent.sock"},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32006  # Unavailable
        assert jsonrpc_error.data["error_code"] == "unavailable"

    def test_failed_precondition_error_mapping(self) -> None:
        """Test FailedPreconditionError maps to correct code."""
        tool_error = FailedPreconditionError(
            message="GPIO not configured",
            details={"pin": 17, "state": "unconfigured"},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32004  # Failed precondition
        assert jsonrpc_error.data["error_code"] == "failed_precondition"

    def test_internal_error_mapping(self) -> None:
        """Test InternalError maps to correct code."""
        tool_error = InternalError(
            message="Unexpected database error",
            details={"database": "metrics.db"},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32099  # Internal error
        assert jsonrpc_error.data["error_code"] == "internal"

    def test_generic_tool_error_mapping(self) -> None:
        """Test generic ToolError maps to internal error."""
        tool_error = ToolError(
            error_code="custom_error",
            message="Something went wrong",
            details={"info": "test"},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32000  # Server error
        assert jsonrpc_error.data["error_code"] == "custom_error"

    def test_not_found_error_mapping(self) -> None:
        """Test not_found error code maps correctly."""
        tool_error = ToolError(
            error_code="not_found",
            message="Tool not found",
            details={"tool": "unknown.tool"},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32003  # Not found
        assert jsonrpc_error.data["error_code"] == "not_found"

    def test_unauthenticated_error_mapping(self) -> None:
        """Test unauthenticated error code maps correctly."""
        tool_error = ToolError(
            error_code="unauthenticated",
            message="Authentication required",
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32002  # Unauthenticated
        assert jsonrpc_error.data["error_code"] == "unauthenticated"

    def test_resource_exhausted_error_mapping(self) -> None:
        """Test resource_exhausted error code maps correctly."""
        tool_error = ToolError(
            error_code="resource_exhausted",
            message="Rate limit exceeded",
            details={"limit": 100, "current": 150},
        )

        jsonrpc_error = tool_error_to_jsonrpc_error(tool_error)

        assert jsonrpc_error.code == -32005  # Resource exhausted
        assert jsonrpc_error.data["error_code"] == "resource_exhausted"


# =============================================================================
# Tests for JSONRPCError class
# =============================================================================


class TestJSONRPCError:
    """Tests for JSONRPCError class."""

    def test_jsonrpc_error_creation(self) -> None:
        """Test creating a JSONRPCError."""
        error = JSONRPCError(code=-32600, message="Invalid Request")

        assert error.code == -32600
        assert error.message == "Invalid Request"
        assert error.data is None

    def test_jsonrpc_error_with_data(self) -> None:
        """Test JSONRPCError with data field."""
        error = JSONRPCError(
            code=-32000,
            message="Server error",
            data={"error_code": "internal", "details": {}},
        )

        assert error.data == {"error_code": "internal", "details": {}}

    def test_jsonrpc_error_to_dict(self) -> None:
        """Test JSONRPCError to_dict method."""
        error = JSONRPCError(
            code=-32001,
            message="Permission denied",
            data={"error_code": "permission_denied"},
        )

        result = error.to_dict()

        assert result["code"] == -32001
        assert result["message"] == "Permission denied"
        assert result["data"]["error_code"] == "permission_denied"

    def test_jsonrpc_error_to_dict_without_data(self) -> None:
        """Test JSONRPCError to_dict without data."""
        error = JSONRPCError(code=-32700, message="Parse error")

        result = error.to_dict()

        assert result["code"] == -32700
        assert result["message"] == "Parse error"
        assert "data" not in result


# =============================================================================
# Tests for JSONRPCRequest class
# =============================================================================


class TestJSONRPCRequest:
    """Tests for JSONRPCRequest dataclass."""

    def test_request_creation(self) -> None:
        """Test creating a JSONRPCRequest."""
        request = JSONRPCRequest(
            jsonrpc="2.0",
            id="req-1",
            method="system.get_basic_info",
            params={},
        )

        assert request.jsonrpc == "2.0"
        assert request.id == "req-1"
        assert request.method == "system.get_basic_info"
        assert request.params == {}

    def test_request_is_notification(self) -> None:
        """Test is_notification property."""
        notification = JSONRPCRequest(
            jsonrpc="2.0",
            id=None,
            method="system.notify",
            params={},
        )

        regular_request = JSONRPCRequest(
            jsonrpc="2.0",
            id="req-1",
            method="system.get_basic_info",
            params={},
        )

        assert notification.is_notification is True
        assert regular_request.is_notification is False


# =============================================================================
# Tests for JSONRPCResponse class
# =============================================================================


class TestJSONRPCResponse:
    """Tests for JSONRPCResponse class."""

    def test_success_response_creation(self) -> None:
        """Test creating a success response."""
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id="req-1",
            result={"hostname": "raspberrypi"},
            error=None,
        )

        assert response.is_error is False
        assert response.result == {"hostname": "raspberrypi"}

    def test_error_response_creation(self) -> None:
        """Test creating an error response."""
        error = JSONRPCError(code=-32600, message="Invalid Request")
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id="req-1",
            result=None,
            error=error,
        )

        assert response.is_error is True
        assert response.error.code == -32600

    def test_response_to_json_success(self) -> None:
        """Test serializing success response to JSON."""
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id="req-1",
            result={"status": "ok"},
            error=None,
        )

        json_str = response.to_json()
        parsed = json.loads(json_str)

        assert "result" in parsed
        assert "error" not in parsed

    def test_response_to_json_error(self) -> None:
        """Test serializing error response to JSON."""
        error = JSONRPCError(code=-32600, message="Invalid Request")
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id="req-1",
            result=None,
            error=error,
        )

        json_str = response.to_json()
        parsed = json.loads(json_str)

        assert "error" in parsed
        assert "result" not in parsed
