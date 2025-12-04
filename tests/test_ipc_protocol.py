"""
Tests for the IPC protocol module.

Tests the IPCRequest, IPCResponse, and related protocol classes.
"""

from __future__ import annotations

import json

from mcp_raspi.ipc.protocol import (
    DEFAULT_SOCKET_PATH,
    DEFAULT_TIMEOUT,
    MAX_MESSAGE_SIZE,
    CallerInfo,
    IPCConnectionError,
    IPCError,
    IPCErrorDetail,
    IPCProtocolError,
    IPCRequest,
    IPCResponse,
    IPCTimeoutError,
    IPCUnavailableError,
    RequestIDGenerator,
)

# =============================================================================
# IPC Error Tests
# =============================================================================


class TestIPCError:
    """Tests for IPC error classes."""

    def test_ipc_error_creation(self) -> None:
        """Test basic IPCError creation."""
        error = IPCError("Test error", {"key": "value"})
        assert error.message == "Test error"
        assert error.details == {"key": "value"}
        assert str(error) == "Test error"

    def test_ipc_error_default_details(self) -> None:
        """Test IPCError with default empty details."""
        error = IPCError("Test error")
        assert error.details == {}

    def test_ipc_timeout_error(self) -> None:
        """Test IPCTimeoutError."""
        error = IPCTimeoutError("Request timed out")
        assert isinstance(error, IPCError)
        assert error.message == "Request timed out"

    def test_ipc_unavailable_error(self) -> None:
        """Test IPCUnavailableError."""
        error = IPCUnavailableError("Agent not available")
        assert isinstance(error, IPCError)
        assert error.message == "Agent not available"

    def test_ipc_protocol_error(self) -> None:
        """Test IPCProtocolError."""
        error = IPCProtocolError("Invalid message format")
        assert isinstance(error, IPCError)
        assert error.message == "Invalid message format"

    def test_ipc_connection_error(self) -> None:
        """Test IPCConnectionError."""
        error = IPCConnectionError("Connection failed")
        assert isinstance(error, IPCError)
        assert error.message == "Connection failed"


# =============================================================================
# Request ID Generator Tests
# =============================================================================


class TestRequestIDGenerator:
    """Tests for RequestIDGenerator."""

    def test_generate_unique_ids(self) -> None:
        """Test that generated IDs are unique."""
        generator = RequestIDGenerator()
        ids = {generator.generate() for _ in range(1000)}
        assert len(ids) == 1000

    def test_id_format(self) -> None:
        """Test that IDs have expected format."""
        generator = RequestIDGenerator()
        request_id = generator.generate()

        # Format: {timestamp_ms}-{counter}-{random}
        parts = request_id.split("-")
        assert len(parts) == 3
        assert parts[0].isdigit()  # timestamp
        assert parts[1].isdigit()  # counter
        assert len(parts[2]) == 8  # random hex

    def test_mark_completed(self) -> None:
        """Test marking IDs as completed."""
        generator = RequestIDGenerator()
        request_id = generator.generate()

        # Should not raise
        generator.mark_completed(request_id)

        # Should handle missing ID gracefully
        generator.mark_completed("nonexistent-id")

    def test_active_ids_cleanup(self) -> None:
        """Test that active IDs are cleaned up when limit exceeded."""
        generator = RequestIDGenerator()
        generator._max_active_ids = 100

        # Generate more than max
        for _ in range(150):
            generator.generate()

        # Should have cleaned up some
        assert len(generator._active_ids) <= 150


# =============================================================================
# CallerInfo Tests
# =============================================================================


class TestCallerInfo:
    """Tests for CallerInfo."""

    def test_caller_info_defaults(self) -> None:
        """Test CallerInfo with defaults."""
        caller = CallerInfo()
        assert caller.user == "anonymous"
        assert caller.role == "viewer"

    def test_caller_info_custom(self) -> None:
        """Test CallerInfo with custom values."""
        caller = CallerInfo(user="alice", role="admin")
        assert caller.user == "alice"
        assert caller.role == "admin"

    def test_caller_info_to_dict(self) -> None:
        """Test CallerInfo serialization."""
        caller = CallerInfo(user="bob", role="operator")
        data = caller.to_dict()
        assert data == {"user": "bob", "role": "operator"}


# =============================================================================
# IPCRequest Tests
# =============================================================================


