"""
Command handlers for the Privileged Agent.

This module implements command handlers for the privileged operations agent.
Each handler executes a specific privileged operation and returns results.

Design follows Doc 02 §6.4 (Operation Set).

Handler Registration:
- Handlers are registered by operation name (e.g., "ping", "gpio.write")
- Each handler receives the full IPCRequest and returns a dict result
- Handlers should raise exceptions for errors, which are caught and
  converted to IPC error responses
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.logging import get_logger

logger = get_logger(__name__)

# Handler type: takes request, returns result dict
HandlerFunc = Callable[[IPCRequest], Awaitable[dict[str, Any]]]


class HandlerError(Exception):
    """
    Exception raised by handlers for operational errors.

    Attributes:
        code: Error code string.
        message: Human-readable error message.
        details: Optional structured error details.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a handler error."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class HandlerRegistry:
    """
    Registry for IPC command handlers.

    This registry maps operation names to handler functions and
    provides dispatch capabilities.

    Example:
        >>> registry = HandlerRegistry()
        >>> registry.register("ping", handle_ping)
        >>> result = await registry.dispatch(request)
    """

    def __init__(self) -> None:
        """Initialize the handler registry."""
        self._handlers: dict[str, HandlerFunc] = {}

    def register(self, operation: str, handler: HandlerFunc) -> None:
        """
        Register a handler for an operation.

        Args:
            operation: Operation name (e.g., "ping", "gpio.write").
            handler: Async handler function.
        """
        if operation in self._handlers:
            logger.warning(
                "Overwriting existing handler",
                extra={"operation": operation},
            )
        self._handlers[operation] = handler
        logger.debug("Handler registered", extra={"operation": operation})

    def unregister(self, operation: str) -> None:
        """
        Unregister a handler for an operation.

        Args:
            operation: Operation name to unregister.
        """
        self._handlers.pop(operation, None)

    def has_handler(self, operation: str) -> bool:
        """
        Check if a handler is registered for an operation.

        Args:
            operation: Operation name to check.

        Returns:
            True if handler exists, False otherwise.
        """
        return operation in self._handlers

    def get_operations(self) -> list[str]:
        """
        Get list of registered operations.

        Returns:
            List of operation names.
        """
        return list(self._handlers.keys())

    async def dispatch(self, request: IPCRequest) -> dict[str, Any]:
        """
        Dispatch a request to the appropriate handler.

        Args:
            request: The IPC request to dispatch.

        Returns:
            Handler result dictionary.

        Raises:
            HandlerError: If operation not found or handler fails.
        """
        operation = request.operation

        if operation not in self._handlers:
            raise HandlerError(
                code="unknown_operation",
                message=f"Unknown operation: {operation}",
                details={"operation": operation, "available": self.get_operations()},
            )

        handler = self._handlers[operation]

        logger.info(
            "Dispatching IPC request",
            extra={
                "operation": operation,
                "request_id": request.id,
            },
        )

        try:
            result = await handler(request)
            return result

        except HandlerError:
            # Re-raise handler errors as-is
            raise

        except Exception as e:
            # Wrap unexpected exceptions
            logger.exception(
                "Handler error",
                extra={
                    "operation": operation,
                    "request_id": request.id,
                    "error": str(e),
                },
            )
            raise HandlerError(
                code="internal",
                message=f"Handler failed: {type(e).__name__}: {e}",
                details={"operation": operation},
            ) from e


# =============================================================================
# Built-in Handlers
# =============================================================================


async def handle_ping(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the ping command.

    This is a simple health check command that returns a pong response.

    Args:
        request: The IPC request.

    Returns:
        Dict with pong=True.
    """
    logger.debug("Ping request received", extra={"request_id": request.id})
    return {"pong": True}


async def handle_echo(request: IPCRequest) -> dict[str, Any]:
    """
    Handle the echo command.

    This command echoes back the provided message.

    Args:
        request: The IPC request containing "message" parameter.

    Returns:
        Dict with the echoed message.
    """
    message = request.params.get("message", "")
    return {"echo": message}


async def handle_get_info(_request: IPCRequest) -> dict[str, Any]:
    """
    Handle the get_info command.

    Returns information about the privileged agent.

    Args:
        request: The IPC request.

    Returns:
        Dict with agent information.
    """
    from mcp_raspi_ops import __version__

    return {
        "name": "raspi-ops-agent",
        "version": __version__,
        "status": "running",
    }


def get_default_registry() -> HandlerRegistry:
    """
    Get a registry with default handlers registered.

    Returns:
        HandlerRegistry with ping, echo, and get_info handlers.
    """
    registry = HandlerRegistry()
    registry.register("ping", handle_ping)
    registry.register("echo", handle_echo)
    registry.register("get_info", handle_get_info)
    return registry
