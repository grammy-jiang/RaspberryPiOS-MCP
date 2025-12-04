"""
IPC Protocol definitions for MCP Server <-> Privileged Agent communication.

This module defines the IPC protocol, message formats, and error classes
for Unix domain socket communication between the MCP server and the
privileged operations agent.

Design follows Doc 02 §6 (Privileged IPC Protocol) and §12 (IPC Robustness).

Protocol Format:
- Transport: Unix domain socket
- Message format: Length-prefixed JSON (4-byte big-endian length + JSON payload)
- Request: {"id": "uuid", "operation": "cmd", "timestamp": "iso8601", "params": {...}}
- Response: {"id": "uuid", "status": "ok"|"error", "data": {...}, "error": {...}}
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# =============================================================================
# IPC Exceptions
# =============================================================================


class IPCError(Exception):
    """Base exception for IPC errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize an IPC error."""
        super().__init__(message)
        self.message = message
        self.details = details or {}


class IPCTimeoutError(IPCError):
    """Raised when an IPC request times out."""

    pass


class IPCUnavailableError(IPCError):
    """Raised when the privileged agent is unavailable."""

    pass


class IPCProtocolError(IPCError):
    """Raised when there's a protocol violation."""

    pass


class IPCConnectionError(IPCError):
    """Raised when there's a connection error."""

    pass


# =============================================================================
# Request ID Generation
# =============================================================================