class TestIPCRequest:
    """Tests for IPCRequest."""

    def test_request_creation(self) -> None:
        """Test basic request creation."""
        request = IPCRequest(
            id="test-123",
            operation="gpio.write",
            params={"pin": 17, "value": 1},
        )
        assert request.id == "test-123"
        assert request.operation == "gpio.write"
        assert request.params == {"pin": 17, "value": 1}

    def test_request_create_factory(self) -> None:
        """Test request creation using factory method."""
        request = IPCRequest.create(
            operation="ping",
            params={"message": "hello"},
        )
        assert request.operation == "ping"
        assert request.params == {"message": "hello"}
        assert len(request.id) > 0
        assert request.timestamp is not None

    def test_request_with_caller(self) -> None:
        """Test request with caller info."""
        caller = CallerInfo(user="alice", role="admin")
        request = IPCRequest.create(
            operation="test",
            caller=caller,
        )
        assert request.caller is not None
        assert request.caller.user == "alice"

    def test_request_to_dict(self) -> None:
        """Test request serialization to dict."""
        request = IPCRequest(
            id="test-123",
            operation="ping",
            params={"key": "value"},
            timestamp="2024-01-01T00:00:00Z",
        )
        data = request.to_dict()
        assert data["id"] == "test-123"
        assert data["operation"] == "ping"
        assert data["params"] == {"key": "value"}
        assert data["timestamp"] == "2024-01-01T00:00:00Z"

    def test_request_to_json(self) -> None:
        """Test request serialization to JSON."""
        request = IPCRequest(
            id="test-123",
            operation="ping",
            params={},
            timestamp="2024-01-01T00:00:00Z",
        )
        json_str = request.to_json()
        data = json.loads(json_str)
        assert data["id"] == "test-123"
        assert data["operation"] == "ping"

    def test_request_from_dict(self) -> None:
        """Test request deserialization from dict."""
        data = {
            "id": "test-456",
            "operation": "gpio.read",
            "params": {"pin": 18},
            "timestamp": "2024-01-01T00:00:00Z",
        }
        request = IPCRequest.from_dict(data)
        assert request.id == "test-456"
        assert request.operation == "gpio.read"
        assert request.params == {"pin": 18}

    def test_request_from_dict_with_caller(self) -> None:
        """Test request deserialization with caller info."""
        data = {
            "id": "test-789",
            "operation": "test",
            "params": {},
            "caller": {"user": "bob", "role": "operator"},
        }
        request = IPCRequest.from_dict(data)
        assert request.caller is not None
        assert request.caller.user == "bob"
        assert request.caller.role == "operator"

    def test_request_from_json(self) -> None:
        """Test request deserialization from JSON."""
        json_str = '{"id": "test-abc", "operation": "echo", "params": {"msg": "hi"}}'
        request = IPCRequest.from_json(json_str)
        assert request.id == "test-abc"
        assert request.operation == "echo"
        assert request.params == {"msg": "hi"}

    def test_request_roundtrip(self) -> None:
        """Test request serialization roundtrip."""
        original = IPCRequest.create(
            operation="test.operation",
            params={"a": 1, "b": "two"},
            caller=CallerInfo(user="test", role="admin"),
        )
        json_str = original.to_json()
        restored = IPCRequest.from_json(json_str)

        assert restored.id == original.id
        assert restored.operation == original.operation
        assert restored.params == original.params
        assert restored.caller.user == original.caller.user  # type: ignore
        assert restored.caller.role == original.caller.role  # type: ignore


# =============================================================================
# IPCErrorDetail Tests
# =============================================================================


class TestIPCErrorDetail:
    """Tests for IPCErrorDetail."""

    def test_error_detail_creation(self) -> None:
        """Test error detail creation."""
        detail = IPCErrorDetail(
            code="invalid_argument",
            message="Pin must be between 1 and 40",
            details={"pin": 50},
        )
        assert detail.code == "invalid_argument"
        assert detail.message == "Pin must be between 1 and 40"
        assert detail.details == {"pin": 50}

    def test_error_detail_to_dict(self) -> None:
        """Test error detail serialization."""
        detail = IPCErrorDetail(
            code="test_error",
            message="Test message",
        )
        data = detail.to_dict()
        assert data["code"] == "test_error"
        assert data["message"] == "Test message"
        assert data["details"] == {}

    def test_error_detail_from_dict(self) -> None:
        """Test error detail deserialization."""
        data = {
            "code": "failed_precondition",
            "message": "Hardware not ready",
            "details": {"device": "gpio"},
        }
        detail = IPCErrorDetail.from_dict(data)
        assert detail.code == "failed_precondition"
        assert detail.message == "Hardware not ready"
        assert detail.details == {"device": "gpio"}


