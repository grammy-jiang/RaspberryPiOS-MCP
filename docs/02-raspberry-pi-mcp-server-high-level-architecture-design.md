# 02. Raspberry Pi MCP Server – High‑Level Architecture Design

## 1. Document Purpose

- Describe the overall architecture and key components of the Raspberry Pi MCP Server.  
- Explain the responsibilities, interactions, and main data flows between modules.  
- Provide architectural constraints and guidance for the module design documents (06–10).

## 2. Architectural Overview

### 2.1 Context

The system operates in the following environment:

- A Raspberry Pi device running **Raspberry Pi OS**.  
- The MCP server runs on the same physical machine as the OS it manages.  
- External access:  
  - Local network (LAN/Wi‑Fi), typically restricted to the local network.  
  - Public exposure through Cloudflare Tunnel + Cloudflare Access, with OAuth/OIDC in front.  
- Primary clients:  
  - AI models such as ChatGPT (via MCP tools).  
  - Other MCP‑capable services or automation scripts.

### 2.2 Implementation Language & Dependencies

To simplify implementation and maintenance on Raspberry Pi OS, the primary implementation language is **Python 3.11+**, with the following key dependencies (these can be refined during implementation) to cover onboard hardware and common peripherals.

- **Core runtime (protocol & configuration layer)**  
  - `fastapi` – MCP HTTP server framework (ASGI).  
  - `uvicorn[standard]` – ASGI server process.  
  - `pydantic` – configuration and data models (including MCP tool payload models).  
  - `pyyaml` – loading `config.yml`.  
  - `pyjwt` – verifying Cloudflare Access / other OAuth JWTs.  

- **Onboard hardware & system information**  
  - `psutil` – system information and metrics: CPU/memory/disk/network.  
  - `/proc`, `/sys`, and `vcgencmd` – obtaining CPU temperature, throttling status, and device model.  
  - Network interfaces, routes, and IP information via `psutil` + `ip` / `ip addr`.  

- **General I/O buses and onboard interfaces (GPIO / I2C / SPI / UART, etc.)**  
  - `gpiozero` (or abstractions over `lgpio`/`RPi.GPIO`) – GPIO and PWM control, LEDs, fans, and simple peripherals.  
  - `smbus2` – I2C access for common sensors (e.g., temperature/humidity, environmental sensors, IMUs).  
  - (Optional) `spidev` – SPI bus access for SPI sensors, displays, etc.  
  - (Optional) `pyserial` – UART/serial access for external peripherals (serial sensors, MCUs, etc.).  

- **Camera & media**  
  - (Optional) `picamera2` or equivalent – access to the Raspberry Pi CSI camera (photos, basic video capture).  
  - When high‑level camera libraries are not available, fall back to `libcamera-*` CLI or other system‑level interfaces.  

- **System services & logs**  
  - (Optional) `dbus-next` – systemd access via D‑Bus (service status, control).  
  - If D‑Bus is not available, fall back to `subprocess` calls to `systemctl`, `journalctl`, etc.  

- **Standard library (no extra dependency)**  
  - `asyncio` – concurrency and async I/O.  
  - `subprocess` – invoking `systemctl`, `journalctl`, `vcgencmd`, `libcamera-*`, etc.  
  - `logging` – base logging, wrapped to produce structured JSON.  
  - `sqlite3` – persistence for metrics and local state.  
  - `pathlib`, `os`, `json`, etc.

**Dependency strategy**:

- Within a capability domain, if there is both:  
  - A mature, widely used third‑party library (richer features, friendlier API), and  
  - Standard‑library or lower‑level interfaces,  
  then:  
  - **Prefer the higher‑level third‑party library** (e.g., `gpiozero` instead of raw `/sys` or `RPi.GPIO`; `dbus-next` instead of shelling out to `systemctl`; `picamera2` instead of calling `libcamera` directly).  
  - If the high‑level library is not installed, cannot be installed, fails to initialize, or does not support a specific function, **fall back** to the lower‑level implementation (e.g., `subprocess` + system commands, direct `/sys`/`/proc` access).  
- Fallback behavior MUST:  
  - Detect library availability at startup or first use and record capability information (to feed `system.get_capabilities` / FR‑28).  
  - Log warnings when falling back and degrade gracefully where possible.  
  - Keep semantics consistent: the same MCP tool should have the same input/output contract across backends.

- **Development & test dependencies (recommended)**  
  - `pytest` + `pytest-asyncio` – unit tests and async tests.  
  - `mypy` – static type checking.  
  - `ruff` – style and static analysis.  
  - `black` (optional) – code formatting.  

Dependency management SHOULD use a single `pyproject.toml` managed by `uv`, without extra `requirements.txt` files.

### 2.3 Core Components

The architecture is split into the following main components:

1. **MCP Server (non‑privileged process)**  
   - Implements the MCP protocol (HTTP/JSON‑RPC).  
   - Processes authentication information (Cloudflare Access/OAuth).  
   - Validates parameters, enforces authorization, logs, and maps `ToolError` to JSON‑RPC errors.  
   - Invokes domain modules (system info, metrics, services, device control, self‑update, etc.).  

2. **Privileged Operations Agent (`raspi-ops-agent`)**  
   - Runs as root or a dedicated user with sudo capabilities.  
   - Exposes a local IPC interface over a Unix domain socket.  
   - Executes privileged operations only through a fixed set of “operation types”:  
     - GPIO/I2C/SPI/camera access.  
     - systemd service control.  
     - Process signals.  
     - Reboot/shutdown.  
     - Self‑update and OS update operations.  
   - Enforces an operation whitelist and parameter validation to avoid arbitrary command execution.  

3. **Cloudflare Tunnel & Access (edge layer)**  
   - Exposes the MCP server safely to the internet.  
   - Terminates TLS, decrypts traffic, and applies Cloudflare Access policies.  
   - Integrates with OAuth/OIDC identity providers and forwards identity assertions (JWT/headers) to the backend.  

4. **Local System Resources**  
   - OS kernel, filesystem, `/proc`, `/sys`, systemd, hardware buses, sensors, etc.  
   - Accessed by modules through well‑defined, constrained interfaces.

5. **Extension / Plugin Host (Phase 2+)**  
   - A host framework inside MCP Server for loading optional Python plugins or invoking external components via subprocess/FFI (e.g., Go/Node tools).  
   - Exposes new tool namespaces (e.g., `storage.*`, `docker.*`) while enforcing the same security/authorization model.  
   - Ensures all dangerous operations still go through `raspi-ops-agent` and cannot bypass the privilege boundary.

### 2.4 Logical Module Groups

Logically, server functions are grouped into domain modules:

- **System Information, Metrics & Network** – system info, metrics collection, network state.  
- **Service & Process Management** – systemd service control, process enumeration/detail.  
- **Device Control & Power** – GPIO, I2C, camera, reboot/shutdown.  
- **Logging & Observability** – application logs, audit logs, diagnostics.  
- **Security & Access Control** – auth, roles, tool policies, rate limiting.  
- **Self‑Update & OS Update & Rollback** – server self‑update, optional OS updates, safe rollback.  
- **Deployment & Operations Integration** – systemd integration, Cloudflare Tunnel, backup/restore.  
- **Extension & External Integration** – plugins and external tools.

These modules are implemented as libraries/subsystems and invoked by the MCP tool layer through clear interfaces.

### 2.5 Core Python Interfaces

For testability and maintainability, we recommend the following core Python interfaces:

- `class ToolContext(BaseModel)` – encapsulates the context of a single MCP call. Example fields:  
  - `tool_name: str`  
  - `caller: CallerInfo` (user id, role, IP, etc.)  
  - `request_id: str`  
  - `timestamp: datetime`  
- `ToolHandler = Callable[[ToolContext, Dict[str, Any]], Awaitable[ToolResponse]]` – MCP tool handler type.  
- `class ToolRegistry` – manages the mapping from tool names to handlers:

  ```python
  class ToolRegistry:
      def register(self, name: str, handler: ToolHandler) -> None: ...
      async def invoke(self, name: str, ctx: ToolContext, params: dict) -> ToolResponse: ...
  ```

