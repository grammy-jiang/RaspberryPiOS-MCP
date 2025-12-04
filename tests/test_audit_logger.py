"""
Tests for the audit logger module.

Tests cover:
- Audit log entry creation
- Tool call logging
- Auth event logging
- Security event logging
- Sensitive field masking
- File logging
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from mcp_raspi.config import LoggingConfig
from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.security.audit_logger import (
    AuditLogger,
    get_audit_logger,
    log_tool_call,
    set_audit_logger,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def audit_logger() -> AuditLogger:
    """Create an AuditLogger for testing without file output."""
    return AuditLogger(log_to_file=False, log_to_stdout=False)


@pytest.fixture
def file_audit_logger(tmp_path: Path) -> AuditLogger:
    """Create an AuditLogger with file output."""
    audit_path = tmp_path / "audit.log"
    return AuditLogger(
        audit_log_path=str(audit_path),
        log_to_file=True,
        log_to_stdout=False,
    )


@pytest.fixture
def sample_context() -> ToolContext:
    """Create a sample ToolContext for testing."""
    return ToolContext(
        tool_name="system.reboot",
        caller=CallerInfo(
            user_id="admin@example.com",
            role="admin",
            ip_address="192.168.1.100",
        ),
        request_id="req-12345",
    )


# =============================================================================
# Tests for AuditLogger Initialization
# =============================================================================


class TestAuditLoggerInit:
    """Tests for AuditLogger initialization."""

    def test_init_without_file(self) -> None:
        """Test initialization without file logging."""
        logger = AuditLogger(log_to_file=False, log_to_stdout=True)
        assert logger._audit_log_path is None
        assert logger._file_logger is None

    def test_init_with_file(self, tmp_path: Path) -> None:
        """Test initialization with file logging."""
        audit_path = tmp_path / "audit.log"
        logger = AuditLogger(
            audit_log_path=str(audit_path),
            log_to_file=True,
        )
        assert logger._audit_log_path == str(audit_path)
        assert logger._file_logger is not None

    def test_from_config(self, tmp_path: Path) -> None:
        """Test AuditLogger creation from config."""
        audit_path = tmp_path / "audit.log"
        config = LoggingConfig(
            audit_log_path=str(audit_path),
            log_to_stdout=False,
        )

        logger = AuditLogger.from_config(config)

        assert logger._audit_log_path == str(audit_path)

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that init creates log directory if needed."""
        audit_path = tmp_path / "subdir" / "audit.log"
        AuditLogger(
            audit_log_path=str(audit_path),
            log_to_file=True,
        )
        assert audit_path.parent.exists()


# =============================================================================
# Tests for Tool Call Logging
# =============================================================================


