"""
Audit logging for privileged operations in the Raspberry Pi MCP Server.

This module provides structured audit logging following the design
specifications in Doc 04 §5 (Audit Logging) and Doc 09 §4 (Audit Logging).

Audit logs record:
- All MCP tool invocations (especially privileged operations)
- Authentication/authorization events
- System state changes
- Security-relevant configuration changes
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_raspi.config import LoggingConfig
    from mcp_raspi.context import ToolContext

logger = logging.getLogger("mcp_raspi.security.audit_logger")


class AuditLogger:
    """
    Structured audit logger for privileged operations.

    Records tool invocations and security events with consistent
    fields for analysis and compliance.

    Audit log format (JSON):
    {
        "timestamp": "2025-01-15T14:30:00Z",
        "event_type": "tool_call",
        "user_id": "user@example.com",
        "role": "admin",
        "action": "system.reboot",
        "result": "success",
        "params": {...},
        "duration_ms": 45.2,
        "source_ip": "192.168.1.100",
        "request_id": "req-12345"
    }

    Example:
        >>> audit_logger = AuditLogger.from_config(config.logging)
        >>> audit_logger.log_tool_call(ctx, status="success")
    """

    # Fields that should be masked in audit logs
    SENSITIVE_FIELD_PATTERNS = [
        "token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "secret_key",
        "private_key",
        "credential",
        "auth",
    ]

    def __init__(
        self,
        audit_log_path: str | None = None,
        log_to_file: bool = True,
        log_to_stdout: bool = False,
    ) -> None:
        """
        Initialize the audit logger.

        Args:
            audit_log_path: Path to the audit log file.
            log_to_file: Whether to write to file.
            log_to_stdout: Whether to write to stdout.
        """
        self._audit_log_path = audit_log_path
        self._log_to_file = log_to_file
        self._log_to_stdout = log_to_stdout
        self._file_logger: logging.Logger | None = None

        if log_to_file and audit_log_path:
            self._setup_file_logger(audit_log_path)

    @classmethod
    def from_config(cls, config: LoggingConfig) -> AuditLogger:
        """
        Create an AuditLogger from configuration.

        Args:
            config: LoggingConfig with audit log settings.

        Returns:
            Configured AuditLogger instance.
        """
        return cls(
            audit_log_path=config.audit_log_path,
            log_to_file=True,
            log_to_stdout=config.log_to_stdout,
        )

    def _setup_file_logger(self, path: str) -> None:
        """
        Set up file logging for audit logs.

        Args:
            path: Path to the audit log file.
        """
        try:
            # Ensure directory exists
            log_dir = Path(path).parent
            log_dir.mkdir(parents=True, exist_ok=True)

            # Create a dedicated logger for audit
            self._file_logger = logging.getLogger("mcp_raspi.audit")
            self._file_logger.setLevel(logging.INFO)
            self._file_logger.propagate = False

            # Remove existing handlers
            self._file_logger.handlers.clear()

            # Add file handler
            handler = logging.FileHandler(path, mode="a", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._file_logger.addHandler(handler)

            logger.info("Audit logging initialized to %s", path)
        except Exception as e:
            logger.error("Failed to setup audit file logging: %s", str(e))
            self._file_logger = None

    def log_tool_call(
        self,
        ctx: ToolContext,
        status: str,
        error_code: str | None = None,
        params: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """
        Log a tool invocation.

        Args:
            ctx: Tool context with caller and request information.
            status: Result status ("success" or "error").
            error_code: Error code if status is "error".
            params: Tool parameters (sensitive fields will be masked).
            duration_ms: Execution duration in milliseconds.
            extra: Additional fields to include.
        """
        entry = self._build_entry(
            event_type="tool_call",
            ctx=ctx,
            status=status,
            error_code=error_code,
            params=params,
            duration_ms=duration_ms,
            extra=extra,
        )
        self._write_entry(entry)

    def log_auth_event(
        self,
        event_type: str,
        success: bool,
        user_id: str | None = None,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an authentication or authorization event.

        Args:
            event_type: Type of auth event (e.g., "auth_success", "auth_failure").
            success: Whether the event was successful.
            user_id: User identifier if known.
            source_ip: Client IP address.
            details: Additional event details.
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "success": success,
            "user_id": user_id,
            "source_ip": source_ip,
        }

        if details:
            entry["details"] = self._mask_sensitive_fields(details)

        self._write_entry(entry)

    def log_security_event(
        self,
        event_type: str,
        description: str,
        severity: str = "info",
        ctx: ToolContext | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log a security-related event.

        Args:
            event_type: Type of security event.
            description: Human-readable description.
            severity: Event severity (info, warning, error, critical).
            ctx: Optional tool context.
            details: Additional event details.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "severity": severity,
            "description": description,
        }

        if ctx:
            entry["user_id"] = ctx.caller.user_id
            entry["role"] = ctx.caller.role
            entry["source_ip"] = ctx.caller.ip_address
            entry["request_id"] = ctx.request_id

        if details:
            entry["details"] = self._mask_sensitive_fields(details)

        self._write_entry(entry)

    def _build_entry(
        self,
        event_type: str,
        ctx: ToolContext,
        status: str,
        error_code: str | None = None,
        params: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build an audit log entry.

        Args:
            event_type: Type of event.
            ctx: Tool context.
            status: Result status.
            error_code: Optional error code.
            params: Tool parameters.
            duration_ms: Execution duration.
            extra: Additional fields.

        Returns:
            Audit log entry dictionary.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "user_id": ctx.caller.user_id,
            "role": ctx.caller.role,
            "action": ctx.tool_name,
            "result": status,
            "request_id": ctx.request_id,
        }

        if ctx.caller.ip_address:
            entry["source_ip"] = ctx.caller.ip_address

        if error_code:
            entry["error_code"] = error_code

        if params:
            entry["params"] = self._mask_sensitive_fields(params)

        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 2)

        if extra:
            for key, value in extra.items():
                if key not in entry:
                    entry[key] = value

        return entry

    def _mask_sensitive_fields(
        self, data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Mask sensitive fields in a dictionary.

        Sensitive fields (containing 'token', 'password', 'secret', etc.)
        are replaced with '<masked>'.

        Args:
            data: Dictionary to mask.

        Returns:
            Dictionary with sensitive values masked.
        """
        masked = {}
        for key, value in data.items():
            key_lower = key.lower()
            is_sensitive = any(
                pattern in key_lower for pattern in self.SENSITIVE_FIELD_PATTERNS
            )

            if is_sensitive:
                if isinstance(value, str) and len(value) > 8:
                    # Show first and last 2 chars
                    masked[key] = f"{value[:2]}...{value[-2:]}"
                else:
                    masked[key] = "<masked>"
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive_fields(value)
            elif isinstance(value, list):
                masked[key] = [
                    self._mask_sensitive_fields(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked[key] = value

        return masked

    def _write_entry(self, entry: dict[str, Any]) -> None:
        """
        Write an audit log entry.

        Args:
            entry: The audit log entry to write.
        """
        json_line = json.dumps(entry, default=str)

        # Write to file
        if self._file_logger:
            try:
                self._file_logger.info(json_line)
            except Exception as e:
                logger.error("Failed to write audit log entry: %s", str(e))

        # Also log to main logger at debug level for visibility
        if self._log_to_stdout:
            logger.info("AUDIT: %s", json_line)


# Global audit logger instance (initialized during app startup)
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """
    Get the global audit logger instance.

    Returns:
        The configured AuditLogger.

    Raises:
        RuntimeError: If audit logger not initialized.
    """
    global _audit_logger
    if _audit_logger is None:
        # Return a default instance that logs to stdout
        return AuditLogger(log_to_file=False, log_to_stdout=True)
    return _audit_logger


def set_audit_logger(audit_logger: AuditLogger) -> None:
    """
    Set the global audit logger instance.

    Args:
        audit_logger: The AuditLogger to use globally.
    """
    global _audit_logger
    _audit_logger = audit_logger


def log_tool_call(
    ctx: ToolContext,
    status: str,
    error_code: str | None = None,
    params: dict[str, Any] | None = None,
    duration_ms: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Convenience function to log a tool call using the global audit logger.

    Args:
        ctx: Tool context.
        status: Result status.
        error_code: Optional error code.
        params: Tool parameters.
        duration_ms: Execution duration.
        extra: Additional fields.
    """
    get_audit_logger().log_tool_call(
        ctx=ctx,
        status=status,
        error_code=error_code,
        params=params,
        duration_ms=duration_ms,
        extra=extra,
    )