- Each domain module exposes a “service class” that handlers call, for example:  
  - `SystemInfoService`, `MetricsService`, `NetworkService` – `system.*`, `metrics.*`, `network.*`.  
  - `GpioService`, `I2cService`, `CameraService`, `PowerService` – `gpio.*`, `i2c.*`, `camera.*`, `system.reboot`/`system.shutdown`.  
  - `ServiceManager`, `ProcessManager` – `service.*`, `process.*`.  
  - `LogsService` – `logs.*`.  
  - `UpdateService` – self‑update and OS update tools.  
  - `IntrospectionService` – capability matrix and server introspection (FR‑27, FR‑28).  
  - `ExtensionManager` (Phase 2+) – plugin loading and external integrations.  

The MCP HTTP entrypoint is intentionally thin:

- Parse HTTP/JSON‑RPC requests into `ToolContext` + parameter dict.  
- Use `ToolRegistry.invoke` to dispatch to the appropriate handler.  
- Serialize handler results (or `ToolError`) into MCP‑compatible JSON‑RPC responses.

## 3. Process Model & Deployment

### 3.1 Recommended Process Model

To balance security and functionality, we use a two‑process model:

- `mcp-raspi-server` (non‑privileged):  
  - Runs as a non‑root user.  
  - Listens on localhost or LAN address (e.g., `127.0.0.1:8000`).  
  - Implements MCP protocol, authentication, authorization, and request routing.  

- `raspi-ops-agent` (privileged):  
  - Runs as root or a dedicated privileged user.  
  - Listens on a Unix domain socket for requests from MCP Server.  
  - Exposes only a fixed set of operation types (via a dispatcher/handler registry).  

Both are managed by `systemd`:

- Separate systemd units with restart policies (`Restart=on-failure`).  
- `mcp-raspi-server` depends on `raspi-ops-agent` (see doc 12 for unit files).

### 3.2 Network & Exposure

- MCP Server by default listens on `127.0.0.1` or an internal IP and is **not exposed directly to the internet**.  
- Public access is provided through a Cloudflare Tunnel reverse proxy:  
  - Cloudflare Tunnel → local `127.0.0.1:8000`.  
  - Cloudflare Access enforces OAuth/OIDC and adds headers such as `Cf-Access-Jwt-Assertion`.  
- For pure LAN deployments, Cloudflare can be skipped, but a reverse proxy with TLS and auth is still recommended.

## 4. Module Responsibilities

### 4.1 System Information, Metrics & Network

- Provide basic system information: model, hardware, OS, kernel, boot time, etc.  
- Provide real‑time health snapshots and periodic metric sampling (CPU/memory/disk/network/temperature).  
- Provide network status information: interfaces, IP addresses, link status, basic routing view.  
- Abstract access to `/proc`, `/sys`, `vcgencmd`, `ip`/`ip addr`, etc., combined with `psutil`.  
- Implement MCP tools `system.*`, `metrics.*`, and `network.*` (schemas and APIs defined in docs 05 and 06).

### 4.2 Service & Process Management

- Enumerate and query current processes and their attributes.  
- Wrap systemd and related commands (e.g., `systemctl`) for service control.  
- Provide controlled service start/stop/restart capabilities.  
- Implement MCP tools `service.*` and `process.*` (see docs 05 and 07).

### 4.3 Device Control

- Wrap GPIO, PWM, I2C, SPI, and camera hardware interfaces.  
- Hide hardware differences across Pi models.  
- Apply pin and address whitelists to avoid unsafe operations.  
- Implement MCP tools `gpio.*`, `i2c.*`, `camera.*`, and power tools (`system.reboot`, `system.shutdown` via a `system_power` module).

### 4.4 Logging & Observability

- Manage application logs, audit logs, and diagnostics.  
- Provide log query interfaces (read‑only, restricted).  
- Integrate with system logs (e.g., `journalctl`) for diagnostics.  
- Implement MCP tools `logs.*` (see docs 05 and 09).

### 4.5 Security & Access Control

- Validate authentication tokens from Cloudflare Access or other IdPs.  
- Parse user identity and roles and apply tool‑level access control.  
- Maintain tool configuration (enabled state, safety levels, rate limits, etc.).  
- Implement security modules and integrate with `ToolPolicyEnforcer` (see doc 04).

### 4.6 Self‑Update & Rollback

- Provide MCP tools for server self‑update (`manage.update_server`).  
- Orchestrate update flows: download, verify, switch version, restart services.  
- Implement safe rollback so MCP Server remains available on failure.  
- Optionally provide OS package updates (`manage.update_os` / `manage.preview_os_updates`), executed via `apt`/`apt-get`, treated as high‑risk and disabled by default (see doc 10).

### 4.7 Introspection & Capabilities

- Maintain and report a capability matrix for the current device and server instance:  
  - Available hardware features (camera, temperature sensor, specific buses).  
  - Enabled modules and MCP tool namespaces.  
  - Current version, self‑update status, configuration summary (without secrets).  
- Implement tools like `system.get_capabilities` and `manage.get_server_status` to support FR‑27 and FR‑28.

### 4.8 Extension & Integration

- Provide a unified host framework for plugins and external integrations (Phase 2+):  
  - Load optional Python plugin modules (e.g., `mcp_raspi.modules.extensions.*`).  
  - Interact with non‑Python components (Go/Node tools) via subprocess/FFI.  
- Expose extension capabilities via additional tool namespaces, enforcing the same security/policy model.  
- Ensure all dangerous operations still pass through `raspi-ops-agent` and cannot bypass privilege boundaries.

## 5. Request Flow

### 5.1 Typical Request Lifecycle

1. **Client call**  
   - ChatGPT (or another MCP client) calls a tool (e.g., `gpio.write_pin`) via MCP, sending the request to Cloudflare Tunnel.  

2. **Edge processing**  
   - Cloudflare terminates TLS, validates OAuth/OIDC sessions, and applies Access policies.  
   - Cloudflare forwards authenticated requests to `mcp-raspi-server`, including identity assertions (JWT/headers).  

3. **MCP Server processing**  
   - Validate the request signature and authentication information.  
   - Check whether the requested tool is enabled and the caller has sufficient permissions.  
   - Validate parameters against JSON Schema.  
   - Write an audit log entry.  
   - Route to the corresponding domain module (system, metrics, gpio, etc.).  

4. **Privileged operations (if needed)**  
   - If hardware or privileged operations are required, the module sends a constrained RPC request to `raspi-ops-agent` over IPC.  
   - `raspi-ops-agent` executes the operation and returns a structured result or error.  

5. **Response & logging**  
   - The module returns a domain result object or raises a `ToolError` (or subclass).  
   - The MCP Server’s JSON‑RPC layer places the result in the `result` field or maps `ToolError` to JSON‑RPC `error` according to doc 05 (§2.3, §2.5, §9).  
   - All key steps and errors are logged and surfaced via metrics where appropriate.

### 5.2 Error Handling

- The external protocol layer strictly follows JSON‑RPC 2.0 / MCP conventions (see doc 05 §2.3):  
  - Successful calls:  
    - `result` holds a tool‑specific JSON object (structure defined by that tool’s `result` schema in doc 05).  
  - Failed calls:  
    - Use JSON‑RPC `error` with `error.code` and `error.message` describing the category and summary.  
    - Use `error.data.error_code` and `error.data.details` for project‑specific structured error info.  
- Domain error expression:  
  - Tool handlers encountering domain errors (invalid arguments, insufficient permissions, unavailable resources, etc.) SHOULD raise `ToolError(error_code=..., message=..., details=...)`.  
  - A central mapping layer catches `ToolError` and converts it to JSON‑RPC errors, keeping `error_code` values consistent with doc 05 §9.  