class TestToolCallLogging:
    """Tests for log_tool_call method."""

    def test_log_tool_call_success(
        self, audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test logging a successful tool call."""
        with mock.patch.object(audit_logger, "_write_entry") as mock_write:
            audit_logger.log_tool_call(
                ctx=sample_context,
                status="success",
                params={"reason": "maintenance"},
                duration_ms=45.5,
            )

            mock_write.assert_called_once()
            entry = mock_write.call_args[0][0]

            assert entry["event_type"] == "tool_call"
            assert entry["user_id"] == "admin@example.com"
            assert entry["role"] == "admin"
            assert entry["action"] == "system.reboot"
            assert entry["result"] == "success"
            assert entry["request_id"] == "req-12345"
            assert entry["source_ip"] == "192.168.1.100"
            assert entry["params"]["reason"] == "maintenance"
            assert entry["duration_ms"] == 45.5

    def test_log_tool_call_error(
        self, audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test logging a failed tool call."""
        with mock.patch.object(audit_logger, "_write_entry") as mock_write:
            audit_logger.log_tool_call(
                ctx=sample_context,
                status="error",
                error_code="permission_denied",
            )

            entry = mock_write.call_args[0][0]

            assert entry["result"] == "error"
            assert entry["error_code"] == "permission_denied"

    def test_log_tool_call_with_extra(
        self, audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test logging with extra fields."""
        with mock.patch.object(audit_logger, "_write_entry") as mock_write:
            audit_logger.log_tool_call(
                ctx=sample_context,
                status="success",
                extra={"danger_level": "high", "confirmed": True},
            )

            entry = mock_write.call_args[0][0]

            assert entry["danger_level"] == "high"
            assert entry["confirmed"] is True


# =============================================================================
# Tests for Auth Event Logging
# =============================================================================


class TestAuthEventLogging:
    """Tests for log_auth_event method."""

    def test_log_auth_success(self, audit_logger: AuditLogger) -> None:
        """Test logging successful authentication."""
        with mock.patch.object(audit_logger, "_write_entry") as mock_write:
            audit_logger.log_auth_event(
                event_type="auth_success",
                success=True,
                user_id="user@example.com",
                source_ip="10.0.0.1",
            )

            entry = mock_write.call_args[0][0]

            assert entry["event_type"] == "auth_success"
            assert entry["success"] is True
            assert entry["user_id"] == "user@example.com"
            assert entry["source_ip"] == "10.0.0.1"

    def test_log_auth_failure(self, audit_logger: AuditLogger) -> None:
        """Test logging failed authentication."""
        with mock.patch.object(audit_logger, "_write_entry") as mock_write:
            audit_logger.log_auth_event(
                event_type="auth_failure",
                success=False,
                source_ip="10.0.0.1",
                details={"reason": "invalid_token"},
            )

            entry = mock_write.call_args[0][0]

            assert entry["event_type"] == "auth_failure"
            assert entry["success"] is False
            assert entry["details"]["reason"] == "invalid_token"


# =============================================================================
# Tests for Security Event Logging
# =============================================================================


class TestSecurityEventLogging:
    """Tests for log_security_event method."""

    def test_log_security_event_basic(self, audit_logger: AuditLogger) -> None:
        """Test logging a basic security event."""
        with mock.patch.object(audit_logger, "_write_entry") as mock_write:
            audit_logger.log_security_event(
                event_type="rate_limit_exceeded",
                description="Too many requests",
                severity="warning",
            )

            entry = mock_write.call_args[0][0]

            assert entry["event_type"] == "rate_limit_exceeded"
            assert entry["description"] == "Too many requests"
            assert entry["severity"] == "warning"

    def test_log_security_event_with_context(
        self, audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test logging security event with tool context."""
        with mock.patch.object(audit_logger, "_write_entry") as mock_write:
            audit_logger.log_security_event(
                event_type="suspicious_activity",
                description="Multiple failed auth attempts",
                severity="critical",
                ctx=sample_context,
                details={"attempts": 10},
            )

            entry = mock_write.call_args[0][0]

            assert entry["user_id"] == "admin@example.com"
            assert entry["role"] == "admin"
            assert entry["source_ip"] == "192.168.1.100"
            assert entry["request_id"] == "req-12345"
            assert entry["details"]["attempts"] == 10


# =============================================================================
# Tests for Sensitive Field Masking
# =============================================================================


class TestSensitiveFieldMasking:
    """Tests for masking sensitive fields in logs."""

    def test_mask_token_field(self, audit_logger: AuditLogger) -> None:
        """Test that token fields are masked."""
        data = {"access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"}
        masked = audit_logger._mask_sensitive_fields(data)

        assert masked["access_token"] == "ey...ig"

    def test_mask_password_field(self, audit_logger: AuditLogger) -> None:
        """Test that password fields are masked."""
        data = {"password": "supersecret"}
        masked = audit_logger._mask_sensitive_fields(data)

        assert masked["password"] == "su...et"

    def test_mask_short_value(self, audit_logger: AuditLogger) -> None:
        """Test that short sensitive values are fully masked."""
        data = {"api_key": "short"}
        masked = audit_logger._mask_sensitive_fields(data)

        assert masked["api_key"] == "<masked>"

    def test_mask_nested_fields(self, audit_logger: AuditLogger) -> None:
        """Test that nested sensitive fields are masked."""
        data = {
            "config": {
                "auth_token": "verylongtoken12345",
                "setting": "value",
            }
        }
        masked = audit_logger._mask_sensitive_fields(data)

        assert masked["config"]["auth_token"] == "ve...45"
        assert masked["config"]["setting"] == "value"

    def test_mask_preserves_non_sensitive(self, audit_logger: AuditLogger) -> None:
        """Test that non-sensitive fields are preserved."""
        data = {
            "user": "admin",
            "action": "login",
            "timestamp": "2025-01-01T00:00:00Z",
        }
        masked = audit_logger._mask_sensitive_fields(data)

        assert masked["user"] == "admin"
        assert masked["action"] == "login"
        assert masked["timestamp"] == "2025-01-01T00:00:00Z"

    def test_mask_list_of_dicts(self, audit_logger: AuditLogger) -> None:
        """Test that lists of dicts are processed."""
        data = {
            "items": [
                {"name": "item1", "secret_key": "verysecret123"},
                {"name": "item2", "value": "normal"},
            ]
        }
        masked = audit_logger._mask_sensitive_fields(data)

        assert masked["items"][0]["secret_key"] == "ve...23"
        assert masked["items"][0]["name"] == "item1"
        assert masked["items"][1]["value"] == "normal"


# =============================================================================
# Tests for File Logging
# =============================================================================


class TestFileLogging:
    """Tests for writing audit logs to file."""

    def test_write_entry_to_file(
        self, file_audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test that entries are written to file."""
        file_audit_logger.log_tool_call(
            ctx=sample_context,
            status="success",
        )

        # Read the file and verify
        log_path = Path(file_audit_logger._audit_log_path)
        with open(log_path) as f:
            content = f.read().strip()

        entry = json.loads(content)
        assert entry["event_type"] == "tool_call"
        assert entry["user_id"] == "admin@example.com"
        assert entry["action"] == "system.reboot"

    def test_multiple_entries(
        self, file_audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test multiple entries are appended to file."""
        file_audit_logger.log_tool_call(ctx=sample_context, status="success")
        file_audit_logger.log_tool_call(ctx=sample_context, status="error")

        log_path = Path(file_audit_logger._audit_log_path)
        with open(log_path) as f:
            lines = f.readlines()

        assert len(lines) == 2
        assert json.loads(lines[0])["result"] == "success"
        assert json.loads(lines[1])["result"] == "error"

    def test_timestamp_format(
        self, file_audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test that timestamp is ISO 8601 format."""
        file_audit_logger.log_tool_call(ctx=sample_context, status="success")

        log_path = Path(file_audit_logger._audit_log_path)
        with open(log_path) as f:
            entry = json.loads(f.read().strip())

        # Should be parseable as ISO 8601
        timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        assert timestamp.tzinfo is not None


# =============================================================================
# Tests for Global Audit Logger
# =============================================================================


class TestGlobalAuditLogger:
    """Tests for global audit logger management."""

    def test_get_audit_logger_default(self) -> None:
        """Test getting default audit logger."""
        # Clear any existing global logger
        set_audit_logger(None)

        logger = get_audit_logger()
        assert isinstance(logger, AuditLogger)

    def test_set_and_get_audit_logger(self, tmp_path: Path) -> None:
        """Test setting and getting global audit logger."""
        audit_path = tmp_path / "audit.log"
        custom_logger = AuditLogger(
            audit_log_path=str(audit_path),
            log_to_file=True,
        )

        set_audit_logger(custom_logger)
        retrieved = get_audit_logger()

        assert retrieved is custom_logger

    def test_log_tool_call_function(self, sample_context: ToolContext) -> None:
        """Test the convenience log_tool_call function."""
        mock_logger = mock.MagicMock(spec=AuditLogger)
        set_audit_logger(mock_logger)

        log_tool_call(
            ctx=sample_context,
            status="success",
            params={"key": "value"},
        )

        mock_logger.log_tool_call.assert_called_once_with(
            ctx=sample_context,
            status="success",
            error_code=None,
            params={"key": "value"},
            duration_ms=None,
            extra=None,
        )


# =============================================================================
# Tests for Entry Building
# =============================================================================


class TestEntryBuilding:
    """Tests for audit entry building."""

    def test_build_entry_all_fields(
        self, audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test building entry with all fields."""
        entry = audit_logger._build_entry(
            event_type="tool_call",
            ctx=sample_context,
            status="success",
            error_code=None,
            params={"key": "value"},
            duration_ms=100.5,
            extra={"custom": "field"},
        )

        # Check required fields
        assert "timestamp" in entry
        assert entry["event_type"] == "tool_call"
        assert entry["user_id"] == "admin@example.com"
        assert entry["role"] == "admin"
        assert entry["action"] == "system.reboot"
        assert entry["result"] == "success"
        assert entry["request_id"] == "req-12345"
        assert entry["source_ip"] == "192.168.1.100"
        assert entry["params"] == {"key": "value"}
        assert entry["duration_ms"] == 100.5
        assert entry["custom"] == "field"

    def test_build_entry_minimal(
        self, audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test building entry with minimal fields."""
        entry = audit_logger._build_entry(
            event_type="tool_call",
            ctx=sample_context,
            status="success",
        )

        assert "timestamp" in entry
        assert entry["event_type"] == "tool_call"
        assert entry["user_id"] == "admin@example.com"
        assert entry["result"] == "success"
        assert "error_code" not in entry
        assert "params" not in entry
        assert "duration_ms" not in entry

    def test_build_entry_with_error(
        self, audit_logger: AuditLogger, sample_context: ToolContext
    ) -> None:
        """Test building entry with error."""
        entry = audit_logger._build_entry(
            event_type="tool_call",
            ctx=sample_context,
            status="error",
            error_code="permission_denied",
        )

        assert entry["result"] == "error"
        assert entry["error_code"] == "permission_denied"
