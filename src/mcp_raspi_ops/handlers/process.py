"""
Process operation handlers for the Privileged Agent.

This module implements handlers for process operations:
- process.list_processes: List processes with filtering
- process.get_info: Get detailed process information

These handlers run with elevated privileges and use psutil for process access.

Design follows Doc 07 §4.1 (Process Management).
"""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from typing import Any

import psutil

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

logger = get_logger(__name__)


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
            open_files = proc.open_files()[:20]
            basic_info["open_files"] = [
                {"path": f.path, "fd": f.fd, "mode": getattr(f, "mode", "")}
                for f in open_files
            ]
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            basic_info["open_files"] = []

        # Add network connections (limited)
        try:
            connections = proc.net_connections()[:20]
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
        try:
            env = proc.environ()
            sensitive_patterns = ["key", "secret", "password", "token", "auth", "credential"]
            filtered_env = {
                k: v
                for k, v in env.items()
                if not any(p in k.lower() for p in sensitive_patterns)
            }
            basic_info["environment"] = dict(list(filtered_env.items())[:50])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            basic_info["environment"] = {}

        basic_info["timestamp"] = datetime.now(UTC).isoformat()

        return basic_info

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


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
    if name_pattern:
        name = proc_info.get("name", "")
        if not fnmatch.fnmatch(name.lower(), name_pattern.lower()):
            return False

    if username:
        proc_user = proc_info.get("username", "")
        if proc_user.lower() != username.lower():
            return False

    if min_cpu_percent is not None:
        cpu = proc_info.get("cpu_percent", 0.0)
        if cpu < min_cpu_percent:
            return False

    if min_memory_mb is not None:
        memory_bytes = proc_info.get("memory_rss", 0)
        memory_mb = memory_bytes / (1024 * 1024)
        if memory_mb < min_memory_mb:
            return False

    if status_filter:
        status = proc_info.get("status", "")
        if status.lower() not in [s.lower() for s in status_filter]:
            return False

    return True


async def handle_process_list_processes(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the process.list_processes operation.

    Lists running processes with optional filtering.

    Args:
        request: IPC request with params:
            - filter: Optional filter object with:
                - name_pattern: Filter by process name
                - username: Filter by user
                - min_cpu_percent: Minimum CPU usage
                - min_memory_mb: Minimum memory usage
                - status: List of status values
            - sort_by: Field to sort by
            - sort_order: Sort order (asc, desc)

    Returns:
        Dict with list of processes.

    Raises:
        HandlerError: If listing fails.
    """
    params = request.params
    filter_params = params.get("filter", {}) or {}
    name_pattern = filter_params.get("name_pattern")
    username = filter_params.get("username")
    min_cpu_percent = filter_params.get("min_cpu_percent")
    min_memory_mb = filter_params.get("min_memory_mb")
    status_filter = filter_params.get("status")

    sort_by = params.get("sort_by", "pid")
    sort_order = params.get("sort_order", "asc")

    logger.info(
        "Listing processes",
        extra={
            "request_id": request.id,
            "filter": filter_params,
            "sort_by": sort_by,
        },
    )

    # Collect process information
    processes: list[dict[str, Any]] = []

    # First pass: initialize CPU tracking
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Second pass: collect process info
    for proc in psutil.process_iter():
        proc_info = _get_process_info(proc)
        if proc_info is None:
            continue

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
        processes.sort(key=lambda p: p.get("pid", 0), reverse=reverse)

    return {
        "processes": processes,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def handle_process_get_info(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the process.get_info operation.

    Gets detailed information for a single process.

    Args:
        request: IPC request with params:
            - pid: Process ID

    Returns:
        Dict with detailed process information.

    Raises:
        HandlerError: If process not found or access denied.
    """
    params = request.params
    pid = params.get("pid")

    if pid is None:
        raise HandlerError(
            code="invalid_argument",
            message="pid is required",
            details={"parameter": "pid"},
        )

    try:
        pid = int(pid)
    except (ValueError, TypeError) as e:
        raise HandlerError(
            code="invalid_argument",
            message=f"pid must be an integer, got {type(pid).__name__}",
            details={"parameter": "pid", "value": pid},
        ) from e

    logger.info(
        "Getting process info",
        extra={"request_id": request.id, "pid": pid},
    )

    try:
        proc = psutil.Process(pid)
        proc_info = _get_detailed_process_info(proc)

        if proc_info is None:
            raise HandlerError(
                code="not_found",
                message=f"Process {pid} not found or access denied",
                details={"pid": pid},
            )

        return proc_info

    except psutil.NoSuchProcess as e:
        raise HandlerError(
            code="not_found",
            message=f"Process {pid} not found",
            details={"pid": pid},
        ) from e

    except psutil.AccessDenied as e:
        raise HandlerError(
            code="permission_denied",
            message=f"Access denied to process {pid}",
            details={"pid": pid},
        ) from e


def register_process_handlers(registry: HandlerRegistry) -> None:
    """
    Register process handlers with the handler registry.

    Args:
        registry: The handler registry to register with.
    """
    registry.register("process.list_processes", handle_process_list_processes)
    registry.register("process.get_info", handle_process_get_info)
    logger.debug("Registered process handlers")