- Common error categories:  
  - Privileged agent unavailable/timeout → `error_code="unavailable"`.  
  - Parameter errors → `error_code="invalid_argument"`.  
  - Permission errors → `error_code="permission_denied"`.  
  - Failed preconditions (hardware not ready, invalid state, etc.) → `error_code="failed_precondition"`.  

This layered handling keeps module code focused on domain logic and `ToolError`, while the protocol/logging layer handles JSON‑RPC and error classification.

## 6. Privileged IPC Protocol

### 6.1 Transport & Endpoint

- Use a **Unix domain socket** for local inter‑process communication:  
  - Default path: `/run/mcp-raspi/ops-agent.sock`.  
  - Socket owner is the privileged agent’s user/group; permissions restrict access to the MCP Server user.  
- Message format: JSON text per line (newline‑delimited JSON), one request/response per line.

Implementation:

- `mcp_raspi.ipc.client` and `mcp_raspi_ops.ipc_server` use `asyncio`, `socket`, and `json` to implement this protocol according to the message structures below.

### 6.2 Request Message

Example request JSON:

```json
{
  "id": "req-1234",
  "operation": "gpio.write",
  "timestamp": "2025-01-01T12:34:56Z",
  "caller": {
    "user": "alice@example.com",
    "role": "operator"
  },
  "params": {
    "pin": 17,
    "value": "high",
    "duration_ms": 1000
  }
}
```

- `id` – unique request ID generated by MCP Server to correlate logs and responses.  
- `operation` – privileged operation type (from a fixed set, e.g., `gpio.read`, `gpio.write`, `system.reboot`, `service.control`).  
- `caller` – caller identity summary for audit and optional additional checks.  
- `params` – operation‑specific parameters.

### 6.3 Response Message

Example success response:

```json
{
  "id": "req-1234",
  "status": "ok",
  "data": {
    "pin": 17,
    "value": "high"
  },
  "error": null
}
```

Example failure response:

```json
{
  "id": "req-1234",
  "status": "error",
  "data": null,
  "error": {
    "code": "failed_precondition",
    "message": "GPIO pin 17 is not allowed",
    "details": {
      "pin": 17
    }
  }
}
```

- `status` – `"ok"` or `"error"`.  
- `data` – arbitrary JSON on success (operation‑specific).  
- `error` – error object on failure, with:  
  - `code` – internal error code string.  
  - `message` – human‑readable message.  
  - `details` – optional structured details (e.g., pin/address).

> Note: This `status`/`data`/`error` envelope is **only** for the internal IPC protocol between MCP Server and `raspi-ops-agent`. The external MCP/JSON‑RPC layer uses the standard JSON‑RPC structure described in §5.2.

### 6.4 Operation Set

The privileged agent supports a fixed set of operation types, for example:

- `system.reboot`, `system.shutdown`  
- `gpio.read`, `gpio.write`, `gpio.configure`, `gpio.pwm`  
- `i2c.read`, `i2c.write`, `i2c.scan`  
- `service.status`, `service.control`, `service.list`  
- `process.list`, `process.details`, `process.signal`  
- `update.server`, `update.os`  

Additional operations MUST be explicitly registered in the agent code and enabled by configuration.

Internally, each `operation` string maps to a handler class or function (e.g., `GpioHandler.write`, `ServiceHandler.control`), maintained centrally in a registry.

## 7. Concurrency & Execution Model

### 7.1 MCP Server Concurrency Model

- MCP Server is a long‑running process using `uvicorn` + `asyncio` to handle concurrent requests.  
- Blocking operations (e.g., some OS commands, heavy I/O) SHOULD run in thread pools or subprocesses to avoid blocking the event loop.  
- Requirements:  
  - Configurable per‑request timeout (e.g., 5–30 seconds).  
  - Concurrency limits for privileged operations (e.g., maximum concurrent IPC calls) to avoid overload.  
  - For long‑running tasks (e.g., OS updates), use asynchronous task/job models with status polling (e.g., via `manage.get_server_status`), not long‑held HTTP requests.

### 7.2 Privileged Agent Execution Model

- Treat each operation as an independent task:  
  - Read a request from the IPC queue.  
  - Execute the operation in a restricted environment (possibly using subprocesses).  
  - Write back a response.  
- For high‑risk operations (reboot, shutdown, OS updates), consider separate queues or prioritization to better control concurrency and ordering.

## 8. Configuration & Policy

### 8.1 Configuration Files

Default global configuration file: `/etc/mcp-raspi/config.yml`. It includes:

- Server listen address and port.  
- Cloudflare / OAuth integration settings.  
- Per‑namespace tool enables (`system`, `metrics`, `gpio`, `service`, etc.).  
- Tool safety levels and required roles.  
- Logging paths and log level.  
- Metric sampling configuration.  
- Self‑update and OS update policies.  

See doc 14 for detailed configuration reference and examples.

### 8.2 Load & Validation

- At startup, load `config.yml` and validate it strictly via a Pydantic configuration model:  
  - Network listen address and port.  
  - Tool enable/disable flags, role mappings, safety levels.  
  - GPIO/I2C whitelists and limits.  
  - Logging and metrics configuration.  
  - Self‑update and OS update policies.  
- If validation fails, refuse to start and emit a clear error message.

#### 8.2.1 Configuration Layers & Precedence

Configuration is represented in code as a unified Python object (e.g., `AppConfig`), built from multiple layers (later overrides earlier):

1. **Built‑in defaults**  
   - Default values in the Pydantic model (listen address, log level, sampling intervals, etc.).  
2. **Global config file**  
   - `/etc/mcp-raspi/config.yml` or a YAML file specified via `--config`.  
   - Captures instance‑level persistent settings.  
3. **Environment variables**  
   - Override specific fields using a prefix (e.g., `MCP_RASPI_...`):  
     - `MCP_RASPI_SERVER__LISTEN=0.0.0.0:8000`  
     - `MCP_RASPI_SECURITY__MODE=local`  
   - Suitable for credentials and environment‑specific overrides.  
4. **Command‑line arguments**  
   - Highest precedence; used for a small set of frequently overridden fields.  
   - Example: `mcp-raspi-server --config /path/config.yml --log-level debug`.

The loader MUST apply layers in this order and produce a single `AppConfig` instance, and major settings SHOULD be visible via logs and introspection tools (`manage.get_server_status`).

### 8.3 Reload & Dynamic Changes

- Optional support for config reload (e.g., via SIGHUP or an MCP management tool).  
- When reloading:  
  - Changes to permission policies and whitelists SHOULD NOT disrupt in‑flight operations.  
  - On reload failure, the old configuration MUST remain active.  
  - A config version identifier MAY be included in `manage.get_server_status` to aid debugging.

### 8.4 Example Configuration Skeleton

See doc 14 for a full reference. A minimal skeleton:

```yaml
server:
  listen: "127.0.0.1:8000"
  log_level: "info"

security:
  mode: "cloudflare"  # or "local"
  roles:
    viewer:
      allowed_levels: ["read_only"]
    operator:
      allowed_levels: ["read_only", "safe_control"]
    admin:
      allowed_levels: ["read_only", "safe_control", "admin"]
  role_mappings:
    groups_to_roles:
      "mcp-admins": "admin"
      "iot-ops": "operator"

tools:
  system:
    enabled: true
  gpio:
    enabled: true
  i2c:
    enabled: true

ipc:
  socket_path: "/run/mcp-raspi/ops-agent.sock"
  request_timeout_seconds: 5
```

### 8.5 Tool Policy

Each MCP tool has the following attributes:

- `enabled` – whether it is enabled.  
- `safety_level` – one of `read_only | safe_control | admin`.  
- `rate_limit` – optional call frequency limits.  
- `requires_privileged_agent` – whether it must be executed via the privileged agent.  

These policies are configured via `config.yml` and MAY be modified by future management tools.

## 9. Deployment Modes

### 9.1 Single‑Node

