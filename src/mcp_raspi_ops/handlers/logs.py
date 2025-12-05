"""
Log reading handlers for the Privileged Agent.

This module implements handlers for log reading operations:
- logs.read_app: Read application logs
- logs.read_audit: Read audit logs

These handlers run with elevated privileges to access log files.

Design follows Doc 09 §5 (Log query).
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

logger = get_logger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


def _read_log_file(
    log_path: str,
    limit: int,
    offset: int,
    level: str | None,
    start_time: str | None,
    end_time: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Read log entries from a JSON Lines log file.

    Args:
        log_path: Path to the log file.
        limit: Maximum entries to return.
        offset: Number of entries to skip.
        level: Filter by log level.
        start_time: Filter entries after this ISO 8601 timestamp.
        end_time: Filter entries before this ISO 8601 timestamp.

    Returns:
        Tuple of (list of log entries, total matching count).
    """
    path = Path(log_path)
    if not path.exists():
        return [], 0

    # Parse time filters
    start_dt = None
    end_dt = None
    if start_time:
        with contextlib.suppress(ValueError):
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    if end_time:
        with contextlib.suppress(ValueError):
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

    entries: list[dict[str, Any]] = []
    total_matching = 0
    skipped = 0

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        # Process lines in reverse order (most recent first)
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
                if entry_level != level.upper():
                    continue

            # Apply time range filters
            entry_ts = entry.get("timestamp")
            if entry_ts and (start_dt or end_dt):
                try:
                    entry_time = datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))

                    # start_time is inclusive, end_time is exclusive
                    if start_dt is not None and entry_time < start_dt:
                        continue
                    if end_dt is not None and entry_time >= end_dt:
                        continue
                except (ValueError, AttributeError):
                    pass

            total_matching += 1

            if skipped < offset:
                skipped += 1
                continue

            if len(entries) < limit:
                entries.append(entry)

    except Exception as e:
        logger.warning(f"Error reading log file {log_path}: {e}")

    return entries, total_matching


# =============================================================================
# logs.read_app Handler
# =============================================================================


async def handle_logs_read_app(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the logs.read_app operation.

    Reads application logs from the specified path.

    Args:
        request: IPC request with params:
            - log_path: Path to the log file
            - limit: Maximum entries to return
            - offset: Number of entries to skip
            - level: Filter by log level
            - start_time: Filter entries after this timestamp
            - end_time: Filter entries before this timestamp

    Returns:
        Dict with entries and total count.

    Raises:
        HandlerError: If operation fails.
    """
    params = request.params
    log_path = params.get("log_path", "/var/log/mcp-raspi/app.log")
    limit = params.get("limit", 100)
    offset = params.get("offset", 0)
    level = params.get("level")
    start_time = params.get("start_time")
    end_time = params.get("end_time")

    logger.debug(
        "logs.read_app request",
        extra={
            "request_id": request.id,
            "log_path": log_path,
            "limit": limit,
            "offset": offset,
            "level": level,
        },
    )

    # Validate log path exists and is readable
    path = Path(log_path)
    if not path.exists():
        return {
            "entries": [],
            "total_count": 0,
            "error": f"Log file not found: {log_path}",
        }

    if not path.is_file():
        raise HandlerError(
            code="invalid_argument",
            message=f"Log path is not a file: {log_path}",
            details={"log_path": log_path},
        )

    try:
        entries, total_count = _read_log_file(
            log_path=log_path,
            limit=limit,
            offset=offset,
            level=level,
            start_time=start_time,
            end_time=end_time,
        )

        return {
            "entries": entries,
            "total_count": total_count,
        }

    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to read log file: {e}",
            details={"log_path": log_path, "error": str(e)},
        ) from e


# =============================================================================
# logs.read_audit Handler
# =============================================================================


async def handle_logs_read_audit(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the logs.read_audit operation.

    Reads audit logs from the specified path.

    Args:
        request: IPC request with params:
            - log_path: Path to the audit log file
            - limit: Maximum entries to return
            - offset: Number of entries to skip
            - level: Filter by log level
            - start_time: Filter entries after this timestamp
            - end_time: Filter entries before this timestamp
            - user_id: Filter by user ID
            - action: Filter by action/tool name

    Returns:
        Dict with entries and total count.

    Raises:
        HandlerError: If operation fails.
    """
    params = request.params
    log_path = params.get("log_path", "/var/log/mcp-raspi/audit.log")
    limit = params.get("limit", 100)
    offset = params.get("offset", 0)
    level = params.get("level")
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    user_id_filter = params.get("user_id")
    action_filter = params.get("action")

    logger.debug(
        "logs.read_audit request",
        extra={
            "request_id": request.id,
            "log_path": log_path,
            "limit": limit,
            "offset": offset,
        },
    )

    path = Path(log_path)
    if not path.exists():
        return {
            "entries": [],
            "total_count": 0,
            "error": f"Audit log file not found: {log_path}",
        }

    if not path.is_file():
        raise HandlerError(
            code="invalid_argument",
            message=f"Audit log path is not a file: {log_path}",
            details={"log_path": log_path},
        )

    try:
        entries, total_count = _read_audit_log_file(
            log_path=log_path,
            limit=limit,
            offset=offset,
            level=level,
            start_time=start_time,
            end_time=end_time,
            user_id_filter=user_id_filter,
            action_filter=action_filter,
        )

        return {
            "entries": entries,
            "total_count": total_count,
        }

    except Exception as e:
        raise HandlerError(
            code="internal",
            message=f"Failed to read audit log file: {e}",
            details={"log_path": log_path, "error": str(e)},
        ) from e


def _read_audit_log_file(
    log_path: str,
    limit: int,
    offset: int,
    level: str | None,
    start_time: str | None,
    end_time: str | None,
    user_id_filter: str | None,
    action_filter: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Read audit log entries with additional filters.

    Args:
        log_path: Path to the audit log file.
        limit: Maximum entries to return.
        offset: Number of entries to skip.
        level: Filter by log level.
        start_time: Filter entries after this timestamp.
        end_time: Filter entries before this timestamp.
        user_id_filter: Filter by user ID.
        action_filter: Filter by action/tool name.

    Returns:
        Tuple of (list of audit entries, total matching count).
    """
    path = Path(log_path)
    if not path.exists():
        return [], 0

    # Parse time filters
    start_dt = None
    end_dt = None
    if start_time:
        with contextlib.suppress(ValueError):
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    if end_time:
        with contextlib.suppress(ValueError):
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

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
                if entry_level and entry_level != level.upper():
                    continue

            # Apply time range filters
            entry_ts = entry.get("timestamp")
            if entry_ts and (start_dt or end_dt):
                try:
                    entry_time = datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))

                    # start_time is inclusive, end_time is exclusive
                    if start_dt is not None and entry_time < start_dt:
                        continue
                    if end_dt is not None and entry_time >= end_dt:
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
                entries.append(entry)

    except Exception as e:
        logger.warning(f"Error reading audit log file {log_path}: {e}")

    return entries, total_matching


# =============================================================================
# Handler Registration
# =============================================================================


def register_logs_handlers(registry: HandlerRegistry) -> None:
    """
    Register log handlers with the handler registry.

    Args:
        registry: The handler registry to register with.
    """
    registry.register("logs.read_app", handle_logs_read_app)
    registry.register("logs.read_audit", handle_logs_read_audit)
    logger.debug("Registered logs handlers")
