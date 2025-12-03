"""
Tool routing and registration for the Raspberry Pi MCP Server.

This module provides:
- ToolRegistry: A registry for mapping tool names to handler functions
- @tool_handler: A decorator for registering tool handlers
- Handler dispatch with error handling

Design follows Doc 02 §2.5 (Core Python Interfaces) and Doc 05 §2.5 (Python Tool Handler Interface).
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from mcp_raspi.errors import InternalError, ToolError

if TYPE_CHECKING:
    from mcp_raspi.context import ToolContext

# Type alias for tool handlers (from Doc 05 §2.5.1)
ToolHandler = Callable[["ToolContext", dict[str, Any]], Awaitable[Any]]

# Default global registry (singleton)
_default_registry: ToolRegistry | None = None


class ToolRegistry:
    """
    Registry for mapping tool names to handler functions.

    The registry stores handler functions keyed by their tool names
    (in "namespace.operation" format) and provides methods for registration,
    lookup, and invocation.

    Example:
        >>> registry = ToolRegistry()
        >>> registry.register("system.get_basic_info", my_handler)
        >>> result = await registry.invoke("system.get_basic_info", ctx, {})
    """

    def __init__(self) -> None:
        """Initialize an empty tool registry."""
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        """
        Register a tool handler with the given name.

        Args:
            name: Tool name in "namespace.operation" format.
            handler: Async function that handles the tool call.

        Raises:
            ValueError: If a handler is already registered for the name.

        Example:
            >>> registry.register("system.ping", ping_handler)
        """
        if name in self._handlers:
            raise ValueError(f"Tool '{name}' is already registered")
        self._handlers[name] = handler

    def has_tool(self, name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            name: Tool name to check.

        Returns:
            True if the tool is registered, False otherwise.
        """
        return name in self._handlers

    def get_handler(self, name: str) -> ToolHandler | None:
        """
        Get the handler for a tool by name.

        Args:
            name: Tool name to look up.

        Returns:
            The handler function, or None if not found.
        """
        return self._handlers.get(name)

    def list_tools(self, namespace: str | None = None) -> list[str]:
        """
        List all registered tools, optionally filtered by namespace.

        Args:
            namespace: Optional namespace to filter by.

        Returns:
            List of registered tool names.
        """
        if namespace is None:
            return list(self._handlers.keys())

        return [
            name
            for name in self._handlers
            if name.startswith(f"{namespace}.")
        ]

    def list_namespaces(self) -> list[str]:
        """
        List all unique namespaces from registered tools.

        Returns:
            List of namespace names.
        """
        namespaces: set[str] = set()
        for name in self._handlers:
            parts = name.split(".", 1)
            namespaces.add(parts[0])
        return list(namespaces)

    async def invoke(
        self,
        name: str,
        ctx: ToolContext,
        params: dict[str, Any],
    ) -> Any:
        """
        Invoke a tool handler by name.

        Args:
            name: Tool name to invoke.
            ctx: ToolContext for the request.
            params: Parameters to pass to the handler.

        Returns:
            The handler's return value.

        Raises:
            ToolError: If the tool is not found or handler raises ToolError.

        Example:
            >>> result = await registry.invoke("system.ping", ctx, {"echo": "hello"})
        """
        handler = self.get_handler(name)
        if handler is None:
            raise ToolError(
                error_code="not_found",
                message=f"Tool '{name}' is not registered",
                details={"tool": name},
            )

        try:
            return await handler(ctx, params)
        except ToolError:
            # Re-raise ToolError as-is
            raise
        except Exception as e:
            # Wrap unexpected exceptions in InternalError
            raise InternalError(
                message=f"Internal error in tool '{name}': {e!s}",
                details={"tool": name, "exception_type": type(e).__name__},
            ) from e

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered (for 'in' operator)."""
        return name in self._handlers

    def __len__(self) -> int:
        """Return the number of registered tools."""
        return len(self._handlers)


def get_default_registry() -> ToolRegistry:
    """
    Get the default global tool registry.

    This registry is a singleton that can be used for registering tools
    at module import time using the @tool_handler decorator.

    Returns:
        The default ToolRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def tool_handler(
    name: str,
    *,
    registry: ToolRegistry | None = None,
) -> Callable[[ToolHandler], ToolHandler]:
    """
    Decorator for registering a function as a tool handler.

    Args:
        name: Tool name in "namespace.operation" format.
        registry: Optional ToolRegistry (defaults to the global registry).

    Returns:
        Decorator function that registers the handler.

    Example:
        >>> @tool_handler("system.get_basic_info")
        ... async def handle_get_basic_info(ctx: ToolContext, params: dict) -> dict:
        ...     return {"hostname": "raspberrypi", "status": "ok"}

        >>> # With custom registry
        >>> @tool_handler("gpio.read_pin", registry=my_registry)
        ... async def handle_read_pin(ctx: ToolContext, params: dict) -> dict:
        ...     return {"pin": params["pin"], "value": 1}
    """

    def decorator(handler: ToolHandler) -> ToolHandler:
        target_registry = registry if registry is not None else get_default_registry()
        target_registry.register(name, handler)
        return handler
    return decorator