- The primary target is single‑device deployment:  
  - MCP Server + privileged agent + optional Cloudflare Tunnel on one Pi.  
  - Local or remote (ChatGPT) clients access via MCP.  
- No additional service discovery or distributed coordination is required.

### 9.2 Multi‑Node / Fleet (Future)

- For multiple Pis, an external management plane can be added on top:  
  - Each device still runs its own MCP Server.  
  - The management system orchestrates devices via their MCP interfaces.  
  - This doc does not design a centralized control plane; it only leaves room for such a layer in the future.

## 10. Extensibility & Future Evolution

- To add new tool namespaces (e.g., `storage.*`, `docker.*`):  
  - Register tools and JSON Schemas in the MCP tools spec (doc 05).  
  - Implement corresponding modules or extend existing ones.  
  - Define security policies in configuration.  
- Plugin mechanisms can be used to integrate specific hardware or systems (e.g., Home Assistant, Zigbee gateways) as optional modules.  
- The core architecture keeps interfaces and module boundaries technology‑agnostic, allowing non‑Python components to be integrated via plugins/subprocesses without major refactoring, as long as they respect the established contracts.

## 11. Non‑Goals

- Do not build a general cloud management platform or large‑scale cluster scheduler.
- Do not require multi‑node centralized control; focus on single or small numbers of devices.
- Do not provide a complex Web UI in the core project (a Web UI can be built on top of MCP later).
- Do not promise full support for all non‑Raspberry Pi OS Linux distributions in Phase 1.

---

<!-- Merged from 02-addendum-ipc-protocol-robustness.md -->

## 12. IPC Protocol Robustness & Error Handling

### 12.1 IPC Reconnection Strategy

#### 12.1.1 Overview

The privileged agent may crash, restart, or become temporarily unavailable. The MCP server must handle these scenarios gracefully without affecting user experience.

**Goals**:
- Automatic reconnection on agent failure
- Transparent to clients (where possible)
- Request buffering during downtime
- Clear error messages when unavailable

#### 12.1.2 Connection States

```python
from enum import Enum

class IPCConnectionState(Enum):
    """IPC connection states."""
    DISCONNECTED = "disconnected"    # No connection
    CONNECTING = "connecting"        # Attempting connection
    CONNECTED = "connected"          # Active connection
    RECONNECTING = "reconnecting"    # Attempting reconnection after failure
    FAILED = "failed"                # Reconnection attempts exhausted
```

#### 12.1.3 Reconnection Implementation

```python
# src/mcp_raspi/ipc/client.py

import asyncio
from typing import Optional
from datetime import datetime, timedelta

class IPCClient:
    """IPC client with automatic reconnection."""

    def __init__(self, config: IPCConfig):
        self.config = config
        self.socket_path = config.socket_path
        self.state = IPCConnectionState.DISCONNECTED
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        # Reconnection settings
        self.reconnect_enabled = True
        self.reconnect_delay_seconds = 1.0
        self.reconnect_max_delay_seconds = 30.0
        self.reconnect_backoff_multiplier = 2.0
        self.reconnect_max_attempts = 10  # 0 = infinite

        # Connection tracking
        self.connection_attempts = 0
        self.last_connection_attempt: Optional[datetime] = None
        self.connected_at: Optional[datetime] = None
        self.disconnected_at: Optional[datetime] = None

    async def connect(self) -> bool:
        """
        Connect to privileged agent.

        Returns:
            True if connected, False if failed.
        """
        if self.state == IPCConnectionState.CONNECTED:
            return True

        self.state = IPCConnectionState.CONNECTING
        self.connection_attempts += 1
        self.last_connection_attempt = datetime.now()

        try:
            # Open Unix domain socket
            self.reader, self.writer = await asyncio.open_unix_connection(
                self.socket_path
            )

            # Send handshake
            await self._send_handshake()

            # Wait for handshake response
            response = await self._receive_handshake()

            if response.get("status") == "ok":
                self.state = IPCConnectionState.CONNECTED
                self.connected_at = datetime.now()
                self.connection_attempts = 0
                logger.info("IPC connected to privileged agent")
                return True
            else:
                raise IPCError(f"Handshake failed: {response.get('error')}")

        except Exception as e:
            logger.error(
                "IPC connection failed",
                error=str(e),
                attempt=self.connection_attempts
            )
            self.state = IPCConnectionState.DISCONNECTED
            return False

    async def ensure_connected(self) -> None:
        """
        Ensure connection is active, reconnect if necessary.

        Raises:
            IPCUnavailableError: If connection cannot be established.
        """
        if self.state == IPCConnectionState.CONNECTED:
            return

        # Attempt reconnection
        success = await self._reconnect_with_backoff()

        if not success:
            raise IPCUnavailableError(
                "Privileged agent unavailable. "
                f"Connection attempts: {self.connection_attempts}"
            )

    async def _reconnect_with_backoff(self) -> bool:
        """
        Reconnect with exponential backoff.

        Returns:
            True if reconnected, False if max attempts exceeded.
        """
        self.state = IPCConnectionState.RECONNECTING

        delay = self.reconnect_delay_seconds

        while True:
            # Check max attempts
            if (self.reconnect_max_attempts > 0 and
                self.connection_attempts >= self.reconnect_max_attempts):
                logger.error(
                    "IPC reconnection failed - max attempts exceeded",
                    max_attempts=self.reconnect_max_attempts
                )
                self.state = IPCConnectionState.FAILED
                return False

            # Wait before retry
            logger.info(
                "IPC reconnecting in {:.1f}s",
                delay,
                attempt=self.connection_attempts + 1
            )
            await asyncio.sleep(delay)

            # Attempt connection
            if await self.connect():
                logger.info("IPC reconnection successful")
                return True

            # Exponential backoff
            delay = min(
                delay * self.reconnect_backoff_multiplier,
                self.reconnect_max_delay_seconds
            )

    async def call(
        self,
        operation: str,
        params: dict,
        timeout: float = 30.0
    ) -> dict:
        """
        Call privileged agent operation.

        Args:
            operation: Operation name (e.g., "gpio_write")
            params: Operation parameters
            timeout: Request timeout in seconds

        Returns:
            Operation result

        Raises:
            IPCUnavailableError: Agent unavailable
            IPCTimeoutError: Request timed out
            IPCError: Other IPC errors
        """
        # Ensure connected
        await self.ensure_connected()

        try:
            # Send request
            request_id = self._generate_request_id()
            request = {
                "id": request_id,
                "operation": operation,
                "params": params,
                "timestamp": datetime.now().isoformat()
            }

            await self._send(request)

            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(
                    self._receive(request_id),
                    timeout=timeout
                )
                return response

            except asyncio.TimeoutError:
                logger.error(
                    "IPC request timeout",
                    operation=operation,
                    request_id=request_id,
                    timeout=timeout
                )
                # Mark connection as potentially dead
                await self._mark_connection_dead()
                raise IPCTimeoutError(
                    f"IPC request timed out after {timeout}s"
                )

        except (ConnectionError, BrokenPipeError) as e:
            # Connection lost - attempt reconnection
            logger.warning("IPC connection lost", error=str(e))
            await self._mark_connection_dead()

            # Retry once after reconnection
            if await self._reconnect_with_backoff():
                logger.info("Retrying IPC request after reconnection")
                return await self.call(operation, params, timeout)
            else:
                raise IPCUnavailableError("Privileged agent unavailable")

    async def _mark_connection_dead(self) -> None:
        """Mark connection as dead and clean up."""
        self.state = IPCConnectionState.DISCONNECTED
        self.disconnected_at = datetime.now()

        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

        self.reader = None
        self.writer = None

    async def disconnect(self) -> None:
        """Gracefully disconnect from agent."""
        if self.state != IPCConnectionState.CONNECTED:
            return

        try:
            # Send disconnect message
            await self._send({"type": "disconnect"})
        except:
            pass  # Ignore errors during disconnect

        await self._mark_connection_dead()
        logger.info("IPC disconnected from privileged agent")

    async def health_check(self) -> bool:
        """
        Check if IPC connection is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        if self.state != IPCConnectionState.CONNECTED:
            return False

        try:
            # Send ping
            response = await self.call("ping", {}, timeout=5.0)
            return response.get("status") == "ok"

        except Exception as e:
            logger.warning("IPC health check failed", error=str(e))
            return False
```

