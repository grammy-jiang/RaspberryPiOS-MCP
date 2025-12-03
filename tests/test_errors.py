"""
Tests for the errors module.

This test module validates:
- ToolError base class functionality
- Error subclasses
- Error serialization (to_dict)
"""

from __future__ import annotations

from typing import Any

import pytest

from mcp_raspi.errors import (
    FailedPreconditionError,
    InternalError,
    InvalidArgumentError,
    PermissionDeniedError,
    ToolError,
    UnavailableError,
)

# =============================================================================
# Tests for ToolError Base Class
# =============================================================================


class TestToolError:
    """Tests for ToolError base class."""

    def test_init_with_all_args(self) -> None:
        """Test ToolError initialization with all arguments."""
        error = ToolError(
            error_code="test_error",
            message="Test error message",
            details={"key": "value"},
        )

        assert error.error_code == "test_error"
        assert error.message == "Test error message"
        assert error.details == {"key": "value"}

    def test_init_with_minimal_args(self) -> None:
        """Test ToolError initialization with minimal arguments."""
        error = ToolError(error_code="test_error", message="Test message")

        assert error.error_code == "test_error"
        assert error.message == "Test message"
        assert error.details == {}

    def test_str_representation(self) -> None:
        """Test ToolError string representation."""
        error = ToolError(error_code="test_error", message="Test error message")
        assert str(error) == "Test error message"

    def test_repr_representation(self) -> None:
        """Test ToolError repr representation."""
        error = ToolError(
            error_code="test_error",
            message="Test message",
            details={"pin": 17},
        )
        repr_str = repr(error)

        assert "ToolError" in repr_str
        assert "test_error" in repr_str
        assert "Test message" in repr_str
        assert "pin" in repr_str

    def test_to_dict(self) -> None:
        """Test ToolError to_dict serialization."""
        error = ToolError(
            error_code="test_error",
            message="Test message",
            details={"key": "value"},
        )

        result = error.to_dict()

        assert result == {
            "error_code": "test_error",
            "message": "Test message",
            "details": {"key": "value"},
        }

    def test_to_dict_empty_details(self) -> None:
        """Test ToolError to_dict with empty details."""
        error = ToolError(error_code="test_error", message="Test message")

        result = error.to_dict()

        assert result == {
            "error_code": "test_error",
            "message": "Test message",
            "details": {},
        }

    def test_is_exception(self) -> None:
        """Test that ToolError is a proper exception."""
        error = ToolError(error_code="test_error", message="Test message")

        assert isinstance(error, Exception)

        with pytest.raises(ToolError) as exc_info:
            raise error

        assert exc_info.value.error_code == "test_error"

    def test_details_with_various_types(self) -> None:
        """Test details can contain various types."""
        details: dict[str, Any] = {
            "string": "value",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "list": [1, 2, 3],
            "nested": {"a": "b"},
        }

        error = ToolError(
            error_code="test_error",
            message="Test message",
            details=details,
        )

        assert error.details == details


# =============================================================================
# Tests for Error Subclasses
# =============================================================================


class TestInvalidArgumentError:
    """Tests for InvalidArgumentError class."""

    def test_error_code(self) -> None:
        """Test InvalidArgumentError has correct error code."""
        error = InvalidArgumentError(message="Invalid pin")
        assert error.error_code == "invalid_argument"

    def test_with_details(self) -> None:
        """Test InvalidArgumentError with details."""
        error = InvalidArgumentError(
            message="Pin must be between 1 and 40",
            details={"pin": 50, "valid_range": [1, 40]},
        )

        assert error.message == "Pin must be between 1 and 40"
        assert error.details["pin"] == 50

    def test_is_tool_error(self) -> None:
        """Test InvalidArgumentError is a ToolError."""
        error = InvalidArgumentError(message="Invalid")
        assert isinstance(error, ToolError)


class TestPermissionDeniedError:
    """Tests for PermissionDeniedError class."""

    def test_error_code(self) -> None:
        """Test PermissionDeniedError has correct error code."""
        error = PermissionDeniedError(message="Access denied")
        assert error.error_code == "permission_denied"

    def test_with_details(self) -> None:
        """Test PermissionDeniedError with details."""
        error = PermissionDeniedError(
            message="User lacks permission",
            details={"user": "alice", "required_role": "admin"},
        )

        assert error.details["user"] == "alice"
        assert error.details["required_role"] == "admin"


class TestUnavailableError:
    """Tests for UnavailableError class."""

    def test_error_code(self) -> None:
        """Test UnavailableError has correct error code."""
        error = UnavailableError(message="Agent unavailable")
        assert error.error_code == "unavailable"

    def test_with_details(self) -> None:
        """Test UnavailableError with details."""
        error = UnavailableError(
            message="Privileged agent not responding",
            details={"socket": "/run/mcp-raspi/ops-agent.sock"},
        )

        assert error.details["socket"] == "/run/mcp-raspi/ops-agent.sock"


class TestFailedPreconditionError:
    """Tests for FailedPreconditionError class."""

    def test_error_code(self) -> None:
        """Test FailedPreconditionError has correct error code."""
        error = FailedPreconditionError(message="Hardware not ready")
        assert error.error_code == "failed_precondition"

    def test_with_details(self) -> None:
        """Test FailedPreconditionError with details."""
        error = FailedPreconditionError(
            message="GPIO pin is in use",
            details={"pin": 17, "current_mode": "output"},
        )

        assert error.details["pin"] == 17
        assert error.details["current_mode"] == "output"


class TestInternalError:
    """Tests for InternalError class."""

    def test_error_code(self) -> None:
        """Test InternalError has correct error code."""
        error = InternalError(message="Unexpected error")
        assert error.error_code == "internal"

    def test_with_details(self) -> None:
        """Test InternalError with details."""
        error = InternalError(
            message="Database connection failed",
            details={"database": "metrics.db", "error": "Connection refused"},
        )

        assert error.details["database"] == "metrics.db"


# =============================================================================
# Tests for Exception Handling Patterns
# =============================================================================


class TestExceptionHandlingPatterns:
    """Tests for common exception handling patterns."""

    def test_catch_specific_error(self) -> None:
        """Test catching specific error type."""
        try:
            raise InvalidArgumentError(message="Invalid input")
        except InvalidArgumentError as e:
            assert e.error_code == "invalid_argument"
            caught = True
        else:
            caught = False

        assert caught is True

    def test_catch_as_tool_error(self) -> None:
        """Test catching any ToolError subclass as ToolError."""
        errors = [
            InvalidArgumentError(message="Test"),
            PermissionDeniedError(message="Test"),
            UnavailableError(message="Test"),
            FailedPreconditionError(message="Test"),
            InternalError(message="Test"),
        ]

        for error in errors:
            try:
                raise error
            except ToolError as e:
                assert e.error_code in [
                    "invalid_argument",
                    "permission_denied",
                    "unavailable",
                    "failed_precondition",
                    "internal",
                ]

    def test_error_chain(self) -> None:
        """Test exception chaining."""

        def inner_function() -> None:
            raise ValueError("Original error")

        def outer_function() -> None:
            try:
                inner_function()
            except ValueError as e:
                raise InternalError(
                    message="Wrapped error",
                    details={"original": str(e)},
                ) from e

        with pytest.raises(InternalError) as exc_info:
            outer_function()

        assert exc_info.value.details["original"] == "Original error"
        assert exc_info.value.__cause__ is not None
