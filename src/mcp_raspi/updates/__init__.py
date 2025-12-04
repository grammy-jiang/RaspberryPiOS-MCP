"""
Self-update mechanism for the Raspberry Pi MCP Server.

This package implements the complete self-update functionality:
- Version management and version.json tracking
- Update backend abstraction
- PythonPackageBackend for uv/pip-based updates
- Atomic directory and symlink operations
- State machine for orchestrating updates
- Health checks for verifying updates
- Rollback capability for failed updates
- Systemd service restart integration

Design follows Doc 10 specifications.
"""

from mcp_raspi.updates.backends import PreparedUpdate, UpdateBackend
from mcp_raspi.updates.health_check import HealthChecker, HealthCheckResult
from mcp_raspi.updates.operations import (
    atomic_symlink_switch,
    ensure_directory,
    safe_remove_directory,
)
from mcp_raspi.updates.python_backend import PythonPackageBackend
from mcp_raspi.updates.rollback import RollbackManager, perform_rollback
from mcp_raspi.updates.state_machine import (
    UpdateState,
    UpdateStateData,
    UpdateStateMachine,
)
from mcp_raspi.updates.systemd_restart import (
    ServiceManager,
    graceful_restart_for_update,
    restart_service,
)
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
    # State machine
    "UpdateStateMachine",
    "UpdateState",
    "UpdateStateData",
    # Health checks
    "HealthChecker",
    "HealthCheckResult",
    # Rollback
    "RollbackManager",
    "perform_rollback",
    # Systemd
    "ServiceManager",
    "restart_service",
    "graceful_restart_for_update",
]
