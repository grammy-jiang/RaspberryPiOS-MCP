"""
Self-update mechanism foundation for the Raspberry Pi MCP Server.

This package implements the foundation for self-update functionality:
- Version management and version.json tracking
- Update backend abstraction
- PythonPackageBackend for uv/pip-based updates
- Atomic directory and symlink operations

Design follows Doc 10 §3-4 specifications.
"""

from mcp_raspi.updates.backends import PreparedUpdate, UpdateBackend
from mcp_raspi.updates.operations import (
    atomic_symlink_switch,
    ensure_directory,
    safe_remove_directory,
)
from mcp_raspi.updates.python_backend import PythonPackageBackend
from mcp_raspi.updates.version import (
    VersionHistory,
    VersionInfo,
    VersionManager,
    parse_semantic_version,
)

__all__ = [
    # Version management
    "VersionManager",
    "VersionInfo",
    "VersionHistory",
    "parse_semantic_version",
    # Backends
    "UpdateBackend",
    "PreparedUpdate",
    "PythonPackageBackend",
    # Operations
    "atomic_symlink_switch",
    "ensure_directory",
    "safe_remove_directory",
]
