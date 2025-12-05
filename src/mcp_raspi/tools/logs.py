"""
Logs namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `logs.*` namespace:
- logs.get_recent_app_logs: Query application logs with filters
- logs.get_recent_audit_logs: Query audit logs with filters (admin only)

Design follows Doc 05 §9-10 (logs namespace) and Doc 09 §5 (Log query).

Features:
- Time range filtering (start/end timestamps)
- Level filtering (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Pagination (offset/limit)
- Sensitive data masking for returned log entries
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import InvalidArgumentError
from mcp_raspi.logging import get_logger
from mcp_raspi.security.audit_logger import get_audit_logger
from mcp_raspi.security.rbac import require_role

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Valid log levels for filtering
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Maximum entries per request (prevents excessive memory usage)
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

# Maximum time range to query (days)
MAX_TIME_RANGE_DAYS = 30

# Sensitive data patterns for masking
SENSITIVE_PATTERNS = [
    (
        re.compile(r"(api[_-]?key)\s*[=:]\s*['\"]?[\w\-]+['\"]?", re.IGNORECASE),
        r"\1=***REDACTED***",
    ),
    (
        re.compile(r"(token)\s*[=:]\s*['\"]?[\w\-._]+['\"]?", re.IGNORECASE),
        r"\1=***REDACTED***",
    ),
    (
        re.compile(r"(password)\s*[=:]\s*['\"]?[^\s'\"]+['\"]?", re.IGNORECASE),
        r"\1=***REDACTED***",
    ),
    (
        re.compile(r"(secret)\s*[=:]\s*['\"]?[\w\-._]+['\"]?", re.IGNORECASE),
        r"\1=***REDACTED***",
    ),
    (
        re.compile(r"(credential)\s*[=:]\s*['\"]?[\w\-._]+['\"]?", re.IGNORECASE),
        r"\1=***REDACTED***",
    ),
    (
        re.compile(r"(private[_-]?key)\s*[=:]\s*['\"]?[\w\-._]+['\"]?", re.IGNORECASE),
        r"\1=***REDACTED***",
    ),
    (re.compile(r"(bearer)\s+[\w\-._]+", re.IGNORECASE), r"\1 ***REDACTED***"),
]

# Sensitive field names in JSON objects
SENSITIVE_FIELD_NAMES = {
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "secret_key",
    "private_key",
    "credential",
    "auth",
    "authorization",
    "bearer",
}


# =============================================================================
# Sensitive Data Masking
# =============================================================================


def mask_sensitive_string(text: str) -> str:
    """
    Mask sensitive data in a string.

    Applies regex patterns to redact API keys, tokens, passwords, etc.

    Args:
        text: The string to mask.

    Returns:
        String with sensitive data masked.
    """
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def mask_sensitive_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Mask sensitive fields in a dictionary.

    Args:
        data: Dictionary to mask.

    Returns:
        Dictionary with sensitive values masked.
    """
    masked = {}
    for key, value in data.items():
        key_lower = key.lower()
        is_sensitive = any(s in key_lower for s in SENSITIVE_FIELD_NAMES)

        if is_sensitive:
            if isinstance(value, str) and len(value) > 8:
                # Show first and last 2 chars for long values
                masked[key] = f"{value[:2]}***{value[-2:]}"
            else:
                masked[key] = "***REDACTED***"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_dict(value)
        elif isinstance(value, list):
            masked[key] = [
                mask_sensitive_dict(item)
                if isinstance(item, dict)
                else mask_sensitive_string(str(item))
                if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            masked[key] = mask_sensitive_string(value)
        else:
            masked[key] = value

    return masked


def mask_log_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Mask sensitive data in a log entry.

    Args:
        entry: Log entry dictionary.

    Returns:
        Log entry with sensitive data masked.
    """
    return mask_sensitive_dict(entry)


# =============================================================================
# Validation Helpers
# =============================================================================


def _validate_limit(limit: Any) -> int:
    """
    Validate and normalize limit parameter.

    Args:
        limit: Raw limit value.

    Returns:
        Validated limit as integer.

    Raises:
        InvalidArgumentError: If limit is invalid.
    """
    if limit is None:
        return DEFAULT_LIMIT

    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid limit: {limit}",
                details={"parameter": "limit", "value": limit},
            ) from e

    if limit < 1:
        raise InvalidArgumentError(
            "limit must be at least 1",
            details={"parameter": "limit", "value": limit, "min": 1},
        )

    if limit > MAX_LIMIT:
        raise InvalidArgumentError(
            f"limit cannot exceed {MAX_LIMIT}",
            details={"parameter": "limit", "value": limit, "max": MAX_LIMIT},
        )

    return limit


def _validate_offset(offset: Any) -> int:
    """
    Validate and normalize offset parameter.

    Args:
        offset: Raw offset value.

    Returns:
        Validated offset as integer.

    Raises:
        InvalidArgumentError: If offset is invalid.
    """
    if offset is None:
        return 0

    if not isinstance(offset, int):
        try:
            offset = int(offset)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"Invalid offset: {offset}",
                details={"parameter": "offset", "value": offset},
            ) from e

    if offset < 0:
        raise InvalidArgumentError(
            "offset must be non-negative",
            details={"parameter": "offset", "value": offset, "min": 0},
        )

    return offset


def _validate_level(level: Any) -> str | None:
    """
    Validate log level filter.

    Args:
        level: Raw level value.

    Returns:
        Validated level string or None.

    Raises:
        InvalidArgumentError: If level is invalid.
    """
    if level is None:
        return None

    level_str = str(level).upper()
    if level_str not in VALID_LOG_LEVELS:
        raise InvalidArgumentError(
            f"Invalid log level: {level}. Must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}",
            details={
                "parameter": "level",
                "value": level,
                "valid_values": sorted(VALID_LOG_LEVELS),
            },
        )
    return level_str


def _validate_timestamp(ts: Any, param_name: str) -> datetime | None:
    """
    Validate and parse ISO 8601 timestamp.

    Args:
        ts: Raw timestamp value.
        param_name: Parameter name for error messages.

    Returns:
        Validated datetime or None.

    Raises:
        InvalidArgumentError: If timestamp is invalid.
    """
    if ts is None:
        return None

    if isinstance(ts, datetime):
        return ts

    if not isinstance(ts, str):
        raise InvalidArgumentError(
            f"Invalid {param_name}: must be ISO 8601 timestamp string",
            details={"parameter": param_name, "value": ts},
        )

    try:
        # Parse ISO 8601 format
        # Handle both 'Z' suffix and '+00:00' timezone
        ts_str = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except ValueError as e:
        raise InvalidArgumentError(
            f"Invalid {param_name}: {ts}. Must be ISO 8601 format (e.g., '2025-01-15T14:30:00Z')",
            details={"parameter": param_name, "value": ts},
        ) from e


# =============================================================================
# Log File Reading
# =============================================================================


def _read_log_entries(
    log_path: str,
    limit: int,
    offset: int,
    level: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Read log entries from a JSON Lines log file.

    Reads from the end of the file (most recent entries first) and applies filters.

    Args:
        log_path: Path to the log file.
        limit: Maximum entries to return.
        offset: Number of entries to skip.
        level: Filter by log level.
        start_time: Filter entries after this time.
        end_time: Filter entries before this time.

    Returns:
        Tuple of (list of log entries, total matching count).
    """
    path = Path(log_path)
    if not path.exists():
        return [], 0

    entries: list[dict[str, Any]] = []
    total_matching = 0
    skipped = 0

    try:
        with open(path, encoding="utf-8") as f:
            # Read all lines (we read from end to get most recent first)
            lines = f.readlines()

        # Process lines in reverse order (most recent first)
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines
                continue

            # Apply level filter
            if level is not None:
                entry_level = entry.get("level", "").upper()
                if entry_level != level:
                    continue

            # Apply time range filters
            entry_ts = entry.get("timestamp")
            if entry_ts:
                try:
                    entry_time = datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))

                    # start_time is inclusive, end_time is exclusive
                    if start_time is not None and entry_time < start_time:
                        continue
                    if end_time is not None and entry_time >= end_time:
                        continue
                except (ValueError, AttributeError):
                    # Skip entries with invalid timestamps
                    pass

            # Count matching entries
            total_matching += 1

            # Apply pagination
            if skipped < offset:
                skipped += 1
                continue

            if len(entries) < limit:
                # Mask sensitive data before returning
                masked_entry = mask_log_entry(entry)
                entries.append(masked_entry)

    except Exception as e:
        logger.warning(f"Error reading log file {log_path}: {e}")

    return entries, total_matching


