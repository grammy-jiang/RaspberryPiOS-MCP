"""
Error types for the Raspberry Pi MCP Server.

This module defines the ToolError base class and subclasses for domain-specific errors.
Domain errors should be expressed using ToolError (or subclasses) instead of building
JSON-RPC error objects directly or returning ad-hoc status codes.

Error codes align with doc 05 §9 and map to JSON-RPC errors at the protocol layer.
"""

from __future__ import annotations

from typing import Any


class ToolError(Exception):
    """
    Base exception class for MCP tool errors.

    This class represents domain errors that occur during tool execution.
    ToolError instances are caught at the entry layer and mapped to JSON-RPC
    errors using the error mapping rules defined in the MCP specification.

    Attributes:
        error_code: Internal error code string (e.g., "invalid_argument",
            "permission_denied", "unavailable", "failed_precondition", "internal").
        message: Human-readable error message.
        details: Optional structured details (e.g., parameter values, context).

    Example:
        >>> raise ToolError(
        ...     error_code="invalid_argument",
        ...     message="Pin number must be between 1 and 40",
        ...     details={"pin": 50},
        ... )
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize a ToolError.

        Args:
            error_code: Internal error code string identifying the error category.
            message: Human-readable error message.
            details: Optional dictionary with structured error details.
        """
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"details={self.details!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the error to a dictionary for serialization.

        Returns:
            Dictionary with error_code, message, and details.
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class InvalidArgumentError(ToolError):
    """
    Error raised when a tool receives invalid input arguments.

    This error maps to the "invalid_argument" error code and should be used
    for parameter validation failures.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize an InvalidArgumentError."""
        super().__init__(
            error_code="invalid_argument", message=message, details=details
        )


class PermissionDeniedError(ToolError):
    """
    Error raised when a caller lacks permission for the requested operation.

    This error maps to the "permission_denied" error code and should be used
    when authorization checks fail.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize a PermissionDeniedError."""
        super().__init__(
            error_code="permission_denied", message=message, details=details
        )


class UnavailableError(ToolError):
    """
    Error raised when a required resource or service is unavailable.

    This error maps to the "unavailable" error code and should be used when
    the privileged agent is unavailable, hardware is not accessible, etc.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize an UnavailableError."""
        super().__init__(error_code="unavailable", message=message, details=details)


class FailedPreconditionError(ToolError):
    """
    Error raised when a precondition for the operation is not met.

    This error maps to the "failed_precondition" error code and should be used
    when hardware is not ready, system is in an invalid state, etc.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize a FailedPreconditionError."""
        super().__init__(
            error_code="failed_precondition", message=message, details=details
        )


class InternalError(ToolError):
    """
    Error raised for unexpected internal errors.

    This error maps to the "internal" error code and should be used for
    unexpected exceptions that should be logged with full stack traces.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize an InternalError."""
        super().__init__(error_code="internal", message=message, details=details)
