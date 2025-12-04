"""
JSON-RPC 2.0 protocol handling for the Raspberry Pi MCP Server.

This module implements JSON-RPC 2.0 request parsing and response formatting
following the MCP protocol specification and design documents 02 and 05.

Features:
- JSON-RPC 2.0 request parsing with validation
- JSON-RPC 2.0 response formatting (success and error)
- ToolError to JSON-RPC error code mapping
- Graceful handling of malformed requests

Error Code Mapping (from Doc 05 §9.1.2):
- -32700: Parse error (malformed JSON)
- -32600: Invalid Request (missing/invalid jsonrpc, method, etc.)
- -32601: Method not found (unknown tool)
- -32602: Invalid params (parameter validation failed)
- -32603: Internal error (framework failure)
- -32000 to -32099: Server errors (mapped from ToolError)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mcp_raspi.errors import ToolError

# =============================================================================
# JSON-RPC Error Codes
# =============================================================================

# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Project-specific error codes (from Doc 05 §9.1.2)
ERROR_CODE_MAP: dict[str, int] = {
    "invalid_argument": INVALID_PARAMS,  # -32602
    "permission_denied": -32001,
    "unauthenticated": -32002,
    "not_found": -32003,
    "failed_precondition": -32004,
    "resource_exhausted": -32005,
    "unavailable": -32006,
    "internal": -32099,
}

# Default server error code for unmapped error codes
DEFAULT_SERVER_ERROR = -32000


# =============================================================================
# Data Classes
# =============================================================================


class JSONRPCError(Exception):
    """
    Represents a JSON-RPC 2.0 error object.

    This class is both an Exception (so it can be raised) and a data container
    for JSON-RPC error information.

    Attributes:
        code: Integer error code (per JSON-RPC 2.0 spec).
        message: Human-readable error message.
        data: Optional structured error data with project-specific fields.
    """

    def __init__(
        self,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize a JSONRPCError.

        Args:
            code: Integer error code.
            message: Human-readable error message.
            data: Optional structured error data.
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the error to a dictionary for JSON serialization.

        Returns:
            Dictionary with code, message, and optionally data.
        """
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return (
            f"JSONRPCError(code={self.code}, "
            f"message={self.message!r}, "
            f"data={self.data!r})"
        )


@dataclass
class JSONRPCRequest:
    """
    Represents a parsed JSON-RPC 2.0 request.

    Attributes:
        jsonrpc: Protocol version (must be "2.0").
        id: Request identifier (string or number, None for notifications).
        method: The method/tool to invoke.
        params: Parameters for the method (dict or empty dict).
    """

    jsonrpc: str
    id: str | int | None
    method: str
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def is_notification(self) -> bool:
        """Check if this is a notification (no id field)."""
        return self.id is None