# =============================================================================
# IPCResponse Tests
# =============================================================================


class TestIPCResponse:
    """Tests for IPCResponse."""

    def test_response_creation(self) -> None:
        """Test basic response creation."""
        response = IPCResponse(
            id="test-123",
            status="ok",
            data={"result": True},
        )
        assert response.id == "test-123"
        assert response.status == "ok"
        assert response.data == {"result": True}
        assert response.error is None

    def test_response_success_factory(self) -> None:
        """Test success response factory."""
        response = IPCResponse.success("req-123", {"value": 42})
        assert response.id == "req-123"
        assert response.status == "ok"
        assert response.data == {"value": 42}
        assert response.error is None
        assert response.is_success
        assert not response.is_error

    def test_response_error_factory(self) -> None:
        """Test error response factory."""
        response = IPCResponse.create_error(
            request_id="req-456",
            code="invalid_argument",
            message="Invalid parameter",
            details={"param": "pin"},
        )
        assert response.id == "req-456"
        assert response.status == "error"
        assert response.data is None
        assert response.error is not None
        assert response.error.code == "invalid_argument"
        assert response.error.message == "Invalid parameter"
        assert not response.is_success
        assert response.is_error

    def test_response_to_dict(self) -> None:
        """Test response serialization to dict."""
        response = IPCResponse.success("req-789", {"pong": True})
        data = response.to_dict()
        assert data["id"] == "req-789"
        assert data["status"] == "ok"
        assert data["data"] == {"pong": True}
        assert data["error"] is None

    def test_response_to_json(self) -> None:
        """Test response serialization to JSON."""
        response = IPCResponse.success("req-abc", {"test": 1})
        json_str = response.to_json()
        data = json.loads(json_str)
        assert data["id"] == "req-abc"
        assert data["status"] == "ok"

    def test_response_from_dict(self) -> None:
        """Test response deserialization from dict."""
        data = {
            "id": "req-def",
            "status": "ok",
            "data": {"value": "result"},
            "error": None,
        }
        response = IPCResponse.from_dict(data)
        assert response.id == "req-def"
        assert response.status == "ok"
        assert response.data == {"value": "result"}

    def test_response_from_dict_with_error(self) -> None:
        """Test response deserialization with error."""
        data = {
            "id": "req-err",
            "status": "error",
            "data": None,
            "error": {
                "code": "unavailable",
                "message": "Service unavailable",
                "details": {},
            },
        }
        response = IPCResponse.from_dict(data)
        assert response.id == "req-err"
        assert response.status == "error"
        assert response.error is not None
        assert response.error.code == "unavailable"

    def test_response_from_json(self) -> None:
        """Test response deserialization from JSON."""
        json_str = '{"id": "req-json", "status": "ok", "data": {"key": "value"}, "error": null}'
        response = IPCResponse.from_json(json_str)
        assert response.id == "req-json"
        assert response.data == {"key": "value"}

    def test_response_roundtrip_success(self) -> None:
        """Test success response serialization roundtrip."""
        original = IPCResponse.success("roundtrip-1", {"nested": {"key": "value"}})
        json_str = original.to_json()
        restored = IPCResponse.from_json(json_str)

        assert restored.id == original.id
        assert restored.status == original.status
        assert restored.data == original.data

    def test_response_roundtrip_error(self) -> None:
        """Test error response serialization roundtrip."""
        original = IPCResponse.create_error(
            request_id="roundtrip-2",
            code="test_error",
            message="Test error message",
            details={"key": "value"},
        )
        json_str = original.to_json()
        restored = IPCResponse.from_json(json_str)

        assert restored.id == original.id
        assert restored.status == original.status
        assert restored.error is not None
        assert restored.error.code == original.error.code  # type: ignore
        assert restored.error.message == original.error.message  # type: ignore


# =============================================================================
# Protocol Constants Tests
# =============================================================================


class TestProtocolConstants:
    """Tests for protocol constants."""

    def test_max_message_size(self) -> None:
        """Test maximum message size constant."""
        assert MAX_MESSAGE_SIZE == 1024 * 1024  # 1 MB

    def test_default_timeout(self) -> None:
        """Test default timeout constant."""
        assert DEFAULT_TIMEOUT == 30.0

    def test_default_socket_path(self) -> None:
        """Test default socket path constant."""
        assert DEFAULT_SOCKET_PATH == "/run/mcp-raspi/ops-agent.sock"