#### 12.1.4 Configuration

```yaml
# /etc/mcp-raspi/config.yml

ipc:
  socket_path: "/var/run/mcp-raspi/agent.sock"
  timeout_seconds: 30

  reconnection:
    enabled: true
    initial_delay_seconds: 1.0
    max_delay_seconds: 30.0
    backoff_multiplier: 2.0
    max_attempts: 10  # 0 = infinite

  health_check:
    enabled: true
    interval_seconds: 60
```

#### 12.1.5 Health Monitoring

```python
# Background task to monitor IPC health
async def monitor_ipc_health(ipc_client: IPCClient):
    """Monitor IPC connection health."""
    while True:
        await asyncio.sleep(60)  # Check every minute

        if not await ipc_client.health_check():
            logger.warning("IPC health check failed - attempting reconnection")

            # Trigger reconnection
            if await ipc_client._reconnect_with_backoff():
                logger.info("IPC health restored")
            else:
                logger.error("IPC health check failed - agent unavailable")

                # Alert operations
                await alerting.send_alert(
                    severity="critical",
                    message="Privileged agent unavailable",
                    context={"last_connected": ipc_client.connected_at}
                )
```

### 12.2 Request ID Collision Handling

#### 12.2.1 Overview

Request IDs must be unique to match responses to requests. Collisions can occur with poor ID generation or long-lived connections.

#### 12.2.2 Request ID Generation

```python
import uuid
import time
from typing import Set

class RequestIDGenerator:
    """Generates unique request IDs."""

    def __init__(self):
        self.counter = 0
        self.active_ids: Set[str] = set()
        self.max_active_ids = 10000  # Prevent memory leak

    def generate(self) -> str:
        """
        Generate unique request ID.

        Format: {timestamp_ms}-{counter}-{random}
        Example: 1701629400123-42-a3f5e8c2
        """
        timestamp_ms = int(time.time() * 1000)
        self.counter = (self.counter + 1) % 1000000  # Reset at 1M

        # Add randomness for extra uniqueness
        random_suffix = uuid.uuid4().hex[:8]

        request_id = f"{timestamp_ms}-{self.counter}-{random_suffix}"

        # Detect collision (extremely rare)
        if request_id in self.active_ids:
            logger.warning("Request ID collision detected", request_id=request_id)
            # Regenerate with new UUID
            request_id = f"{timestamp_ms}-{self.counter}-{uuid.uuid4().hex[:8]}"

        # Track active IDs
        self.active_ids.add(request_id)

        # Cleanup old IDs to prevent memory leak
        if len(self.active_ids) > self.max_active_ids:
            # Remove oldest 10%
            to_remove = list(self.active_ids)[:1000]
            self.active_ids -= set(to_remove)

        return request_id

    def mark_completed(self, request_id: str) -> None:
        """Mark request as completed and remove from active set."""
        self.active_ids.discard(request_id)
```

#### 12.2.3 Request Tracking

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

@dataclass
class PendingRequest:
    """Pending IPC request."""
    request_id: str
    operation: str
    params: dict
    sent_at: datetime
    timeout_seconds: float
    future: asyncio.Future

class RequestTracker:
    """Tracks pending IPC requests."""

    def __init__(self):
        self.pending: Dict[str, PendingRequest] = {}
        self.id_generator = RequestIDGenerator()

    async def send_request(
        self,
        operation: str,
        params: dict,
        timeout: float
    ) -> dict:
        """
        Send request and wait for response.

        Args:
            operation: Operation name
            params: Operation parameters
            timeout: Request timeout

        Returns:
            Response from agent

        Raises:
            IPCTimeoutError: Request timed out
        """
        # Generate unique ID
        request_id = self.id_generator.generate()

        # Create future for response
        future = asyncio.Future()

        # Track request
        self.pending[request_id] = PendingRequest(
            request_id=request_id,
            operation=operation,
            params=params,
            sent_at=datetime.now(),
            timeout_seconds=timeout,
            future=future
        )

        # Send request
        request = {
            "id": request_id,
            "operation": operation,
            "params": params
        }
        await self._write_to_socket(request)

        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            # Clean up pending request
            self.pending.pop(request_id, None)
            self.id_generator.mark_completed(request_id)

            raise IPCTimeoutError(
                f"Request {request_id} timed out after {timeout}s"
            )

        finally:
            # Mark ID as completed
            self.id_generator.mark_completed(request_id)

    def handle_response(self, response: dict) -> None:
        """
        Handle response from agent.

        Args:
            response: Response dict with "id" field
        """
        request_id = response.get("id")

        if not request_id:
            logger.warning("Response missing request ID", response=response)
            return

        # Find pending request
        pending = self.pending.get(request_id)

        if not pending:
            logger.warning(
                "Received response for unknown request ID",
                request_id=request_id
            )
            return

        # Set result on future
        if not pending.future.done():
            pending.future.set_result(response)

        # Remove from pending
        self.pending.pop(request_id, None)

    async def cleanup_expired_requests(self) -> None:
        """Clean up expired pending requests."""
        now = datetime.now()
        expired = []

        for request_id, pending in self.pending.items():
            elapsed = (now - pending.sent_at).total_seconds()

            if elapsed > pending.timeout_seconds:
                expired.append(request_id)

                # Cancel future
                if not pending.future.done():
                    pending.future.set_exception(
                        IPCTimeoutError(f"Request expired: {request_id}")
                    )

        # Remove expired
        for request_id in expired:
            self.pending.pop(request_id, None)
            self.id_generator.mark_completed(request_id)

        if expired:
            logger.warning(
                "Cleaned up expired IPC requests",
                count=len(expired)
            )
```

### 12.3 Large Response Handling

#### 12.3.1 Overview

Some IPC responses may be large (e.g., process list with 100+ processes, metrics queries). The protocol must handle responses larger than a single read buffer.

**Challenges**:
- Socket buffers are limited (typically 8-64KB)
- Need to reassemble multi-chunk responses
- Prevent memory exhaustion with size limits

#### 12.3.2 Chunked Protocol

```python
# Protocol design for large responses

# Request (no change)
{
  "id": "request-123",
  "operation": "process_list",
  "params": {}
}

# Response (small - fits in one message)
{
  "id": "request-123",
  "status": "ok",
  "result": {...}
}

# Response (large - chunked)
# Chunk 1:
{
  "id": "request-123",
  "status": "ok",
  "chunked": true,
  "chunk_index": 0,
  "total_chunks": 5,
  "chunk_data": "...partial data..."
}

# Chunks 2-4: Same format with incrementing chunk_index

# Chunk 5 (final):
{
  "id": "request-123",
  "status": "ok",
  "chunked": true,
  "chunk_index": 4,
  "total_chunks": 5,
  "chunk_data": "...final data...",
  "final": true
}
```

#### 12.3.3 Implementation

```python
# src/mcp_raspi/ipc/protocol.py

import json
from typing import Dict, List, Optional
from dataclasses import dataclass

MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MB max per message
MAX_TOTAL_SIZE = 10 * 1024 * 1024  # 10 MB max total response

@dataclass
class ChunkedResponse:
    """Tracks chunked response assembly."""
    request_id: str
    total_chunks: int
    chunks: Dict[int, bytes]  # chunk_index -> data
    total_size: int = 0

