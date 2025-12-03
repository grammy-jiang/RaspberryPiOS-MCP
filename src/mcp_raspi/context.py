"""
Tool context management for the Raspberry Pi MCP Server.

This module defines the ToolContext dataclass that carries the context of a
single MCP tool call, including caller identity, request ID, and timestamps.

Design follows Doc 02 §2.5 (Core Python Interfaces).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_raspi.protocol import JSONRPCRequest


@dataclass
class CallerInfo:
    """
    Represents the identity and authorization context of a caller.

    Attributes:
        user_id: User identifier from authentication (e.g., email, sub claim).
        role: Assigned role after role mapping (e.g., viewer, operator, admin).
        ip_address: Client IP address for audit logging.
        groups: External groups from authentication provider.
    """

    user_id: str | None = None
    role: str = "anonymous"
    ip_address: str | None = None
    groups: list[str] = field(default_factory=list)

    @property
    def is_authenticated(self) -> bool:
        """Check if the caller is authenticated (has a user_id)."""
        return self.user_id is not None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert CallerInfo to a dictionary for serialization.

        Returns:
            Dictionary with caller information.
        """
        return {
            "user_id": self.user_id,
            "role": self.role,
            "ip_address": self.ip_address,
            "groups": self.groups,
        }


@dataclass
class ToolContext:
    """
    Encapsulates the context of a single MCP tool call.

    This context is passed to every tool handler and contains all metadata
    needed for authorization, logging, and auditing.

    Attributes:
        tool_name: Full tool name (e.g., "system.get_basic_info").
        caller: CallerInfo with identity and authorization context.
        request_id: Unique request identifier from JSON-RPC request.
        timestamp: When the request was received (UTC).
        metadata: Additional context (e.g., parsed headers, request metadata).
    """

    tool_name: str
    caller: CallerInfo
    request_id: str | int | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def namespace(self) -> str:
        """
        Extract the namespace from the tool name.

        Returns:
            The namespace part (e.g., "system" from "system.get_basic_info").
        """
        parts = self.tool_name.split(".", 1)
        return parts[0]

    @property
    def operation(self) -> str:
        """
        Extract the operation from the tool name.

        Returns:
            The operation part (e.g., "get_basic_info" from "system.get_basic_info").
        """
        parts = self.tool_name.split(".", 1)
        return parts[1] if len(parts) > 1 else parts[0]

    def to_dict(self) -> dict[str, Any]:
        """
        Convert ToolContext to a dictionary for logging/serialization.

        Returns:
            Dictionary with context information.
        """
        return {
            "tool_name": self.tool_name,
            "caller": self.caller.to_dict(),
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_request(
        cls,
        request: JSONRPCRequest,
        caller: CallerInfo | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolContext:
        """
        Create a ToolContext from a parsed JSON-RPC request.

        Args:
            request: The parsed JSONRPCRequest.
            caller: Optional CallerInfo (defaults to anonymous).
            metadata: Optional additional metadata.

        Returns:
            A ToolContext instance for the request.

        Example:
            >>> from mcp_raspi.protocol import parse_request
            >>> req = parse_request('{"jsonrpc":"2.0","id":"1","method":"system.info","params":{}}')
            >>> ctx = ToolContext.from_request(req, caller=CallerInfo(user_id="admin"))
        """
        return cls(
            tool_name=request.method,
            caller=caller or CallerInfo(),
            request_id=request.id,
            timestamp=datetime.now(UTC),
            metadata=metadata or {},
        )