@dataclass
class JSONRPCResponse:
    """
    Represents a JSON-RPC 2.0 response.

    Either result or error must be present, but not both.

    Attributes:
        jsonrpc: Protocol version (always "2.0").
        id: Request identifier (matches request, or null for parse errors).
        result: Success result (if not an error).
        error: Error object (if an error occurred).
    """

    jsonrpc: str
    id: str | int | None
    result: Any | None = None
    error: JSONRPCError | None = None

    @property
    def is_error(self) -> bool:
        """Check if this is an error response."""
        return self.error is not None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the response to a dictionary for JSON serialization.

        Returns:
            Dictionary with jsonrpc, id, and either result or error.
        """
        response: dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
        }
        if self.error is not None:
            response["error"] = self.error.to_dict()
        else:
            response["result"] = self.result
        return response

    def to_json(self) -> str:
        """
        Serialize the response to a JSON string.

        Returns:
            JSON string representation of the response.
        """
        return json.dumps(self.to_dict(), separators=(",", ":"))


# =============================================================================
# Request Parsing
# =============================================================================


def parse_request(request_json: str) -> JSONRPCRequest:
    """
    Parse a JSON-RPC 2.0 request from a JSON string.

    Args:
        request_json: Raw JSON string containing the request.

    Returns:
        Parsed JSONRPCRequest object.

    Raises:
        JSONRPCError: If the request is malformed or invalid.

    Example:
        >>> request = parse_request('{"jsonrpc":"2.0","id":"1","method":"system.get_basic_info","params":{}}')
        >>> print(request.method)
        system.get_basic_info
    """
    # Parse JSON
    try:
        data = json.loads(request_json)
    except json.JSONDecodeError as e:
        raise JSONRPCError(
            code=PARSE_ERROR,
            message=f"Parse error: Invalid JSON - {e.msg}",
        ) from e

    # Validate that we have an object
    if not isinstance(data, dict):
        raise JSONRPCError(
            code=INVALID_REQUEST,
            message="Invalid Request: Request must be a JSON object",
        )

    # Validate jsonrpc field
    jsonrpc = data.get("jsonrpc")
    if jsonrpc is None:
        raise JSONRPCError(
            code=INVALID_REQUEST,
            message="Invalid Request: Missing 'jsonrpc' field",
        )
    if jsonrpc != "2.0":
        raise JSONRPCError(
            code=INVALID_REQUEST,
            message=f"Invalid Request: jsonrpc must be '2.0', got '{jsonrpc}'",
        )

    # Validate method field
    method = data.get("method")
    if method is None:
        raise JSONRPCError(
            code=INVALID_REQUEST,
            message="Invalid Request: Missing 'method' field",
        )
    if not isinstance(method, str) or not method:
        raise JSONRPCError(
            code=INVALID_REQUEST,
            message="Invalid Request: 'method' must be a non-empty string",
        )

    # Get optional id field (None for notifications)
    request_id = data.get("id")

    # Validate params field (optional, defaults to empty dict)
    params = data.get("params", {})
    if not isinstance(params, (dict, list)):
        raise JSONRPCError(
            code=INVALID_PARAMS,
            message="Invalid params: 'params' must be an object or array",
        )
    # JSON-RPC 2.0 allows both object and positional (array) params.
    # For MCP tools, we normalize array params to a dict with '_args' key.
    # This allows handlers to access positional params as params.get("_args").
    if isinstance(params, list):
        params = {"_args": params}

    return JSONRPCRequest(
        jsonrpc="2.0",
        id=request_id,
        method=method,
        params=params,
    )


# =============================================================================
# Response Formatting
# =============================================================================


def format_success_response(
    request_id: str | int | None,
    result: Any,
) -> JSONRPCResponse:
    """
    Format a successful JSON-RPC 2.0 response.

    Args:
        request_id: The request ID to include in the response.
        result: The result value to include in the response.

    Returns:
        JSONRPCResponse object representing a success response.

    Example:
        >>> response = format_success_response("req-1", {"hostname": "pi"})
        >>> print(response.to_json())
        {"jsonrpc":"2.0","id":"req-1","result":{"hostname":"pi"}}
    """
    return JSONRPCResponse(
        jsonrpc="2.0",
        id=request_id,
        result=result,
        error=None,
    )


def format_error_response(
    request_id: str | int | None,
    error: JSONRPCError,
) -> JSONRPCResponse:
    """
    Format a JSON-RPC 2.0 error response.

    Args:
        request_id: The request ID (may be None for parse errors).
        error: The JSONRPCError object describing the error.

    Returns:
        JSONRPCResponse object representing an error response.

    Example:
        >>> error = JSONRPCError(code=-32600, message="Invalid Request")
        >>> response = format_error_response("req-1", error)
        >>> print(response.to_json())
        {"jsonrpc":"2.0","id":"req-1","error":{"code":-32600,"message":"Invalid Request"}}
    """
    return JSONRPCResponse(
        jsonrpc="2.0",
        id=request_id,
        result=None,
        error=error,
    )


# =============================================================================
# ToolError to JSON-RPC Error Mapping
# =============================================================================


def tool_error_to_jsonrpc_error(tool_error: ToolError) -> JSONRPCError:
    """
    Convert a ToolError to a JSONRPCError.

    Maps the ToolError's error_code to the appropriate JSON-RPC error code
    as defined in Doc 05 §9.1.2.

    Args:
        tool_error: The ToolError to convert.

    Returns:
        JSONRPCError with appropriate code and structured data.

    Example:
        >>> from mcp_raspi.errors import InvalidArgumentError
        >>> err = InvalidArgumentError(message="Invalid pin", details={"pin": 99})
        >>> jsonrpc_err = tool_error_to_jsonrpc_error(err)
        >>> print(jsonrpc_err.code)
        -32602
    """
    # Map error_code to JSON-RPC code
    jsonrpc_code = ERROR_CODE_MAP.get(tool_error.error_code, DEFAULT_SERVER_ERROR)

    # Build the data object with project-specific fields
    data: dict[str, Any] = {
        "error_code": tool_error.error_code,
        "message": tool_error.message,
        "details": tool_error.details,
    }

    return JSONRPCError(
        code=jsonrpc_code,
        message=tool_error.message,
        data=data,
    )


def create_method_not_found_error(method: str) -> JSONRPCError:
    """
    Create a "Method not found" error for an unknown tool.

    Args:
        method: The method name that was not found.

    Returns:
        JSONRPCError with code -32601.
    """
    return JSONRPCError(
        code=METHOD_NOT_FOUND,
        message=f"Method not found: {method}",
        data={
            "error_code": "not_found",
            "message": f"Tool '{method}' is not registered",
            "details": {"method": method},
        },
    )


def create_internal_error(
    message: str, details: dict[str, Any] | None = None
) -> JSONRPCError:
    """
    Create an internal error for unexpected exceptions.

    Args:
        message: Error message describing what went wrong.
        details: Optional additional details.

    Returns:
        JSONRPCError with code -32603.
    """
    return JSONRPCError(
        code=INTERNAL_ERROR,
        message=message,
        data={
            "error_code": "internal",
            "message": message,
            "details": details or {},
        },
    )