class IPCProtocol:
    """IPC protocol handler with chunking support."""

    def __init__(self):
        self.pending_chunked: Dict[str, ChunkedResponse] = {}

    async def send_response(
        self,
        writer: asyncio.StreamWriter,
        request_id: str,
        result: dict
    ) -> None:
        """
        Send response, chunking if necessary.

        Args:
            writer: Stream writer
            request_id: Request ID
            result: Result to send
        """
        # Serialize result
        result_json = json.dumps(result)
        result_bytes = result_json.encode('utf-8')

        # Check if chunking needed
        if len(result_bytes) <= MAX_MESSAGE_SIZE:
            # Send as single message
            response = {
                "id": request_id,
                "status": "ok",
                "result": result
            }
            await self._write_message(writer, response)

        else:
            # Send as chunked messages
            await self._send_chunked_response(
                writer,
                request_id,
                result_bytes
            )

    async def _send_chunked_response(
        self,
        writer: asyncio.StreamWriter,
        request_id: str,
        data: bytes
    ) -> None:
        """Send large response as chunks."""
        chunk_size = MAX_MESSAGE_SIZE - 500  # Leave room for metadata

        # Calculate chunks
        total_chunks = (len(data) + chunk_size - 1) // chunk_size

        logger.info(
            "Sending chunked IPC response",
            request_id=request_id,
            total_size=len(data),
            total_chunks=total_chunks
        )

        # Send chunks
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(data))
            chunk_data = data[start:end]

            chunk = {
                "id": request_id,
                "status": "ok",
                "chunked": True,
                "chunk_index": i,
                "total_chunks": total_chunks,
                "chunk_data": chunk_data.decode('utf-8'),
                "final": (i == total_chunks - 1)
            }

            await self._write_message(writer, chunk)

    async def receive_response(
        self,
        reader: asyncio.StreamReader,
        request_id: str
    ) -> dict:
        """
        Receive response, reassembling chunks if necessary.

        Args:
            reader: Stream reader
            request_id: Expected request ID

        Returns:
            Complete response

        Raises:
            IPCProtocolError: Protocol violation
        """
        # Read first message
        message = await self._read_message(reader)

        # Check if chunked
        if not message.get("chunked"):
            # Single message response
            return message.get("result")

        # Chunked response - start assembly
        return await self._receive_chunked_response(
            reader,
            request_id,
            message
        )

    async def _receive_chunked_response(
        self,
        reader: asyncio.StreamReader,
        request_id: str,
        first_chunk: dict
    ) -> dict:
        """Receive and reassemble chunked response."""
        total_chunks = first_chunk["total_chunks"]

        # Initialize chunked response tracking
        chunked = ChunkedResponse(
            request_id=request_id,
            total_chunks=total_chunks,
            chunks={}
        )

        # Store first chunk
        chunk_data = first_chunk["chunk_data"].encode('utf-8')
        chunked.chunks[0] = chunk_data
        chunked.total_size += len(chunk_data)

        # Receive remaining chunks
        for expected_index in range(1, total_chunks):
            chunk = await self._read_message(reader)

            # Validate chunk
            if chunk.get("id") != request_id:
                raise IPCProtocolError("Chunk request ID mismatch")

            if chunk.get("chunk_index") != expected_index:
                raise IPCProtocolError("Chunk index out of order")

            # Store chunk
            chunk_data = chunk["chunk_data"].encode('utf-8')
            chunked.chunks[expected_index] = chunk_data
            chunked.total_size += len(chunk_data)

            # Check size limit
            if chunked.total_size > MAX_TOTAL_SIZE:
                raise IPCProtocolError(
                    f"Response exceeds max size {MAX_TOTAL_SIZE}"
                )

            # Check if final
            if chunk.get("final"):
                break

        # Reassemble chunks
        complete_data = b''.join(
            chunked.chunks[i] for i in range(len(chunked.chunks))
        )

        # Parse result
        result_json = complete_data.decode('utf-8')
        result = json.loads(result_json)

        logger.info(
            "Received chunked IPC response",
            request_id=request_id,
            total_size=chunked.total_size,
            chunks_count=len(chunked.chunks)
        )

        return result

    async def _write_message(
        self,
        writer: asyncio.StreamWriter,
        message: dict
    ) -> None:
        """Write message to stream with length prefix."""
        # Serialize message
        message_json = json.dumps(message)
        message_bytes = message_json.encode('utf-8')

        # Write length prefix (4 bytes, big-endian)
        length = len(message_bytes)
        length_bytes = length.to_bytes(4, byteorder='big')

        writer.write(length_bytes)
        writer.write(message_bytes)
        await writer.drain()

    async def _read_message(
        self,
        reader: asyncio.StreamReader
    ) -> dict:
        """Read message from stream with length prefix."""
        # Read length prefix
        length_bytes = await reader.readexactly(4)
        length = int.from_bytes(length_bytes, byteorder='big')

        # Validate length
        if length > MAX_MESSAGE_SIZE:
            raise IPCProtocolError(
                f"Message size {length} exceeds max {MAX_MESSAGE_SIZE}"
            )

        # Read message
        message_bytes = await reader.readexactly(length)
        message_json = message_bytes.decode('utf-8')
        message = json.loads(message_json)

        return message
```

### 12.4 Error Recovery

#### 12.4.1 Partial Write Recovery

```python
async def _write_with_recovery(
    self,
    writer: asyncio.StreamWriter,
    data: bytes
) -> None:
    """Write data with recovery on partial write."""
    offset = 0
    total_length = len(data)

    while offset < total_length:
        try:
            writer.write(data[offset:])
            await writer.drain()
            offset = total_length  # Success

        except BrokenPipeError:
            # Connection broken - cannot recover
            raise IPCConnectionError("IPC connection broken during write")

        except BlockingIOError:
            # Socket buffer full - retry
            logger.warning("IPC socket buffer full, retrying")
            await asyncio.sleep(0.1)
```

#### 12.4.2 Corrupted Message Recovery

```python
async def _read_message_with_recovery(
    self,
    reader: asyncio.StreamReader
) -> Optional[dict]:
    """Read message with recovery from corruption."""
    try:
        return await self._read_message(reader)

    except json.JSONDecodeError as e:
        logger.error("IPC message JSON decode error", error=str(e))

        # Attempt to skip to next message boundary
        # (Look for next length prefix)
        await self._skip_to_next_message(reader)

        return None  # Message lost

    except Exception as e:
        logger.error("IPC message read error", error=str(e))
        raise
```

---

<!-- Merged from 02-addendum-resource-limits-concurrency.md -->

## 13. Resource Limits & Concurrency Control

### 13.1 Maximum Concurrent Requests

#### 13.1.1 Overview

Limiting concurrent requests prevents resource exhaustion and ensures predictable performance on resource-constrained Raspberry Pi devices.

**Goals**:
- Prevent memory exhaustion from too many concurrent requests
- Maintain acceptable response times under load
- Graceful degradation when limits reached
- Fair request scheduling

#### 13.1.2 Concurrency Limits by Device

| Device | Max Concurrent Requests | Reasoning |
|--------|------------------------|-----------|
| **Pi 5** | 50 | Powerful CPU, 8GB RAM available |
| **Pi 4 (4GB)** | 30 | Good CPU, adequate RAM |
| **Pi 4 (2GB)** | 20 | Good CPU, limited RAM |
| **Pi 3** | 15 | Slower CPU, 1GB RAM |
| **Zero 2W** | 10 | Minimal resources |

#### 13.1.3 Implementation

```python
# src/mcp_raspi/server/concurrency.py

import asyncio
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ConcurrencyConfig:
    """Concurrency control configuration."""
    max_concurrent_requests: int = 30
    max_queue_size: int = 100
    queue_timeout_seconds: float = 60.0

    # Per-tool limits
    per_tool_limits: dict = None  # {"gpio.write_pin": 10, ...}

