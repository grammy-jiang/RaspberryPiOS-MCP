"""
Tests for the routing module (ToolRegistry and @tool_handler decorator).

This test module validates:
- ToolRegistry registration and dispatch
- @tool_handler decorator functionality
- Error handling during dispatch
- Namespace filtering and tool discovery
"""

from __future__ import annotations

from typing import Any

import pytest

from mcp_raspi.context import CallerInfo, ToolContext
from mcp_raspi.errors import InvalidArgumentError, ToolError
from mcp_raspi.routing import ToolRegistry, tool_handler

# =============================================================================
# Helper Functions for Tests
# =============================================================================


async def dummy_handler(ctx: ToolContext, _params: dict[str, Any]) -> dict[str, Any]:
    """A simple test handler."""
    return {"status": "ok", "tool": ctx.tool_name}


async def echo_handler(_ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
    """A handler that echoes parameters."""
    return {"echoed": params}


async def error_handler(_ctx: ToolContext, _params: dict[str, Any]) -> dict[str, Any]:
    """A handler that raises an error."""
    raise InvalidArgumentError(
        message="Test error",
        details={"param": "test"},
    )


async def exception_handler(
    _ctx: ToolContext, _params: dict[str, Any]
) -> dict[str, Any]:
    """A handler that raises a non-ToolError exception."""
    raise RuntimeError("Unexpected error")


# =============================================================================
# Tests for ToolRegistry
# =============================================================================


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_registry_creation(self) -> None:
        """Test creating an empty registry."""
        registry = ToolRegistry()
        assert len(registry) == 0

    def test_register_handler(self) -> None:
        """Test registering a handler."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)

        assert "system.ping" in registry
        assert len(registry) == 1

    def test_register_multiple_handlers(self) -> None:
        """Test registering multiple handlers."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)
        registry.register("system.health", echo_handler)
        registry.register("gpio.read_pin", dummy_handler)

        assert len(registry) == 3
        assert "system.ping" in registry
        assert "system.health" in registry
        assert "gpio.read_pin" in registry

    def test_register_duplicate_raises(self) -> None:
        """Test that registering duplicate tool name raises error."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("system.ping", echo_handler)

    def test_has_tool(self) -> None:
        """Test has_tool method."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)

        assert registry.has_tool("system.ping") is True
        assert registry.has_tool("system.unknown") is False

    def test_get_handler(self) -> None:
        """Test getting a handler by name."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)

        handler = registry.get_handler("system.ping")
        assert handler is dummy_handler

    def test_get_handler_not_found(self) -> None:
        """Test getting a handler that doesn't exist."""
        registry = ToolRegistry()

        handler = registry.get_handler("system.unknown")
        assert handler is None

    def test_list_tools(self) -> None:
        """Test listing all registered tools."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)
        registry.register("gpio.read_pin", dummy_handler)

        tools = registry.list_tools()

        assert sorted(tools) == ["gpio.read_pin", "system.ping"]

    def test_list_tools_by_namespace(self) -> None:
        """Test listing tools filtered by namespace."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)
        registry.register("system.health", dummy_handler)
        registry.register("gpio.read_pin", dummy_handler)

        system_tools = registry.list_tools(namespace="system")

        assert sorted(system_tools) == ["system.health", "system.ping"]

    def test_list_namespaces(self) -> None:
        """Test listing all namespaces."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)
        registry.register("gpio.read_pin", dummy_handler)
        registry.register("metrics.health", dummy_handler)

        namespaces = registry.list_namespaces()

        assert sorted(namespaces) == ["gpio", "metrics", "system"]

    @pytest.mark.asyncio
    async def test_invoke_success(self) -> None:
        """Test invoking a handler successfully."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)

        ctx = ToolContext(
            tool_name="system.ping",
            caller=CallerInfo(),
            request_id="req-1",
        )

        result = await registry.invoke("system.ping", ctx, {})

        assert result["status"] == "ok"
        assert result["tool"] == "system.ping"

    @pytest.mark.asyncio
    async def test_invoke_with_params(self) -> None:
        """Test invoking a handler with parameters."""
        registry = ToolRegistry()
        registry.register("system.echo", echo_handler)

        ctx = ToolContext(
            tool_name="system.echo",
            caller=CallerInfo(),
            request_id="req-2",
        )

        result = await registry.invoke("system.echo", ctx, {"message": "hello"})

        assert result["echoed"] == {"message": "hello"}

    @pytest.mark.asyncio
    async def test_invoke_not_found(self) -> None:
        """Test invoking a handler that doesn't exist."""
        registry = ToolRegistry()

        ctx = ToolContext(
            tool_name="system.unknown",
            caller=CallerInfo(),
            request_id="req-3",
        )

        with pytest.raises(ToolError) as exc_info:
            await registry.invoke("system.unknown", ctx, {})

        assert exc_info.value.error_code == "not_found"

    @pytest.mark.asyncio
    async def test_invoke_handler_raises_tool_error(self) -> None:
        """Test that ToolError from handler propagates."""
        registry = ToolRegistry()
        registry.register("system.error", error_handler)

        ctx = ToolContext(
            tool_name="system.error",
            caller=CallerInfo(),
            request_id="req-4",
        )

        with pytest.raises(InvalidArgumentError) as exc_info:
            await registry.invoke("system.error", ctx, {})

        assert exc_info.value.error_code == "invalid_argument"
        assert exc_info.value.details["param"] == "test"

    @pytest.mark.asyncio
    async def test_invoke_handler_raises_exception(self) -> None:
        """Test that non-ToolError exceptions are wrapped."""
        registry = ToolRegistry()
        registry.register("system.crash", exception_handler)

        ctx = ToolContext(
            tool_name="system.crash",
            caller=CallerInfo(),
            request_id="req-5",
        )

        with pytest.raises(ToolError) as exc_info:
            await registry.invoke("system.crash", ctx, {})

        assert exc_info.value.error_code == "internal"
        assert "Unexpected error" in exc_info.value.message

    def test_registry_contains(self) -> None:
        """Test __contains__ operator."""
        registry = ToolRegistry()
        registry.register("system.ping", dummy_handler)

        assert "system.ping" in registry
        assert "system.pong" not in registry

    def test_registry_len(self) -> None:
        """Test __len__ operator."""
        registry = ToolRegistry()

        assert len(registry) == 0

        registry.register("system.ping", dummy_handler)
        assert len(registry) == 1

        registry.register("gpio.read", dummy_handler)
        assert len(registry) == 2


# =============================================================================
# Tests for @tool_handler Decorator
# =============================================================================


class TestToolHandlerDecorator:
    """Tests for the @tool_handler decorator."""

    def test_decorator_registers_handler(self) -> None:
        """Test that decorator registers the handler."""
        registry = ToolRegistry()

        @tool_handler("test.decorated", registry=registry)
        async def decorated_handler(
            _ctx: ToolContext, _params: dict[str, Any]
        ) -> dict[str, Any]:
            return {"decorated": True}

        assert "test.decorated" in registry

    def test_decorator_preserves_function(self) -> None:
        """Test that decorator preserves function identity."""
        registry = ToolRegistry()

        @tool_handler("test.identity", registry=registry)
        async def identity_handler(
            _ctx: ToolContext, _params: dict[str, Any]
        ) -> dict[str, Any]:
            return {}

        assert identity_handler.__name__ == "identity_handler"

    @pytest.mark.asyncio
    async def test_decorated_handler_callable(self) -> None:
        """Test that decorated handler can be called via registry."""
        registry = ToolRegistry()

        @tool_handler("test.callable", registry=registry)
        async def callable_handler(
            _ctx: ToolContext, _params: dict[str, Any]
        ) -> dict[str, Any]:
            return {"answer": 42}

        ctx = ToolContext(
            tool_name="test.callable",
            caller=CallerInfo(),
            request_id="req-1",
        )

        result = await registry.invoke("test.callable", ctx, {})
        assert result["answer"] == 42

    def test_decorator_with_docstring(self) -> None:
        """Test that decorator preserves docstring."""
        registry = ToolRegistry()

        @tool_handler("test.documented", registry=registry)
        async def documented_handler(
            _ctx: ToolContext, _params: dict[str, Any]
        ) -> dict[str, Any]:
            """This is a documented handler."""
            return {}

        assert documented_handler.__doc__ == "This is a documented handler."

    def test_decorator_multiple_registrations(self) -> None:
        """Test registering multiple handlers via decorator."""
        registry = ToolRegistry()

        @tool_handler("ns1.tool1", registry=registry)
        async def handler1(
            _ctx: ToolContext, _params: dict[str, Any]
        ) -> dict[str, Any]:
            return {"handler": 1}

        @tool_handler("ns2.tool2", registry=registry)
        async def handler2(
            _ctx: ToolContext, _params: dict[str, Any]
        ) -> dict[str, Any]:
            return {"handler": 2}

        assert "ns1.tool1" in registry
        assert "ns2.tool2" in registry
        assert len(registry) == 2


# =============================================================================
# Tests for Default Global Registry
# =============================================================================


class TestDefaultRegistry:
    """Tests for default global registry behavior."""

    def test_get_default_registry(self) -> None:
        """Test getting the default registry."""
        from mcp_raspi.routing import get_default_registry

        registry = get_default_registry()

        assert registry is not None
        assert isinstance(registry, ToolRegistry)

    def test_default_registry_is_singleton(self) -> None:
        """Test that default registry is a singleton."""
        from mcp_raspi.routing import get_default_registry

        registry1 = get_default_registry()
        registry2 = get_default_registry()

        assert registry1 is registry2
