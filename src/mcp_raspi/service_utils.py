"""
Shared service utilities for both MCP server and privileged agent.

This module provides common functions for service operations that need
to be shared between the tools layer and the ops handlers layer.
"""

from __future__ import annotations

import fnmatch


def is_service_allowed(
    service_name: str,
    allowed_services: list[str],
) -> bool:
    """
    Check if a service is allowed by the whitelist.

    Args:
        service_name: The service name to check.
        allowed_services: List of allowed service names/patterns.

    Returns:
        True if service is allowed, False otherwise.
    """
    if not allowed_services:
        # If no whitelist configured, deny all service operations
        return False

    # Normalize service name (add .service suffix if missing)
    if not service_name.endswith(".service"):
        normalized_name = f"{service_name}.service"
    else:
        normalized_name = service_name

    # Check against whitelist patterns
    for pattern in allowed_services:
        # Normalize pattern as well
        if not pattern.endswith(".service") and not pattern.endswith("*"):
            pattern = f"{pattern}.service"

        # Use fnmatch for pattern matching (supports * and ?)
        if fnmatch.fnmatch(normalized_name, pattern):
            return True
        # Also check without .service suffix for flexibility
        if fnmatch.fnmatch(service_name, pattern):
            return True

    return False