class ConcurrencyLimiter:
    """Limits concurrent request processing."""

    def __init__(self, config: ConcurrencyConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self.queue = asyncio.Queue(maxsize=config.max_queue_size)

        # Per-tool semaphores
        self.tool_semaphores = {}
        if config.per_tool_limits:
            for tool, limit in config.per_tool_limits.items():
                self.tool_semaphores[tool] = asyncio.Semaphore(limit)

        # Metrics
        self.active_requests = 0
        self.queued_requests = 0
        self.total_requests = 0
        self.rejected_requests = 0

    async def acquire(
        self,
        tool_name: str,
        timeout: Optional[float] = None
    ) -> bool:
        """
        Acquire permission to process request.

        Args:
            tool_name: Name of tool being invoked
            timeout: Timeout for queue wait (uses config default if None)

        Returns:
            True if acquired, raises exception if timeout/rejected

        Raises:
            ConcurrencyLimitError: Queue full or timeout
        """
        timeout = timeout or self.config.queue_timeout_seconds

        self.total_requests += 1

        # Check if queue full
        if self.queue.qsize() >= self.config.max_queue_size:
            self.rejected_requests += 1
            raise ConcurrencyLimitError(
                f"Request queue full ({self.config.max_queue_size}). "
                "Server is overloaded."
            )

        try:
            # Wait for global semaphore with timeout
            self.queued_requests += 1
            await asyncio.wait_for(
                self.semaphore.acquire(),
                timeout=timeout
            )
            self.queued_requests -= 1
            self.active_requests += 1

            # Also acquire per-tool semaphore if configured
            if tool_name in self.tool_semaphores:
                await self.tool_semaphores[tool_name].acquire()

            return True

        except asyncio.TimeoutError:
            self.queued_requests -= 1
            self.rejected_requests += 1
            raise ConcurrencyLimitError(
                f"Request queue timeout after {timeout}s. "
                "Server is overloaded."
            )

    def release(self, tool_name: str) -> None:
        """
        Release concurrency permit.

        Args:
            tool_name: Name of tool that was invoked
        """
        self.active_requests -= 1
        self.semaphore.release()

        # Release per-tool semaphore if acquired
        if tool_name in self.tool_semaphores:
            self.tool_semaphores[tool_name].release()

    def get_stats(self) -> dict:
        """Get concurrency statistics."""
        return {
            "max_concurrent": self.config.max_concurrent_requests,
            "active": self.active_requests,
            "queued": self.queued_requests,
            "total_requests": self.total_requests,
            "rejected_requests": self.rejected_requests,
            "rejection_rate": (
                self.rejected_requests / self.total_requests
                if self.total_requests > 0 else 0
            )
        }

# Usage in request handler
async def handle_mcp_request(request: dict, limiter: ConcurrencyLimiter):
    """Handle MCP request with concurrency limiting."""
    tool_name = request["method"]

    try:
        # Acquire permission (blocks if at limit)
        await limiter.acquire(tool_name)

        try:
            # Process request
            result = await execute_tool(tool_name, request["params"])
            return result

        finally:
            # Always release
            limiter.release(tool_name)

    except ConcurrencyLimitError as e:
        # Return error to client
        return {
            "error": {
                "code": -32000,  # Server error
                "message": str(e)
            }
        }
```

#### 13.1.4 Configuration

```yaml
# /etc/mcp-raspi/config.yml

server:
  concurrency:
    max_concurrent_requests: 30  # Device-dependent
    max_queue_size: 100
    queue_timeout_seconds: 60.0

    # Per-tool limits (optional)
    per_tool_limits:
      "gpio.write_pin": 10       # Limit GPIO writes
      "camera.capture": 3         # Limit concurrent captures
      "service.start": 5          # Limit service operations
```

#### 13.1.5 Dynamic Adjustment

```python
# Automatically adjust limits based on device model
def get_concurrency_limits() -> ConcurrencyConfig:
    """Get appropriate concurrency limits for device."""
    device_model = detect_device_model()

    limits = {
        "pi5": ConcurrencyConfig(max_concurrent_requests=50),
        "pi4-4gb": ConcurrencyConfig(max_concurrent_requests=30),
        "pi4-2gb": ConcurrencyConfig(max_concurrent_requests=20),
        "pi3": ConcurrencyConfig(max_concurrent_requests=15),
        "zero2w": ConcurrencyConfig(max_concurrent_requests=10),
    }

    return limits.get(device_model, ConcurrencyConfig(max_concurrent_requests=20))
```

### 13.2 Memory Limits

#### 13.2.1 Overview

Memory limits prevent the MCP server from consuming all available RAM, leaving resources for the OS and other applications.

#### 13.2.2 Memory Budget by Device

| Device | Total RAM | OS Reserve | Other Apps | MCP Budget | Limit |
|--------|-----------|------------|------------|------------|-------|
| Pi 5 (8GB) | 8192 MB | 200 MB | 500 MB | 7492 MB | 250 MB |
| Pi 4 (4GB) | 4096 MB | 200 MB | 500 MB | 3396 MB | 250 MB |
| Pi 4 (2GB) | 2048 MB | 200 MB | 300 MB | 1548 MB | 200 MB |
| Pi 3 (1GB) | 1024 MB | 150 MB | 200 MB | 674 MB | 150 MB |
| Zero 2W | 512 MB | 100 MB | 100 MB | 312 MB | 100 MB |

#### 13.2.3 Systemd Memory Limits

```ini
# /etc/systemd/system/mcp-raspi-server.service

[Service]
# Hard limit - process killed if exceeded
MemoryMax=250M

# Soft limit - throttling starts here
MemoryHigh=200M

# Swap limit (disable swap for predictable performance)
MemorySwapMax=0
```

#### 13.2.4 Application-Level Memory Tracking

```python
# src/mcp_raspi/server/memory.py

import psutil
import os
from typing import Optional

class MemoryMonitor:
    """Monitors application memory usage."""

    def __init__(self, limit_mb: int, warning_threshold: float = 0.8):
        self.limit_bytes = limit_mb * 1024 * 1024
        self.warning_threshold = warning_threshold
        self.warning_bytes = int(self.limit_bytes * warning_threshold)
        self.process = psutil.Process(os.getpid())

    def get_current_usage(self) -> int:
        """Get current memory usage in bytes."""
        return self.process.memory_info().rss

    def get_usage_percent(self) -> float:
        """Get memory usage as percentage of limit."""
        current = self.get_current_usage()
        return (current / self.limit_bytes) * 100

    def is_above_warning(self) -> bool:
        """Check if memory usage above warning threshold."""
        return self.get_current_usage() > self.warning_bytes

    def is_above_limit(self) -> bool:
        """Check if memory usage above hard limit."""
        return self.get_current_usage() > self.limit_bytes

    async def check_and_alert(self) -> None:
        """Check memory and alert if thresholds exceeded."""
        current_mb = self.get_current_usage() / (1024 * 1024)
        limit_mb = self.limit_bytes / (1024 * 1024)
        percent = self.get_usage_percent()

        if self.is_above_limit():
            logger.critical(
                "Memory limit exceeded",
                current_mb=f"{current_mb:.1f}",
                limit_mb=f"{limit_mb:.1f}",
                percent=f"{percent:.1f}%"
            )
            # Trigger emergency actions
            await self._emergency_memory_reduction()

        elif self.is_above_warning():
            logger.warning(
                "Memory usage high",
                current_mb=f"{current_mb:.1f}",
                limit_mb=f"{limit_mb:.1f}",
                percent=f"{percent:.1f}%"
            )

    async def _emergency_memory_reduction(self) -> None:
        """Emergency memory reduction actions."""
        # 1. Clear metrics cache
        await metrics_store.clear_cache()

        # 2. Clear log buffers
        await log_buffer.flush()

        # 3. Force garbage collection
        import gc
        gc.collect()

        # 4. Reject new requests temporarily
        concurrency_limiter.pause_new_requests(duration=30)

        logger.info("Emergency memory reduction completed")

# Background task
async def monitor_memory(memory_monitor: MemoryMonitor):
    """Background task to monitor memory."""
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        await memory_monitor.check_and_alert()
```

#### 13.2.5 Per-Component Memory Budgets

```python
MEMORY_BUDGETS = {
    # Component budgets (MB)
    "server_base": 40,        # MCP server core
    "metrics_cache": 30,      # Metrics query cache
    "log_buffer": 10,         # Log buffering
    "request_pool": 50,       # Active request processing
    "ipc_buffers": 20,        # IPC communication
    "other": 50,              # Misc overhead
}

def check_budget_compliance():
    """Check if components staying within budgets."""
    # Measure per-component usage (requires memory profiling)
    # This is Phase 2+ feature
    pass
```

### 13.3 GPIO/I2C Operation Queuing

#### 13.3.1 Overview

Hardware operations (GPIO, I2C) must be serialized to prevent conflicts and ensure reliable operation.

**Requirements**:
- Serial access to shared GPIO pins
- Serial access to I2C bus
- Fair scheduling (prevent starvation)
- Timeout handling

#### 13.3.2 GPIO Operation Queue

```python
# src/mcp_raspi/hardware/gpio_queue.py

import asyncio
from collections import deque
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class GPIOOperation:
    """Queued GPIO operation."""
    pin: int
    operation: str  # "read", "write", "pwm"
    params: dict
    future: asyncio.Future
    queued_at: datetime
    timeout: float

class GPIOQueue:
    """Queue for GPIO operations to prevent conflicts."""

    def __init__(self):
        # Per-pin queues
        self.pin_queues: Dict[int, deque] = {}
        self.pin_locks: Dict[int, asyncio.Lock] = {}

        # Global queue metrics
        self.total_operations = 0
        self.timed_out_operations = 0

    async def execute(
        self,
        pin: int,
        operation: str,
        params: dict,
        timeout: float = 10.0
    ) -> any:
        """
        Execute GPIO operation with queuing.

        Args:
            pin: GPIO pin number
            operation: Operation type
            params: Operation parameters
            timeout: Operation timeout

        Returns:
            Operation result

        Raises:
            TimeoutError: Operation timed out in queue
        """
        # Ensure queue and lock exist for pin
        if pin not in self.pin_queues:
            self.pin_queues[pin] = deque()
            self.pin_locks[pin] = asyncio.Lock()

        # Create operation
        future = asyncio.Future()
        op = GPIOOperation(
            pin=pin,
            operation=operation,
            params=params,
            future=future,
            queued_at=datetime.now(),
            timeout=timeout
        )

        self.total_operations += 1

        # Acquire lock for pin (serializes access)
        async with self.pin_locks[pin]:
            try:
                # Execute operation
                result = await asyncio.wait_for(
                    self._execute_operation(op),
                    timeout=timeout
                )
                return result

            except asyncio.TimeoutError:
                self.timed_out_operations += 1
                logger.error(
                    "GPIO operation timeout",
                    pin=pin,
                    operation=operation,
                    timeout=timeout
                )
                raise TimeoutError(
                    f"GPIO operation on pin {pin} timed out after {timeout}s"
                )

    async def _execute_operation(self, op: GPIOOperation) -> any:
        """Execute the actual GPIO operation."""
        if op.operation == "read":
            return await self._gpio_read(op.pin)
        elif op.operation == "write":
            return await self._gpio_write(op.pin, op.params["value"])
        elif op.operation == "pwm":
            return await self._gpio_pwm(op.pin, op.params)
        else:
            raise ValueError(f"Unknown GPIO operation: {op.operation}")

    async def _gpio_read(self, pin: int) -> int:
        """Read GPIO pin value."""
        # Actual GPIO read implementation
        # This would call IPC to privileged agent
        result = await ipc_client.call("gpio_read", {"pin": pin})
        return result["value"]

    async def _gpio_write(self, pin: int, value: int) -> None:
        """Write GPIO pin value."""
        await ipc_client.call("gpio_write", {"pin": pin, "value": value})

    async def _gpio_pwm(self, pin: int, params: dict) -> None:
        """Configure PWM on GPIO pin."""
        await ipc_client.call("gpio_pwm", {"pin": pin, **params})

    def get_queue_stats(self) -> dict:
        """Get queue statistics."""
        return {
            "total_operations": self.total_operations,
            "timed_out": self.timed_out_operations,
            "active_pins": len(self.pin_locks),
            "queue_depths": {
                pin: len(queue)
                for pin, queue in self.pin_queues.items()
                if len(queue) > 0
            }
        }
```

#### 13.3.3 I2C Bus Queue

```python
# src/mcp_raspi/hardware/i2c_queue.py

class I2CBusQueue:
    """Queue for I2C bus operations."""

    def __init__(self):
        # One lock per I2C bus
        self.bus_locks: Dict[int, asyncio.Lock] = {}

        # Metrics
        self.operations_per_bus: Dict[int, int] = {}

    async def execute(
        self,
        bus: int,
        address: int,
        operation: str,
        params: dict,
        timeout: float = 5.0
    ) -> any:
        """
        Execute I2C operation with bus locking.

        Args:
            bus: I2C bus number
            address: I2C device address
            operation: Operation type (read/write)
            params: Operation parameters
            timeout: Operation timeout

        Returns:
            Operation result
        """
        # Ensure lock exists for bus
        if bus not in self.bus_locks:
            self.bus_locks[bus] = asyncio.Lock()
            self.operations_per_bus[bus] = 0

        # Acquire bus lock (only one I2C operation at a time per bus)
        async with self.bus_locks[bus]:
            self.operations_per_bus[bus] += 1

            try:
                result = await asyncio.wait_for(
                    self._execute_i2c_operation(bus, address, operation, params),
                    timeout=timeout
                )
                return result

            except asyncio.TimeoutError:
                logger.error(
                    "I2C operation timeout",
                    bus=bus,
                    address=f"0x{address:02X}",
                    operation=operation
                )
                raise TimeoutError(
                    f"I2C operation on bus {bus} address 0x{address:02X} "
                    f"timed out after {timeout}s"
                )

    async def _execute_i2c_operation(
        self,
        bus: int,
        address: int,
        operation: str,
        params: dict
    ) -> any:
        """Execute I2C operation via IPC."""
        if operation == "read":
            result = await ipc_client.call("i2c_read", {
                "bus": bus,
                "address": address,
                **params
            })
            return result["data"]

        elif operation == "write":
            await ipc_client.call("i2c_write", {
                "bus": bus,
                "address": address,
                **params
            })
            return None

        else:
            raise ValueError(f"Unknown I2C operation: {operation}")
```

#### 13.3.4 Configuration

```yaml
# /etc/mcp-raspi/config.yml

hardware:
  gpio:
    queue:
      enabled: true
      default_timeout_seconds: 10.0
      max_queue_depth_per_pin: 20

  i2c:
    queue:
      enabled: true
      default_timeout_seconds: 5.0
      max_operations_per_second: 100  # Rate limit
```

### 13.4 Request Prioritization (Phase 2+)

#### 13.4.1 Priority Classes

```python
from enum import IntEnum

class RequestPriority(IntEnum):
    """Request priority levels."""
    CRITICAL = 0   # Emergency operations (reboot, shutdown)
    HIGH = 1       # Important operations (service management)
    NORMAL = 2     # Standard tool requests
    LOW = 3        # Background tasks (metrics, logs)

# Priority queue implementation
class PriorityQueue:
    """Priority-based request queue."""

    def __init__(self):
        self.queues = {
            priority: asyncio.Queue()
            for priority in RequestPriority
        }

    async def put(self, priority: RequestPriority, item: any):
        """Add item to priority queue."""
        await self.queues[priority].put(item)

    async def get(self) -> any:
        """Get highest priority item."""
        # Check queues in priority order
        for priority in RequestPriority:
            if not self.queues[priority].empty():
                return await self.queues[priority].get()

        # All queues empty - wait for any
        tasks = [
            asyncio.create_task(queue.get())
            for queue in self.queues.values()
        ]

        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()

        return done.pop().result()
```