class RequestIDGenerator:
    """
    Generates unique request IDs.

    Format: {timestamp_ms}-{counter}-{random}
    Example: 1701629400123-42-a3f5e8c2

    This ensures uniqueness across process restarts and handles high-frequency
    requests without collision.
    """

    def __init__(self) -> None:
        """Initialize the request ID generator."""
        self._counter = 0
        self._active_ids: set[str] = set()
        self._max_active_ids = 10000

    def generate(self) -> str:
        """
        Generate a unique request ID.

        Returns:
            A unique request ID string.
        """
        timestamp_ms = int(time.time() * 1000)
        self._counter = (self._counter + 1) % 1000000

        # Add randomness for extra uniqueness
        random_suffix = uuid.uuid4().hex[:8]

        request_id = f"{timestamp_ms}-{self._counter}-{random_suffix}"

        # Handle extremely rare collision case
        if request_id in self._active_ids:
            request_id = f"{timestamp_ms}-{self._counter}-{uuid.uuid4().hex[:8]}"

        # Track active IDs
        self._active_ids.add(request_id)

        # Cleanup IDs to prevent memory leak
        if len(self._active_ids) > self._max_active_ids:
            # Remove arbitrary 10% - order doesn't matter for collision prevention
            # since IDs include timestamps and randomness for uniqueness
            to_remove = list(self._active_ids)[: self._max_active_ids // 10]
            self._active_ids -= set(to_remove)

        return request_id

    def mark_completed(self, request_id: str) -> None:
        """
        Mark a request ID as completed.

        Args:
            request_id: The request ID to remove from active tracking.
        """
        self._active_ids.discard(request_id)


# =============================================================================
# IPC Message Models
# =============================================================================


@dataclass
class CallerInfo:
    """
    Caller identity information for audit purposes.

    Attributes:
        user: User identifier.
        role: User role.
    """

    user: str = "anonymous"
    role: str = "viewer"

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary."""
        return {"user": self.user, "role": self.role}


@dataclass
class IPCRequest:
    """
    IPC request message from MCP Server to Privileged Agent.

    Attributes:
        id: Unique request identifier.
        operation: Operation to execute (e.g., "gpio.write", "ping").
        params: Operation-specific parameters.
        timestamp: ISO 8601 timestamp when request was created.
        caller: Optional caller identity information.
    """

    id: str
    operation: str
    params: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    caller: CallerInfo | None = None

    @classmethod
    def create(
        cls,
        operation: str,
        params: dict[str, Any] | None = None,
        request_id: str | None = None,
        caller: CallerInfo | None = None,
    ) -> IPCRequest:
        """
        Create a new IPC request.

        Args:
            operation: Operation to execute.
            params: Operation parameters.
            request_id: Optional request ID (generated if not provided).
            caller: Optional caller info.

        Returns:
            A new IPCRequest instance.
        """
        if request_id is None:
            request_id = uuid.uuid4().hex

        return cls(
            id=request_id,
            operation=operation,
            params=params or {},
            timestamp=datetime.now(UTC).isoformat(),
            caller=caller,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data: dict[str, Any] = {
            "id": self.id,
            "operation": self.operation,
            "params": self.params,
            "timestamp": self.timestamp,
        }
        if self.caller:
            data["caller"] = self.caller.to_dict()
        return data

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IPCRequest:
        """Create from dictionary."""
        caller = None
        if "caller" in data:
            caller = CallerInfo(
                user=data["caller"].get("user", "anonymous"),
                role=data["caller"].get("role", "viewer"),
            )
        return cls(
            id=data["id"],
            operation=data["operation"],
            params=data.get("params", {}),
            timestamp=data.get("timestamp", datetime.now(UTC).isoformat()),
            caller=caller,
        )

    @classmethod
    def from_json(cls, json_str: str) -> IPCRequest:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class IPCErrorDetail:
    """
    Error details in IPC response.

    Attributes:
        code: Error code string (e.g., "failed_precondition").
        message: Human-readable error message.
        details: Optional structured error details.
    """

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IPCErrorDetail:
        """Create from dictionary."""
        return cls(
            code=data.get("code", "internal"),
            message=data.get("message", "Unknown error"),
            details=data.get("details", {}),
        )


@dataclass
class IPCResponse:
    """
    IPC response message from Privileged Agent to MCP Server.

    Attributes:
        id: Request ID (must match the request).
        status: Status ("ok" or "error").
        data: Response data on success.
        error: Error details on failure.
    """

    id: str
    status: str
    data: dict[str, Any] | None = None
    error: IPCErrorDetail | None = None

    @classmethod
    def success(
        cls, request_id: str, data: dict[str, Any] | None = None
    ) -> IPCResponse:
        """
        Create a success response.

        Args:
            request_id: The request ID to respond to.
            data: Response data.

        Returns:
            A success IPCResponse.
        """
        return cls(id=request_id, status="ok", data=data or {}, error=None)

    @classmethod
    def create_error(
        cls,
        request_id: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> IPCResponse:
        """
        Create an error response.

        Args:
            request_id: The request ID to respond to.
            code: Error code.
            message: Error message.
            details: Optional error details.

        Returns:
            An error IPCResponse.
        """
        return cls(
            id=request_id,
            status="error",
            data=None,
            error=IPCErrorDetail(code=code, message=message, details=details or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data: dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "data": self.data,
            "error": self.error.to_dict() if self.error else None,
        }
        return data

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IPCResponse:
        """Create from dictionary."""
        error = None
        if data.get("error"):
            error = IPCErrorDetail.from_dict(data["error"])

        return cls(
            id=data["id"],
            status=data["status"],
            data=data.get("data"),
            error=error,
        )

    @classmethod
    def from_json(cls, json_str: str) -> IPCResponse:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @property
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return self.status == "ok"

    @property
    def is_error(self) -> bool:
        """Check if response indicates an error."""
        return self.status == "error"


# =============================================================================
# Protocol Constants
# =============================================================================

# Maximum message size: 1 MB
MAX_MESSAGE_SIZE = 1024 * 1024

# Maximum total response size for chunked responses: 10 MB
MAX_TOTAL_SIZE = 10 * 1024 * 1024

# Default timeout for IPC requests: 30 seconds
DEFAULT_TIMEOUT = 30.0

# Default socket path
DEFAULT_SOCKET_PATH = "/run/mcp-raspi/ops-agent.sock"
