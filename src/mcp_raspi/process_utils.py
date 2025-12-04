"""
Shared process utilities for both MCP server and privileged agent.

This module provides common functions for process operations that need
to be shared between the tools layer and the ops handlers layer.
"""

from __future__ import annotations

import fnmatch
from typing import Any


def process_matches_filter(
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
