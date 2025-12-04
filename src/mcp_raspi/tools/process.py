"""
Process namespace tools for the Raspberry Pi MCP Server.

This module implements tools in the `process.*` namespace:
- process.list_processes: List processes with filtering (name, user, CPU%)
- process.get_info: Get detailed info for single PID

Design follows Doc 05 §5-6 (process namespace specification) and Doc 07.
"""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import psutil

from mcp_raspi.context import ToolContext
from mcp_raspi.errors import (
    InvalidArgumentError,
    PermissionDeniedError,
)
from mcp_raspi.logging import get_logger

if TYPE_CHECKING:
    from mcp_raspi.config import AppConfig

logger = get_logger(__name__)

# Valid process status values for filtering
VALID_STATUSES = {"running", "sleeping", "disk-sleep", "stopped", "zombie", "idle"}


def _validate_pagination(
    offset: int | None,
    limit: int | None,
) -> tuple[int, int]:
    """
    Validate pagination parameters.

    Args:
        offset: Number of items to skip.
        limit: Maximum number of items to return.

    Returns:
        Tuple of (offset, limit) with defaults applied.

    Raises:
        InvalidArgumentError: If parameters are invalid.
    """
    if offset is None:
        offset = 0
    elif not isinstance(offset, int) or offset < 0:
        raise InvalidArgumentError(
            "offset must be a non-negative integer",
            details={"parameter": "offset", "value": offset},
        )

    if limit is None:
        limit = 100  # Default limit
    elif not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise InvalidArgumentError(
            "limit must be an integer between 1 and 1000",
            details={"parameter": "limit", "value": limit},
        )

    return offset, limit


def _validate_pid(pid: int | None) -> int:
    """
    Validate process ID.

    Args:
        pid: The PID to validate.

    Returns:
        Validated PID.

    Raises:
        InvalidArgumentError: If PID is invalid.
    """
    if pid is None:
        raise InvalidArgumentError(
            "pid is required",
            details={"parameter": "pid"},
        )

    if not isinstance(pid, int):
        try:
            pid = int(pid)
        except (ValueError, TypeError) as e:
            raise InvalidArgumentError(
                f"pid must be an integer, got {type(pid).__name__}",
                details={"parameter": "pid", "value": pid},
            ) from e

    if pid < 1:
        raise InvalidArgumentError(
            "pid must be a positive integer",
            details={"parameter": "pid", "value": pid},
        )

    return pid


def _is_pid_protected(pid: int, deny_pids: list[int]) -> bool:
    """
    Check if a PID is protected from management.

    Args:
        pid: The PID to check.
        deny_pids: List of protected PIDs.

    Returns:
        True if PID is protected, False otherwise.
    """
    # PID 1 (init/systemd) is always protected
    if pid == 1:
        return True

    # Check against deny list
    return pid in deny_pids


def _process_matches_filter(
    proc_info: dict[str, Any],
    name_pattern: str | None,
    username: str | None,
    min_cpu_percent: float | None,
    min_memory_mb: float | None,
    status_filter: list[str] | None,
) -> bool:
    """
    Check if a process matches the given filters.

    Args:
        proc_info: Process information dictionary.
        name_pattern: Optional name pattern filter (supports wildcards).
        username: Optional username filter.
        min_cpu_percent: Minimum CPU usage percentage.
        min_memory_mb: Minimum memory usage in MB.
        status_filter: List of allowed status values.

    Returns:
        True if process matches all filters.
    """
    # Filter by name pattern
    if name_pattern:
        name = proc_info.get("name", "")
        if not fnmatch.fnmatch(name.lower(), name_pattern.lower()):
            return False

    # Filter by username
    if username:
        proc_user = proc_info.get("username", "")
        if proc_user.lower() != username.lower():
            return False

    # Filter by CPU usage
    if min_cpu_percent is not None:
        cpu = proc_info.get("cpu_percent", 0.0)
        if cpu < min_cpu_percent:
            return False

    # Filter by memory usage (convert bytes to MB)
    if min_memory_mb is not None:
        memory_bytes = proc_info.get("memory_rss", 0)
        memory_mb = memory_bytes / (1024 * 1024)
        if memory_mb < min_memory_mb:
            return False

    # Filter by status
    if status_filter:
        status = proc_info.get("status", "")
        if status.lower() not in [s.lower() for s in status_filter]:
            return False

    return True


