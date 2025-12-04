"""
Tests for service handlers in the privileged agent (ops layer).

This test module validates:
- Service handlers parse and validate parameters correctly
- Service handlers handle errors appropriately
- Service whitelist functionality works at the handler level
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mcp_raspi.ipc.protocol import IPCRequest
from mcp_raspi.service_utils import is_service_allowed
from mcp_raspi_ops.handlers.service import (
    _parse_service_status_output,
    handle_service_control_service,
    handle_service_get_status,
    handle_service_list_services,
    handle_service_set_enabled,
    register_service_handlers,
)
from mcp_raspi_ops.handlers_core import HandlerError, HandlerRegistry

# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestWhitelistValidation:
    """Tests for service whitelist validation at handler level."""

    def test_exact_match(self) -> None:
        """Test exact service name match."""
        assert is_service_allowed("nginx", ["nginx", "docker"])
        assert is_service_allowed("nginx.service", ["nginx", "docker"])

    def test_wildcard_match(self) -> None:
        """Test wildcard pattern matching."""
        assert is_service_allowed("mcp-raspi-server", ["mcp-raspi-*"])
        assert not is_service_allowed("nginx", ["mcp-raspi-*"])

    def test_empty_whitelist(self) -> None:
        """Test empty whitelist denies all."""
        assert not is_service_allowed("nginx", [])


class TestStatusParsing:
    """Tests for systemctl status output parsing."""

    def test_parse_active_running(self) -> None:
        """Test parsing active running status."""
        output = """
● nginx.service - A high performance web server
     Loaded: loaded (/lib/systemd/system/nginx.service; enabled; vendor preset: enabled)
     Active: active (running) since Mon 2024-01-01 12:00:00 UTC; 1h ago
   Main PID: 1234 (nginx)
      Tasks: 2 (limit: 4915)
     Memory: 12.3M
"""
        result = _parse_service_status_output(output)
        assert result["loaded"] is True
        assert result["status"] == "active"
        assert result["sub_status"] == "running"
        assert result["pid"] == 1234
        assert "memory_bytes" in result

    def test_parse_inactive_dead(self) -> None:
        """Test parsing inactive dead status."""
        output = """
● nginx.service - A high performance web server
     Loaded: loaded (/lib/systemd/system/nginx.service; disabled; vendor preset: enabled)
     Active: inactive (dead) since Mon 2024-01-01 12:00:00 UTC; 1h ago
"""
        result = _parse_service_status_output(output)
        assert result["loaded"] is True
        assert result["status"] == "inactive"
        assert result["sub_status"] == "dead"

    def test_parse_failed(self) -> None:
        """Test parsing failed status."""
        output = """
● nginx.service - A high performance web server
     Loaded: loaded (/lib/systemd/system/nginx.service; enabled; vendor preset: enabled)
     Active: failed since Mon 2024-01-01 12:00:00 UTC; 1h ago
"""
        result = _parse_service_status_output(output)
        assert result["status"] == "failed"
        assert result["sub_status"] == "failed"

    def test_parse_memory_formats(self) -> None:
        """Test parsing different memory formats."""
        # Test KB
        result = _parse_service_status_output("Memory: 512K")
        assert result["memory_bytes"] == 512 * 1024

        # Test MB
        result = _parse_service_status_output("Memory: 12.3M")
        assert result["memory_bytes"] == int(12.3 * 1024 * 1024)

        # Test GB
        result = _parse_service_status_output("Memory: 1.5G")
        assert result["memory_bytes"] == int(1.5 * 1024 * 1024 * 1024)


# =============================================================================
# Tests for Handler Registration
# =============================================================================


class TestHandlerRegistration:
    """Tests for handler registration."""

    def test_register_handlers(self) -> None:
        """Test handlers are registered correctly."""
        registry = HandlerRegistry()
        register_service_handlers(registry)

        assert registry.has_handler("service.list_services")
        assert registry.has_handler("service.get_status")
        assert registry.has_handler("service.control_service")
        assert registry.has_handler("service.set_enabled")


# =============================================================================
# Tests for Handler Parameter Validation
# =============================================================================


class TestHandlerValidation:
    """Tests for handler parameter validation."""

    @pytest.mark.asyncio
    async def test_get_status_requires_service_name(self) -> None:
        """Test get_status requires service_name parameter."""
        request = IPCRequest(id="test-1", operation="service.get_status", params={})

        with pytest.raises(HandlerError) as exc_info:
            await handle_service_get_status(request)
        assert "required" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_control_service_requires_service_name(self) -> None:
        """Test control_service requires service_name parameter."""
        request = IPCRequest(
            id="test-2",
            operation="service.control_service",
            params={"action": "restart"},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_service_control_service(request)
        assert "required" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_control_service_requires_action(self) -> None:
        """Test control_service requires action parameter."""
        request = IPCRequest(
            id="test-3",
            operation="service.control_service",
            params={"service_name": "nginx"},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_service_control_service(request)
        assert "Invalid action" in exc_info.value.message or "required" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_control_service_validates_action(self) -> None:
        """Test control_service validates action value."""
        request = IPCRequest(
            id="test-4",
            operation="service.control_service",
            params={"service_name": "nginx", "action": "kill"},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_service_control_service(request)
        assert "Invalid action" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_set_enabled_requires_service_name(self) -> None:
        """Test set_enabled requires service_name parameter."""
        request = IPCRequest(
            id="test-5",
            operation="service.set_enabled",
            params={"enabled": True},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_service_set_enabled(request)
        assert "required" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_set_enabled_requires_enabled(self) -> None:
        """Test set_enabled requires enabled parameter."""
        request = IPCRequest(
            id="test-6",
            operation="service.set_enabled",
            params={"service_name": "nginx"},
        )

        with pytest.raises(HandlerError) as exc_info:
            await handle_service_set_enabled(request)
        assert "required" in exc_info.value.message


# =============================================================================
# Tests for Handler with Mocked systemctl
# =============================================================================


class TestHandlersWithMock:
    """Tests for handlers with mocked systemctl commands."""

    @pytest.mark.asyncio
    async def test_list_services_parses_output(self) -> None:
        """Test list_services parses systemctl output correctly."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """
UNIT                     LOAD   ACTIVE   SUB     DESCRIPTION
nginx.service            loaded active   running nginx - high performance web server
docker.service           loaded active   running Docker Application Container Engine
sshd.service             loaded active   running OpenSSH server daemon
"""
        with patch(
            "mcp_raspi_ops.handlers.service._run_systemctl",
            return_value=mock_result,
        ):
            request = IPCRequest(
                id="test-7",
                operation="service.list_services",
                params={"allowed_services": ["nginx", "docker"]},
            )
            result = await handle_service_list_services(request)

            assert "services" in result
            # Should filter to only whitelisted services
            service_names = [s["name"] for s in result["services"]]
            assert "nginx.service" in service_names
            assert "docker.service" in service_names
            # sshd should be filtered out
            assert "sshd.service" not in service_names

    @pytest.mark.asyncio
    async def test_get_status_returns_status(self) -> None:
        """Test get_status returns parsed status."""
        status_output = MagicMock()
        status_output.returncode = 0
        status_output.stdout = """
● nginx.service - nginx
     Loaded: loaded (/lib/systemd/system/nginx.service; enabled)
     Active: active (running) since Mon 2024-01-01 12:00:00 UTC
   Main PID: 1234 (nginx)
     Memory: 15.0M
"""
        enabled_output = MagicMock()
        enabled_output.returncode = 0
        enabled_output.stdout = "enabled"

        show_output = MagicMock()
        show_output.returncode = 0
        show_output.stdout = """Description=nginx - high performance web server
ExecStart=/usr/sbin/nginx
"""

        def mock_systemctl(args, timeout=30):  # noqa: ARG001
            if args[0] == "status":
                return status_output
            elif args[0] == "is-enabled":
                return enabled_output
            elif args[0] == "show":
                return show_output
            return MagicMock(returncode=0, stdout="")

        with patch(
            "mcp_raspi_ops.handlers.service._run_systemctl",
            side_effect=mock_systemctl,
        ):
            request = IPCRequest(
                id="test-8",
                operation="service.get_status",
                params={"service_name": "nginx"},
            )
            result = await handle_service_get_status(request)

            assert result["name"] == "nginx.service"
            assert result["status"] == "active"
            assert result["sub_status"] == "running"
            assert result["enabled"] is True
            assert result["pid"] == 1234

    @pytest.mark.asyncio
    async def test_control_service_executes_action(self) -> None:
        """Test control_service executes the action."""
        pre_status = MagicMock()
        pre_status.returncode = 0
        pre_status.stdout = "inactive"

        action_result = MagicMock()
        action_result.returncode = 0
        action_result.stdout = ""
        action_result.stderr = ""

        post_status = MagicMock()
        post_status.returncode = 0
        post_status.stdout = "active"

        call_count = [0]

        def mock_systemctl(args, timeout=30):  # noqa: ARG001
            call_count[0] += 1
            if args[0] == "is-active":
                if call_count[0] <= 1:
                    return pre_status
                return post_status
            return action_result

        with patch(
            "mcp_raspi_ops.handlers.service._run_systemctl",
            side_effect=mock_systemctl,
        ), patch("asyncio.sleep"):
            request = IPCRequest(
                id="test-9",
                operation="service.control_service",
                params={
                    "service_name": "nginx",
                    "action": "start",
                    "caller": {"user_id": "admin", "role": "admin"},
                },
            )
            result = await handle_service_control_service(request)

            assert result["executed"] is True
            assert result["previous_status"] == "inactive"
            assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_set_enabled_executes_enable(self) -> None:
        """Test set_enabled executes enable command."""
        pre_enabled = MagicMock()
        pre_enabled.returncode = 1
        pre_enabled.stdout = "disabled"

        enable_result = MagicMock()
        enable_result.returncode = 0
        enable_result.stdout = ""
        enable_result.stderr = ""

        def mock_systemctl(args, timeout=30):  # noqa: ARG001
            if args[0] == "is-enabled":
                return pre_enabled
            return enable_result

        with patch(
            "mcp_raspi_ops.handlers.service._run_systemctl",
            side_effect=mock_systemctl,
        ):
            request = IPCRequest(
                id="test-10",
                operation="service.set_enabled",
                params={
                    "service_name": "nginx",
                    "enabled": True,
                    "caller": {"user_id": "admin", "role": "admin"},
                },
            )
            result = await handle_service_set_enabled(request)

            assert result["executed"] is True
            assert result["previous_enabled"] is False

    @pytest.mark.asyncio
    async def test_control_service_handles_failure(self) -> None:
        """Test control_service handles systemctl failure."""
        pre_status = MagicMock()
        pre_status.returncode = 0
        pre_status.stdout = "inactive"

        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = ""
        fail_result.stderr = "Failed to start nginx.service: Unit not found"

        def mock_systemctl(args, timeout=30):  # noqa: ARG001
            if args[0] == "is-active":
                return pre_status
            return fail_result

        with patch(
            "mcp_raspi_ops.handlers.service._run_systemctl",
            side_effect=mock_systemctl,
        ):
            request = IPCRequest(
                id="test-11",
                operation="service.control_service",
                params={"service_name": "nginx", "action": "start"},
            )

            with pytest.raises(HandlerError) as exc_info:
                await handle_service_control_service(request)
            assert "Failed" in exc_info.value.message