def _get_log_path(config: AppConfig | None, log_type: str) -> str:
    """
    Get log file path from configuration.

    Args:
        config: AppConfig instance.
        log_type: Type of log ("app" or "audit").

    Returns:
        Path to the log file.
    """
    if config is None:
        if log_type == "audit":
            return "/var/log/mcp-raspi/audit.log"
        return "/var/log/mcp-raspi/app.log"

    if log_type == "audit":
        return config.logging.audit_log_path
    return config.logging.app_log_path


# =============================================================================
# logs.get_recent_app_logs
# =============================================================================


@require_role("viewer")
async def handle_logs_get_recent_app_logs(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the logs.get_recent_app_logs tool call.

    Queries application logs with filtering and pagination.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - limit: Maximum entries to return (default 100, max 1000)
            - offset: Number of entries to skip (default 0)
            - level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            - start_time: Filter entries after this ISO 8601 timestamp
            - end_time: Filter entries before this ISO 8601 timestamp
        config: Optional AppConfig for log paths.

    Returns:
        Dictionary with:
        - entries: List of log entries
        - total_count: Total matching entries
        - has_more: Whether more entries are available
        - filters_applied: Applied filter parameters

    Raises:
        InvalidArgumentError: If parameters are invalid.
    """
    # Validate parameters
    limit = _validate_limit(params.get("limit"))
    offset = _validate_offset(params.get("offset"))
    level = _validate_level(params.get("level"))
    start_time = _validate_timestamp(params.get("start_time"), "start_time")
    end_time = _validate_timestamp(params.get("end_time"), "end_time")

    # Validate time range
    if start_time and end_time and start_time > end_time:
        raise InvalidArgumentError(
            "start_time cannot be after end_time",
            details={
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            },
        )

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"limit": limit, "offset": offset, "level": level},
    )

    logger.info(
        "logs.get_recent_app_logs requested",
        extra={
            "user": ctx.caller.user_id,
            "limit": limit,
            "offset": offset,
            "level": level,
        },
    )

    # Get log file path
    log_path = _get_log_path(config, "app")

    # Read and filter log entries
    entries, total_count = _read_log_entries(
        log_path=log_path,
        limit=limit,
        offset=offset,
        level=level,
        start_time=start_time,
        end_time=end_time,
    )

    has_more = (offset + len(entries)) < total_count

    return {
        "entries": entries,
        "total_count": total_count,
        "returned_count": len(entries),
        "has_more": has_more,
        "filters_applied": {
            "limit": limit,
            "offset": offset,
            "level": level,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# logs.get_recent_audit_logs
# =============================================================================


@require_role("admin")
async def handle_logs_get_recent_audit_logs(
    ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the logs.get_recent_audit_logs tool call.

    Queries audit logs with filtering and pagination.
    Requires admin role due to sensitive nature of audit logs.

    Args:
        ctx: The ToolContext for this request.
        params: Request parameters:
            - limit: Maximum entries to return (default 100, max 1000)
            - offset: Number of entries to skip (default 0)
            - level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            - start_time: Filter entries after this ISO 8601 timestamp
            - end_time: Filter entries before this ISO 8601 timestamp
            - user_id: Filter by user ID
            - action: Filter by action/tool name
        config: Optional AppConfig for log paths.

    Returns:
        Dictionary with:
        - entries: List of audit log entries
        - total_count: Total matching entries
        - has_more: Whether more entries are available
        - filters_applied: Applied filter parameters

    Raises:
        PermissionDeniedError: If caller lacks admin role.
        InvalidArgumentError: If parameters are invalid.
    """
    # Validate parameters
    limit = _validate_limit(params.get("limit"))
    offset = _validate_offset(params.get("offset"))
    level = _validate_level(params.get("level"))
    start_time = _validate_timestamp(params.get("start_time"), "start_time")
    end_time = _validate_timestamp(params.get("end_time"), "end_time")
    user_id_filter = params.get("user_id")
    action_filter = params.get("action")

    # Validate time range
    if start_time and end_time and start_time > end_time:
        raise InvalidArgumentError(
            "start_time cannot be after end_time",
            details={
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            },
        )

    audit = get_audit_logger()
    audit.log_tool_call(
        ctx=ctx,
        status="initiated",
        params={"limit": limit, "offset": offset, "level": level},
    )

    logger.info(
        "logs.get_recent_audit_logs requested",
        extra={
            "user": ctx.caller.user_id,
            "limit": limit,
            "offset": offset,
            "level": level,
        },
    )

    # Get log file path
    log_path = _get_log_path(config, "audit")

    # Read log entries with custom filtering for audit logs
    entries, total_count = _read_audit_log_entries(
        log_path=log_path,
        limit=limit,
        offset=offset,
        level=level,
        start_time=start_time,
        end_time=end_time,
        user_id_filter=user_id_filter,
        action_filter=action_filter,
    )

    has_more = (offset + len(entries)) < total_count

    return {
        "entries": entries,
        "total_count": total_count,
        "returned_count": len(entries),
        "has_more": has_more,
        "filters_applied": {
            "limit": limit,
            "offset": offset,
            "level": level,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "user_id": user_id_filter,
            "action": action_filter,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _read_audit_log_entries(
    log_path: str,
    limit: int,
    offset: int,
    level: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    user_id_filter: str | None,
    action_filter: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Read audit log entries with additional audit-specific filters.

    Args:
        log_path: Path to the audit log file.
        limit: Maximum entries to return.
        offset: Number of entries to skip.
        level: Filter by log level.
        start_time: Filter entries after this time.
        end_time: Filter entries before this time.
        user_id_filter: Filter by user ID.
        action_filter: Filter by action/tool name.

    Returns:
        Tuple of (list of audit entries, total matching count).
    """
    path = Path(log_path)
    if not path.exists():
        return [], 0

    entries: list[dict[str, Any]] = []
    total_matching = 0
    skipped = 0

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Apply level filter
            if level is not None:
                entry_level = entry.get("level", "").upper()
                # Audit logs may not have level, treat as INFO
                if entry_level and entry_level != level:
                    continue

            # Apply time range filters
            entry_ts = entry.get("timestamp")
            if entry_ts:
                try:
                    entry_time = datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))

                    # start_time is inclusive, end_time is exclusive
                    if start_time is not None and entry_time < start_time:
                        continue
                    if end_time is not None and entry_time >= end_time:
                        continue
                except (ValueError, AttributeError):
                    pass

            # Apply user_id filter
            if user_id_filter is not None:
                entry_user = entry.get("user_id", "")
                if user_id_filter.lower() not in str(entry_user).lower():
                    continue

            # Apply action filter
            if action_filter is not None:
                entry_action = entry.get("action", "")
                if action_filter.lower() not in str(entry_action).lower():
                    continue

            total_matching += 1

            if skipped < offset:
                skipped += 1
                continue

            if len(entries) < limit:
                masked_entry = mask_log_entry(entry)
                entries.append(masked_entry)

    except Exception as e:
        logger.warning(f"Error reading audit log file {log_path}: {e}")

    return entries, total_matching