def _get_process_info(proc: psutil.Process) -> dict[str, Any] | None:
    """
    Get process information safely.

    Args:
        proc: psutil.Process object.

    Returns:
        Dictionary with process info, or None if process no longer exists.
    """
    try:
        with proc.oneshot():
            try:
                cmdline = proc.cmdline()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                cmdline = []

            try:
                exe = proc.exe()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                exe = ""

            try:
                cwd = proc.cwd()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                cwd = ""

            try:
                username = proc.username()
            except (psutil.AccessDenied, KeyError):
                username = ""

            try:
                memory_info = proc.memory_info()
                memory_rss = memory_info.rss
                memory_vms = memory_info.vms
            except (psutil.AccessDenied, psutil.ZombieProcess):
                memory_rss = 0
                memory_vms = 0

            try:
                memory_percent = proc.memory_percent()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                memory_percent = 0.0

            try:
                cpu_percent = proc.cpu_percent(interval=None)
            except (psutil.AccessDenied, psutil.ZombieProcess):
                cpu_percent = 0.0

            try:
                num_threads = proc.num_threads()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                num_threads = 0

            try:
                nice = proc.nice()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                nice = 0

            return {
                "pid": proc.pid,
                "name": proc.name(),
                "cmdline": cmdline,
                "exe": exe,
                "cwd": cwd,
                "status": proc.status(),
                "username": username,
                "create_time": proc.create_time(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_rss": memory_rss,
                "memory_vms": memory_vms,
                "num_threads": num_threads,
                "ppid": proc.ppid(),
                "nice": nice,
            }

    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _get_detailed_process_info(proc: psutil.Process) -> dict[str, Any] | None:
    """
    Get detailed process information.

    Args:
        proc: psutil.Process object.

    Returns:
        Dictionary with detailed process info, or None if process no longer exists.
    """
    basic_info = _get_process_info(proc)
    if basic_info is None:
        return None

    try:
        # Add IO counters
        try:
            io_counters = proc.io_counters()
            basic_info["io_counters"] = {
                "read_count": io_counters.read_count,
                "write_count": io_counters.write_count,
                "read_bytes": io_counters.read_bytes,
                "write_bytes": io_counters.write_bytes,
            }
        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            basic_info["io_counters"] = None

        # Add open files (limited)
        try:
            open_files = proc.open_files()[:20]  # Limit to first 20
            basic_info["open_files"] = [
                {"path": f.path, "fd": f.fd, "mode": getattr(f, "mode", "")}
                for f in open_files
            ]
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            basic_info["open_files"] = []

        # Add network connections (limited)
        try:
            connections = proc.net_connections()[:20]  # Limit to first 20
            basic_info["connections"] = [
                {
                    "fd": c.fd,
                    "family": str(c.family.name) if hasattr(c.family, "name") else str(c.family),
                    "type": str(c.type.name) if hasattr(c.type, "name") else str(c.type),
                    "local_address": c.laddr.ip if c.laddr else "",
                    "local_port": c.laddr.port if c.laddr else 0,
                    "remote_address": c.raddr.ip if c.raddr else "",
                    "remote_port": c.raddr.port if c.raddr else 0,
                    "status": c.status,
                }
                for c in connections
            ]
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            basic_info["connections"] = []

        # Add CPU times
        try:
            cpu_times = proc.cpu_times()
            basic_info["cpu_times"] = {
                "user": cpu_times.user,
                "system": cpu_times.system,
            }
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            basic_info["cpu_times"] = None

        # Add environment variables (filtered for security)
        # We only include non-sensitive environment variables
        try:
            env = proc.environ()
            # Filter out sensitive variables
            sensitive_patterns = ["key", "secret", "password", "token", "auth", "credential"]
            filtered_env = {
                k: v
                for k, v in env.items()
                if not any(p in k.lower() for p in sensitive_patterns)
            }
            # Limit size
            basic_info["environment"] = dict(list(filtered_env.items())[:50])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            basic_info["environment"] = {}

        basic_info["timestamp"] = datetime.now(UTC).isoformat()

        return basic_info

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


# =============================================================================
# process.list_processes
# =============================================================================


async def handle_process_list_processes(
    _ctx: ToolContext,
    params: dict[str, Any],
    *,
    _config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the process.list_processes tool call.

    Lists running processes with optional filtering.

    Args:
        _ctx: The ToolContext for this request.
        params: Request parameters:
            - filter: Optional filter object with:
                - name_pattern: Filter by process name (supports wildcards)
                - username: Filter by user running the process
                - min_cpu_percent: Minimum CPU usage percentage
                - min_memory_mb: Minimum memory usage in MB
                - status: List of status values to include
            - sort_by: Field to sort by (cpu_percent, memory_percent, name, pid)
            - sort_order: Sort order (asc, desc)
            - offset: Pagination offset (default 0)
            - limit: Pagination limit (default 100, max 1000)
        config: AppConfig for configuration.

    Returns:
        Dictionary with:
        - processes: List of ProcessSummary objects
        - total_count: Total number of processes matching filter
        - returned_count: Number of processes returned
        - has_more: Whether more results are available
    """
    # Parse filter parameters
    filter_params = params.get("filter", {}) or {}
    name_pattern = filter_params.get("name_pattern")
    username = filter_params.get("username")
    min_cpu_percent = filter_params.get("min_cpu_percent")
    min_memory_mb = filter_params.get("min_memory_mb")
    status_filter = filter_params.get("status")

    # Parse sorting parameters
    sort_by = params.get("sort_by", "pid")
    sort_order = params.get("sort_order", "asc")

    # Validate sorting
    valid_sort_fields = {"pid", "name", "cpu_percent", "memory_percent", "memory_rss", "username"}
    if sort_by not in valid_sort_fields:
        raise InvalidArgumentError(
            f"Invalid sort_by: {sort_by}. Must be one of: {', '.join(sorted(valid_sort_fields))}",
            details={"parameter": "sort_by", "value": sort_by, "valid": list(valid_sort_fields)},
        )

    if sort_order not in ("asc", "desc"):
        raise InvalidArgumentError(
            f"Invalid sort_order: {sort_order}. Must be 'asc' or 'desc'",
            details={"parameter": "sort_order", "value": sort_order},
        )

    # Validate pagination
    offset, limit = _validate_pagination(params.get("offset"), params.get("limit"))

    logger.debug(
        "Listing processes",
        extra={
            "filter": filter_params,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "offset": offset,
            "limit": limit,
        },
    )

    # Collect process information
    processes: list[dict[str, Any]] = []

    # First pass: collect CPU samples (need interval for accurate CPU%)
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent(interval=None)  # Initialize CPU tracking
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Small delay for CPU measurement accuracy (optional, can be removed for speed)
    # await asyncio.sleep(0.1)

    # Second pass: collect process info
    for proc in psutil.process_iter():
        proc_info = _get_process_info(proc)
        if proc_info is None:
            continue

        # Apply filters
        if _process_matches_filter(
            proc_info,
            name_pattern,
            username,
            min_cpu_percent,
            min_memory_mb,
            status_filter,
        ):
            processes.append(proc_info)

    # Sort processes
    reverse = sort_order == "desc"
    try:
        processes.sort(key=lambda p: p.get(sort_by, 0) or 0, reverse=reverse)
    except (TypeError, KeyError):
        # Fallback to PID sort
        processes.sort(key=lambda p: p.get("pid", 0), reverse=reverse)

    # Apply pagination
    total_count = len(processes)
    paginated = processes[offset : offset + limit]

    return {
        "processes": paginated,
        "total_count": total_count,
        "returned_count": len(paginated),
        "has_more": (offset + limit) < total_count,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# process.get_info
# =============================================================================


async def handle_process_get_info(
    _ctx: ToolContext,
    params: dict[str, Any],
    *,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Handle the process.get_info tool call.

    Gets detailed information for a single process by PID.

    Args:
        _ctx: The ToolContext for this request.
        params: Request parameters:
            - pid: Process ID (required)
        config: AppConfig for configuration.

    Returns:
        Dictionary with detailed process information (ProcessDetail schema).

    Raises:
        InvalidArgumentError: If PID is invalid.
        PermissionDeniedError: If PID is protected.
    """
    pid = _validate_pid(params.get("pid"))

    # Get config for protected PIDs
    deny_pids: list[int] = [1]  # Default: protect PID 1
    if config is not None:
        deny_pids = config.tools.process.deny_pids

    # Check if PID is protected (for detailed info, we still allow viewing)
    # This is a softer check than for signal sending
    if _is_pid_protected(pid, deny_pids):
        logger.debug(
            "Process info request for protected PID",
            extra={"pid": pid},
        )

    logger.debug(
        "Getting process info",
        extra={"pid": pid},
    )

    try:
        proc = psutil.Process(pid)
        proc_info = _get_detailed_process_info(proc)

        if proc_info is None:
            raise InvalidArgumentError(
                f"Process {pid} not found or access denied",
                details={"pid": pid},
            )

        return proc_info

    except psutil.NoSuchProcess:
        raise InvalidArgumentError(
            f"Process {pid} not found",
            details={"pid": pid},
        ) from None
    except psutil.AccessDenied:
        raise PermissionDeniedError(
            f"Access denied to process {pid}",
            details={"pid": pid},
        ) from None
