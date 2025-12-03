# 05. MCP Tools Interface & JSON Schema Specification

## 1. Document Purpose

- Define the set of MCP tools exposed by the Raspberry Pi MCP Server, including namespaces, naming conventions, and layering.
- Specify JSON structures (parameters and results) for each tool, together with validation rules, types, and constraints.
- Standardize error handling and versioning conventions so clients (especially AI assistants) have a stable, machine-usable contract.
- Keep this specification aligned with the functional and non-functional requirements in `01-raspberry-pi-mcp-server-requirements-specification.md`.

## 2. Naming, Conventions & Python Interface

### 2.1 Tool Naming

- Tools are named using the `namespace.operation` pattern, for example:
  - `system.get_basic_info`
  - `metrics.get_health_snapshot`
  - `gpio.write_pin`
  - `manage.update_server`
- Initial namespaces:
  - `system` – system information, reboot/shutdown, capability introspection (covers FR‑1, FR‑2, FR‑14–FR‑16, FR‑27–FR‑28).
  - `metrics` – resource and health metrics collection and querying (FR‑3–FR‑4).
  - `network` – network status and interface information.
  - `service` – systemd service management (FR‑5, FR‑7).
  - `process` – process listing, inspection, and (later) control (FR‑5–FR‑8).
  - `gpio` – GPIO and PWM control (FR‑9–FR‑10).
  - `i2c` – I2C bus access (FR‑11).
  - `camera` – camera access (FR‑13).
  - `logs` – log querying and diagnostic views (FR‑23, FR‑26).
  - `manage` – MCP server self-update, OS update wrapper tools, and server state (FR‑21–FR‑23, FR‑27).

### 2.2 v1 Tool Catalog

The v1 release is expected to implement at least the following tools. Tools marked “Phase 2+” are planned for later phases and may be stubbed or omitted in the initial implementation.

- **`system` namespace**
  - `system.get_basic_info`
  - `system.get_health_snapshot`
  - `system.reboot`
  - `system.shutdown` (optional, high-risk; must be explicitly enabled by configuration)
  - `system.get_capabilities` (capability matrix describing available hardware and server modules)

- **`metrics` namespace**
  - `metrics.get_realtime_metrics`
  - `metrics.start_sampling_job`
  - `metrics.stop_sampling_job`
  - `metrics.get_samples`

- **`network` namespace**
  - `network.get_status` (summary of interfaces, IP addresses, and basic connectivity)

- **`gpio` namespace**
  - `gpio.list_pins`
  - `gpio.configure_pin`
  - `gpio.read_pin`
  - `gpio.write_pin`
  - `gpio.set_pwm`

- **`i2c` namespace**
  - `i2c.list_buses`
  - `i2c.scan_bus`
  - `i2c.read`
  - `i2c.write`

- **`camera` namespace**
  - `camera.take_photo`

- **`service` namespace**
  - `service.list_services`
  - `service.get_status`
  - `service.control_service`
  - `service.set_enabled`

- **`process` namespace**
  - `process.list_processes`
  - `process.get_process_details`
  - `process.send_signal` (Phase 2+)

- **`logs` namespace**
  - `logs.get_recent_app_logs`
  - `logs.get_recent_audit_logs`

- **`manage` namespace**
  - `manage.get_server_status` (server version, configuration summary, self-update state)
  - `manage.update_server` (self-update to a specified channel/version)
  - `manage.preview_os_updates` / `manage.apply_os_updates` (Phase 2+, high-risk; OS-level `apt`/`apt-get` updates via a controlled wrapper, possibly surfaced as a higher-level `manage.update_os` tool)

### 2.3 Response Structure & MCP / JSON‑RPC

The external protocol follows MCP over **JSON‑RPC 2.0**. At the protocol level we do not introduce any additional `status`/`data`/`error` wrapper around JSON‑RPC.

- **Successful response (standard JSON‑RPC)**:

  ```json
  {
    "jsonrpc": "2.0",
    "id": "req-1234",
    "result": {
      "...": "tool-specific fields"
    }
  }
  ```

  The structure of the `result` object is defined by the JSON Schemas in the rest of this document for each tool, for example the result schema of `system.get_basic_info`.

- **Error response (standard JSON‑RPC with project-specific `error.data`)**:

  ```json
  {
    "jsonrpc": "2.0",
    "id": "req-1234",
    "error": {
      "code": -32000,
      "message": "Permission denied",
      "data": {
        "error_code": "permission_denied",
        "details": {
          "hint": "Optional structured extra information"
        }
      }
    }
  }
  ```

  - `error.code` and `error.message` follow JSON‑RPC 2.0 conventions.
  - `error.data` carries project-specific structured error information:
    - `error_code`: a symbolic error code such as `permission_denied` or `invalid_argument`, defined in §9.1.
    - `details`: an object with optional extra fields (for example, the problematic parameter name or resource identifier).

#### 2.3.1 Project‑Specific Conventions

- **Standard parts**:
  - `jsonrpc`, `id`, `result`, `error.code`, `error.message` are used exactly as defined by JSON‑RPC 2.0 and MCP.

- **Project conventions (extensions within the standard)**:
  - We do not wrap the tool result in an additional `{ "status": ..., "data": ... }` envelope. The JSON‑RPC `result` field directly holds the domain object defined by the tool’s result schema.
  - To carry richer structured error information, we reserve the fields `error_code` and `details` inside `error.data`:
    - This is a compliant use of JSON‑RPC (the `data` field can be any JSON object).
    - It gives clients (especially AI agents) a stable, machine-readable way to classify errors and inspect details.

Overall:

- On success: `result` is the tool-specific JSON object, following the schemas in this document.
- On failure: we use a standard JSON‑RPC `error` object, with `error.data.error_code` and `error.data.details` populated according to this document.

### 2.4 JSON Schema Conventions

All MCP tool `parameters` and `result` payloads are described using **JSON Schema Draft 7** (or a compatible version). The server uses equivalent Pydantic models to perform validation and serialization.

#### 2.4.1 General Rules

- The top level of every `parameters` and `result` structure is an object:
  - `"type": "object"`.
- Unless explicitly intended as a free-form structure, use:
  - `"additionalProperties": false`.
- Prefer precise, typed fields over generic untyped maps:
  - Use domain objects for complex structures instead of open-ended dictionaries.
- For lists of items, define a dedicated element type and then use an array of that type:
  - For example, a list of processes is an array of `ProcessInfo` objects.
- Shared structures are extracted into JSON Schema `definitions.*` and referenced via `$ref`.

#### 2.4.2 Types & Constraints

- **Strings**:
  - Use strings for names, identifiers, statuses, and short descriptions.
  - Use `"format": "date-time"` for timestamps, represented as ISO‑8601 UTC strings, e.g. `"2025-01-01T12:34:56Z"`.
  - Limit string length where appropriate (e.g. `reason` fields).
- **Numbers and integers**:
  - Always specify reasonable `minimum`/`maximum` when possible (for example, 0–100 for percentages, 1–65535 for ports, 5–3600 for sampling intervals).
  - Encode units in the field name, for example:
    - `temperature_celsius`
    - `uptime_seconds`
    - `memory_total_bytes`
- **Booleans**:
  - Use clear, intention‑revealing names such as `enabled`, `allowed`, or `has_*`.
- **Arrays**:
  - Use `items` to describe the element type (object or primitive).
  - Use `minItems` and `maxItems` as appropriate for bounded lists.
- **Dates and times**:
  - Use ISO‑8601 UTC strings with `"format": "date-time"` for absolute timestamps.
  - For durations or relative times, prefer numeric fields with explicit units (for example, `delay_seconds`).

#### 2.4.3 Optional & Nullable Fields

- Distinguish between **optional** and **nullable** fields:
  - Optional fields:
    - Not listed in the schema `required` array.
    - Callers may omit them entirely.
  - Nullable fields:
    - Declared as `"type": ["T", "null"]`, for example `"type": ["string", "null"]`.
    - Callers may set them explicitly to `null`.
- Pydantic models must mirror this distinction:
  - Optional fields use `Optional[...]` or a default of `None`.
  - This keeps JSON Schema and Python typing in sync.

#### 2.4.4 Reusable Definitions

- For structures used by multiple tools (for example health snapshots, log entries, metric samples, capability matrix entries), define reusable JSON Schema fragments and reference them:
  - Use `$ref` into `definitions.*` or an equivalent in-document model catalog.
  - Define a parallel set of Pydantic models such as `HealthSnapshot`, `LogEntry`, `MetricSample`, `Capability`.
- Reuse ensures consistent semantics for common fields and simplifies evolution for both the server and clients.

#### 2.4.5 Pagination & Filtering

- Tools that can return many items (logs, historical metrics, process lists, etc.) must explicitly define pagination and filtering fields in their parameter schemas:
  - Typical fields:
    - `limit`, `offset` or `page`, `page_size`.
    - Optional `since` / `until` timestamps (with `"format": "date-time"`).
  - Responses can optionally include pagination metadata such as `has_more` or `next_cursor` for incremental fetching.
- Pagination and filtering field names and types should be consistent across all tools that support them.

#### 2.4.6 Backward Compatibility

- Once a tool’s `parameters` or `result` schema is declared “stable”, avoid breaking changes:
  - Do not remove existing fields.
  - Do not change field types or semantics.
- When additional data is required:
  - Add new optional fields with reasonable defaults.
  - Or introduce a new tool name (for example, `system.get_basic_info_v2`) or versioned namespace, leaving the old tool intact.

#### 2.4.7 Schema ↔ Python Model Alignment

- For every tool there must be matching Pydantic models:
  - `ParametersModel`: mirrors the `parameters` schema.
  - `ResultModel`: mirrors the `result` schema.
- Model field names, types, and constraints must stay aligned with the JSON Schemas:
  - Server logic uses the models for automatic validation and serialization.
  - Tests compare models and schemas to catch accidental contract breakages.
- Any change to a tool’s schema must be accompanied by changes to the corresponding models and tests.

### 2.5 Python Tool Handler Interface

In the Python implementation, all MCP tool handlers should use a unified signature and lifecycle to simplify routing, validation, and testing.

#### 2.5.1 Handler Type & Signature

Define a shared handler type alias in `mcp_raspi.server.types`:

```python
from typing import Awaitable, Callable, Dict, Any
from mcp_raspi.server.context import ToolContext
from mcp_raspi.server.types import ToolResponse

ToolHandler = Callable[[ToolContext, Dict[str, Any]], Awaitable[ToolResponse]]
```

- `ToolContext`: carries tool name, caller identity, request ID, timestamps, and other request metadata.
- `params`: a dictionary containing JSON parameters that have already been validated against the tool’s JSON Schema (and Pydantic `ParametersModel`).
- `ToolResponse`: the result object; its structure must match the tool’s result JSON Schema and is returned directly as the JSON‑RPC `result`.

In concrete handlers, we recommend immediately deserializing `params` into the Pydantic parameters model (see §2.4.7):

```python
from typing import Dict, Any
from mcp_raspi.models.system import GetBasicInfoParams, BasicInfo
from mcp_raspi.modules.system_info import SystemInfoService
from mcp_raspi.server.context import ToolContext


async def handle_system_get_basic_info(
    ctx: ToolContext,
    params: Dict[str, Any],
) -> BasicInfo:
    parsed = GetBasicInfoParams(**params)
    service = SystemInfoService()
    return await service.get_basic_info(parsed)
```

#### 2.5.2 Registration & Dispatch

Use a `ToolRegistry` in `mcp_raspi.server.tool_router` to map tool names to handler functions:

```python
from mcp_raspi.server.registry import ToolRegistry
from mcp_raspi.tools.system import handle_system_get_basic_info
from mcp_raspi.tools.metrics import handle_metrics_get_realtime_metrics

registry = ToolRegistry()
registry.register("system.get_basic_info", handle_system_get_basic_info)
registry.register("metrics.get_realtime_metrics", handle_metrics_get_realtime_metrics)
# ...
```

Processing flow for a JSON‑RPC request:

1. Read `method` and `params` from the incoming JSON‑RPC request.
2. Look up the corresponding tool handler in `ToolRegistry`.
3. Parse and validate `params` using the tool’s Pydantic `ParametersModel` (which aligns with the JSON Schema, see §2.4).
4. Build a `ToolContext` and call `handler(ctx, params_dict)`.
5. Serialize the handler’s `ToolResponse` (typically a Pydantic model) and place it inside the JSON‑RPC `result` field.

#### 2.5.3 Error Handling Flow

- When encountering business-level errors, handlers must raise project-specific exceptions (for example, subclasses of `ToolError`) instead of constructing JSON‑RPC `error` objects directly:

  ```python
  from mcp_raspi.server.errors import ToolError

  raise ToolError(
      error_code="permission_denied",
      message="User is not allowed to write to this GPIO pin",
      details={"pin": 17},
  )
  ```

- The MCP server framework is responsible for catching these exceptions and converting them into JSON‑RPC error responses:
  - `error.code` and `error.message` are set according to JSON‑RPC and the error category (for example `invalid_argument`, `permission_denied`, `failed_precondition`).
  - `error.data.error_code` is populated with the symbolic error code defined in §9.1.
  - `error.data.details` carries additional structured information.
- This design:
  - Keeps tool handlers focused on domain logic and returning results or raising exceptions.
  - Centralizes protocol behavior in the JSON‑RPC layer, simplifying auditing and evolution.
  - Allows new error types to be introduced by updating the error mapping table and §9.1, without modifying every handler.

### 2.6 Complete JSON Request/Response Examples

This section provides complete JSON-RPC 2.0 request/response examples for key MCP tools to help implementers and AI assistants understand the exact format expected by the server.

#### 2.6.1 System Information Query

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-sys-001",
  "method": "system.get_basic_info",
  "params": {}
}
```

**Success Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-sys-001",
  "result": {
    "hostname": "raspberrypi",
    "model": "Raspberry Pi 4 Model B Rev 1.4",
    "os": "Raspberry Pi OS (64-bit)",
    "kernel": "6.1.21-v8+",
    "architecture": "aarch64",
    "serial": "10000000a1b2c3d4",
    "uptime_seconds": 86400,
    "timestamp": "2025-01-15T14:30:00Z"
  }
}
```

#### 2.6.2 GPIO Pin Control

**Request** (write to GPIO pin):
```json
{
  "jsonrpc": "2.0",
  "id": "req-gpio-002",
  "method": "gpio.write_pin",
  "params": {
    "pin": 17,
    "value": 1
  }
}
```

**Success Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-gpio-002",
  "result": {
    "pin": 17,
    "value": 1,
    "timestamp": "2025-01-15T14:30:05Z"
  }
}
```

**Error Response** (permission denied):
```json
{
  "jsonrpc": "2.0",
  "id": "req-gpio-002",
  "error": {
    "code": -32001,
    "message": "Permission denied",
    "data": {
      "error_code": "permission_denied",
      "message": "User is not allowed to write to this GPIO pin",
      "details": {
        "pin": 17,
        "required_permission": "gpio:write:17"
      }
    }
  }
}
```

#### 2.6.3 Metrics Query with Time Range

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-metrics-003",
  "method": "metrics.query_history",
  "params": {
    "metric_names": ["cpu_percent", "memory_percent"],
    "start_time": "2025-01-15T14:00:00Z",
    "end_time": "2025-01-15T14:30:00Z",
    "resolution": "1m"
  }
}
```

**Success Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-metrics-003",
  "result": {
    "metrics": {
      "cpu_percent": [
        {"timestamp": "2025-01-15T14:00:00Z", "value": 25.3},
        {"timestamp": "2025-01-15T14:01:00Z", "value": 27.1},
        {"timestamp": "2025-01-15T14:02:00Z", "value": 24.8}
      ],
      "memory_percent": [
        {"timestamp": "2025-01-15T14:00:00Z", "value": 45.2},
        {"timestamp": "2025-01-15T14:01:00Z", "value": 45.6},
        {"timestamp": "2025-01-15T14:02:00Z", "value": 46.1}
      ]
    },
    "start_time": "2025-01-15T14:00:00Z",
    "end_time": "2025-01-15T14:30:00Z",
    "resolution": "1m",
    "data_points": 30
  }
}
```

#### 2.6.4 Service Management

**Request** (start a service):
```json
{
  "jsonrpc": "2.0",
  "id": "req-svc-004",
  "method": "service.start",
  "params": {
    "service_name": "nginx"
  }
}
```

**Success Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-svc-004",
  "result": {
    "service_name": "nginx",
    "action": "start",
    "status": "active",
    "previous_status": "inactive",
    "timestamp": "2025-01-15T14:30:10Z"
  }
}
```

**Error Response** (service not found):
```json
{
  "jsonrpc": "2.0",
  "id": "req-svc-004",
  "error": {
    "code": -32002,
    "message": "Resource not found",
    "data": {
      "error_code": "not_found",
      "message": "Service 'nginx' not found on this system",
      "details": {
        "service_name": "nginx"
      }
    }
  }
}
```

#### 2.6.5 Camera Capture

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-cam-005",
  "method": "camera.capture",
  "params": {
    "width": 1920,
    "height": 1080,
    "format": "jpeg",
    "quality": 85
  }
}
```

**Success Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-cam-005",
  "result": {
    "image_data": "base64_encoded_jpeg_data_here...",
    "width": 1920,
    "height": 1080,
    "format": "jpeg",
    "size_bytes": 245678,
    "timestamp": "2025-01-15T14:30:15Z"
  }
}
```

**Error Response** (device busy):
```json
{
  "jsonrpc": "2.0",
  "id": "req-cam-005",
  "error": {
    "code": -32003,
    "message": "Resource unavailable",
    "data": {
      "error_code": "resource_exhausted",
      "message": "Camera is currently in use by another process",
      "details": {
        "device": "/dev/video0",
        "in_use_by": "motion"
      }
    }
  }
}
```

#### 2.6.6 Self-Update Check

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-upd-006",
  "method": "manage.check_for_updates",
  "params": {}
}
```

**Success Response** (update available):
```json
{
  "jsonrpc": "2.0",
  "id": "req-upd-006",
  "result": {
    "update_available": true,
    "current_version": "1.2.3",
    "latest_version": "1.3.0",
    "release_date": "2025-01-10T00:00:00Z",
    "release_notes_url": "https://github.com/example/releases/v1.3.0",
    "download_url": "https://github.com/example/releases/download/v1.3.0/package.tar.gz",
    "checksum": "sha256:abcdef1234567890..."
  }
}
```

**Success Response** (no update):
```json
{
  "jsonrpc": "2.0",
  "id": "req-upd-006",
  "result": {
    "update_available": false,
    "current_version": "1.3.0",
    "latest_version": "1.3.0",
    "last_checked": "2025-01-15T14:30:20Z"
  }
}
```

#### 2.6.7 Invalid Request Example

**Request** (invalid parameter type):
```json
{
  "jsonrpc": "2.0",
  "id": "req-err-007",
  "method": "gpio.write_pin",
  "params": {
    "pin": "seventeen",
    "value": 1
  }
}
```

**Error Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-err-007",
  "error": {
    "code": -32000,
    "message": "Invalid argument",
    "data": {
      "error_code": "invalid_argument",
      "message": "Parameter 'pin' must be an integer, got string",
      "details": {
        "parameter": "pin",
        "expected_type": "integer",
        "actual_type": "string",
        "provided_value": "seventeen"
      }
    }
  }
}
```

#### 2.6.8 Notes on JSON-RPC Format

All requests must include:
- `jsonrpc`: Always `"2.0"`
- `id`: Unique request identifier (string or number)
- `method`: Tool name in `namespace.operation` format
- `params`: Object containing tool-specific parameters

All success responses include:
- `jsonrpc`: Always `"2.0"`
- `id`: Matching the request ID
- `result`: Object containing tool-specific results

All error responses include:
- `jsonrpc`: Always `"2.0"`
- `id`: Matching the request ID (or `null` for parse errors)
- `error`: Object with:
  - `code`: JSON-RPC error code (negative integer)
  - `message`: Human-readable error summary
  - `data`: Object with:
    - `error_code`: Symbolic error code from §9.1
    - `message`: Detailed error message
    - `details`: Tool-specific error context

## 3. System Namespace (`system.*`)

### 3.1 `system.get_basic_info`

**Purpose**: Return basic hardware and software information about the device.

**Parameters schema**:

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

**Result schema** (simplified example, matches the `BasicInfo` model):

```json
{
  "type": "object",
  "properties": {
    "hostname": { "type": "string" },
    "model": { "type": "string" },
    "cpu_arch": { "type": "string" },
    "cpu_cores": { "type": "integer", "minimum": 1 },
    "memory_total_bytes": { "type": "integer", "minimum": 0 },
    "os_name": { "type": "string" },
    "os_version": { "type": "string" },
    "kernel_version": { "type": "string" },
    "uptime_seconds": { "type": "integer", "minimum": 0 }
  },
  "required": [
    "hostname",
    "model",
    "cpu_arch",
    "cpu_cores",
    "memory_total_bytes",
    "os_name",
    "os_version",
    "kernel_version",
    "uptime_seconds"
  ],
  "additionalProperties": false
}
```

### 3.2 `system.get_health_snapshot`

**Purpose**: Return a one-shot health snapshot of the device (CPU, memory, disk, temperature, throttling flags).

**Parameters schema**: No parameters (empty object). Kept aligned with `metrics.get_realtime_metrics`.

**Result schema** (simplified example, matches the `HealthSnapshot` model):

```json
{
  "type": "object",
  "properties": {
    "timestamp": { "type": "string", "format": "date-time" },
    "cpu_usage_percent": { "type": "number", "minimum": 0, "maximum": 100 },
    "memory_used_bytes": { "type": "integer", "minimum": 0 },
    "memory_total_bytes": { "type": "integer", "minimum": 0 },
    "disk_used_bytes": { "type": "integer", "minimum": 0 },
    "disk_total_bytes": { "type": "integer", "minimum": 0 },
    "cpu_temperature_celsius": { "type": "number" },
    "throttling_flags": {
      "type": "object",
      "properties": {
        "under_voltage": { "type": "boolean" },
        "freq_capped": { "type": "boolean" },
        "throttled": { "type": "boolean" }
      },
      "required": ["under_voltage", "freq_capped", "throttled"],
      "additionalProperties": false
    }
  },
  "required": [
    "timestamp",
    "cpu_usage_percent",
    "memory_used_bytes",
    "memory_total_bytes",
    "disk_used_bytes",
    "disk_total_bytes"
  ],
  "additionalProperties": false
}
```

### 3.3 `system.reboot`

**Purpose**: Schedule a safe reboot of the device.

**Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "reason": { "type": "string", "maxLength": 200 },
    "delay_seconds": {
      "type": "integer",
      "minimum": 0,
      "maximum": 600,
      "default": 5
    }
  },
  "required": [],
  "additionalProperties": false
}
```

**Result schema**:

```json
{
  "type": "object",
  "properties": {
    "scheduled": { "type": "boolean" },
    "effective_after_seconds": { "type": "integer", "minimum": 0 }
  },
  "required": ["scheduled", "effective_after_seconds"],
  "additionalProperties": false
}
```

### 3.4 Future Extensions

- `system.shutdown`:
  - Parameters similar to `system.reboot`.
  - Requires higher privileges and is disabled by default.
  - May include a `force` flag to indicate whether forced shutdown is allowed.
- `system.get_capabilities`:
  - Returns a capability matrix enumerating supported modules, tools, and hardware (for example, presence of camera, sensors, self-update support).
  - Enables clients to adapt their behavior to the specific device.

## 4. Metrics Namespace (`metrics.*`)

### 4.1 `metrics.get_realtime_metrics`

**Purpose**: Return a real-time snapshot of metrics (similar to `system.get_health_snapshot`, but may include more dimensions or frequency).

**Parameters schema**: No parameters (empty object), kept aligned with `system.get_health_snapshot`.

**Result schema**: Same as the result of `system.get_health_snapshot` (`HealthSnapshot` model). If additional fields are added in the future, they must follow the backward-compatibility rules in §2.4.6.

### 4.2 `metrics.start_sampling_job` / `metrics.stop_sampling_job`

**Purpose**: Start or stop a background metrics sampling job.

`metrics.start_sampling_job` **Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "interval_seconds": {
      "type": "integer",
      "minimum": 5,
      "maximum": 3600
    },
    "retention_hours": {
      "type": "integer",
      "minimum": 1,
      "maximum": 168
    }
  },
  "required": ["interval_seconds"],
  "additionalProperties": false
}
```

`metrics.start_sampling_job` **Result schema** (simplified example, matches `SamplingJobStatus`):

```json
{
  "type": "object",
  "properties": {
    "job_id": { "type": "string" },
    "interval_seconds": { "type": "integer", "minimum": 5, "maximum": 3600 },
    "retention_hours": { "type": "integer", "minimum": 1, "maximum": 168 },
    "status": {
      "type": "string",
      "enum": ["created", "running", "stopped"]
    }
  },
  "required": ["job_id", "status"],
  "additionalProperties": false
}
```

`metrics.stop_sampling_job` **Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "job_id": { "type": "string" }
  },
  "required": ["job_id"],
  "additionalProperties": false
}
```

`metrics.stop_sampling_job` **Result schema**:

- May reuse the same object structure as `metrics.start_sampling_job`, representing the current status of the job (typically `stopped`).

`metrics.get_samples` queries time series samples, as described in §4.3.

### 4.3 `metrics.get_samples`

**Parameters schema** (example):

```json
{
  "type": "object",
  "properties": {
    "job_id": { "type": ["string", "null"] },
    "since": { "type": ["string", "null"], "format": "date-time" },
    "until": { "type": ["string", "null"], "format": "date-time" },
    "limit": { "type": ["integer", "null"], "minimum": 1, "maximum": 1000 }
  },
  "required": [],
  "additionalProperties": false
}
```

**Result schema** (example, matches `MetricSamplesResponse`):

```json
{
  "type": "object",
  "properties": {
    "samples": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "timestamp": { "type": "string", "format": "date-time" },
          "cpu_usage_percent": { "type": "number" },
          "memory_used_bytes": { "type": "integer" },
          "disk_used_bytes": { "type": "integer" },
          "cpu_temperature_celsius": { "type": ["number", "null"] }
        },
        "required": ["timestamp"],
        "additionalProperties": false
      }
    }
  },
  "required": ["samples"],
  "additionalProperties": false
}
```

## 5. GPIO Namespace (`gpio.*`)

### 5.1 `gpio.list_pins`

**Purpose**: List the GPIO pins that the server allows access to, with their current configuration and state.

**Parameters schema**: None (empty object).

**Result schema** (simplified example, matches `GpioPinsResponse` / `GpioPinInfo`):

```json
{
  "type": "object",
  "properties": {
    "pins": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "pin": { "type": "integer", "minimum": 1 },
          "mode": { "type": "string", "enum": ["input", "output", "alt", "unknown"] },
          "value": { "type": ["string", "null"], "enum": ["high", "low", null] },
          "allowed": { "type": "boolean" }
        },
        "required": ["pin", "mode", "allowed"],
        "additionalProperties": false
      }
    }
  },
  "required": ["pins"],
  "additionalProperties": false
}
```

### 5.2 `gpio.configure_pin`

**Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "pin": { "type": "integer", "minimum": 1 },
    "mode": { "type": "string", "enum": ["input", "output"] },
    "pull": {
      "type": "string",
      "enum": ["none", "up", "down"],
      "default": "none"
    }
  },
  "required": ["pin", "mode"],
  "additionalProperties": false
}
```

**Result schema**:

- Should return the configured pin state, using the same structure as a single entry from `gpio.list_pins` (`GpioPinInfo` object).

### 5.3 `gpio.write_pin`

**Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "pin": { "type": "integer", "minimum": 1 },
    "value": { "type": "string", "enum": ["high", "low"] },
    "duration_ms": {
      "type": ["integer", "null"],
      "minimum": 1,
      "maximum": 600000
    }
  },
  "required": ["pin", "value"],
  "additionalProperties": false
}
```

If `duration_ms` is non-null, the implementation should automatically revert the pin state after the specified duration, based on configuration (for example, restore the previous state or invert).

**Result schema**:

- May return the current state of the pin after the write (again using the `GpioPinInfo` structure), or an empty object `{}` if no additional information is needed.

### 5.4 `gpio.set_pwm`

**Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "pin": { "type": "integer", "minimum": 1 },
    "frequency_hz": { "type": "number", "minimum": 1, "maximum": 50000 },
    "duty_cycle_percent": { "type": "number", "minimum": 0, "maximum": 100 }
  },
  "required": ["pin", "frequency_hz", "duty_cycle_percent"],
  "additionalProperties": false
}
```

**Result schema**:

- Recommended: return a summary of the effective PWM state with at least the fields `pin`, `frequency_hz`, `duty_cycle_percent`.
- Alternatively, an empty object `{}` is acceptable if the status can be retrieved via `gpio.list_pins`, but the implementation and documentation must stay consistent.

## 6. I2C Namespace (`i2c.*`)

### 6.1 `i2c.list_buses` and `i2c.scan_bus`

**Purpose**: Enumerate available I2C buses and scan for devices on a bus.

`i2c.list_buses` **Parameters schema**: None (empty object).

`i2c.list_buses` **Result schema** (example, matches `I2cBusInfo` list):

```json
{
  "type": "object",
  "properties": {
    "buses": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "bus": { "type": "integer", "minimum": 0 },
          "description": { "type": ["string", "null"] }
        },
        "required": ["bus"],
        "additionalProperties": false
      }
    }
  },
  "required": ["buses"],
  "additionalProperties": false
}
```

`i2c.scan_bus` **Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "bus": { "type": "integer", "minimum": 0 }
  },
  "required": ["bus"],
  "additionalProperties": false
}
```

`i2c.scan_bus` **Result schema**:

```json
{
  "type": "object",
  "properties": {
    "bus": { "type": "integer", "minimum": 0 },
    "addresses": {
      "type": "array",
      "items": { "type": "integer", "minimum": 0, "maximum": 127 }
    }
  },
  "required": ["bus", "addresses"],
  "additionalProperties": false
}
```

### 6.2 `i2c.read` / `i2c.write`

`i2c.read` **Parameters schema** (example):

```json
{
  "type": "object",
  "properties": {
    "bus": { "type": "integer", "minimum": 0 },
    "address": { "type": "integer", "minimum": 0, "maximum": 127 },
    "register": { "type": "integer", "minimum": 0, "maximum": 255 },
    "length": { "type": "integer", "minimum": 1, "maximum": 32 }
  },
  "required": ["bus", "address", "length"],
  "additionalProperties": false
}
```

`i2c.read` **Result schema**:

```json
{
  "type": "object",
  "properties": {
    "bus": { "type": "integer", "minimum": 0 },
    "address": { "type": "integer", "minimum": 0, "maximum": 127 },
    "register": {
      "type": ["integer", "null"],
      "minimum": 0,
      "maximum": 255
    },
    "data": {
      "type": "array",
      "items": { "type": "integer", "minimum": 0, "maximum": 255 },
      "minItems": 1,
      "maxItems": 32
    }
  },
  "required": ["bus", "address", "data"],
  "additionalProperties": false
}
```

`i2c.write` **Parameters schema** (example):

```json
{
  "type": "object",
  "properties": {
    "bus": { "type": "integer", "minimum": 0 },
    "address": { "type": "integer", "minimum": 0, "maximum": 127 },
    "register": {
      "type": ["integer", "null"],
      "minimum": 0,
      "maximum": 255
    },
    "data": {
      "type": "array",
      "items": { "type": "integer", "minimum": 0, "maximum": 255 },
      "minItems": 1,
      "maxItems": 32
    }
  },
  "required": ["bus", "address", "data"],
  "additionalProperties": false
}
```

`i2c.write` **Result schema**:

- For a successful write, either:
  - Return an empty object `{}`, or
  - Return an object with confirmation information (for example, `bus`, `address`, `bytes_written`).
- The implementation and documentation must remain consistent with whichever approach is chosen.

## 7. Camera Namespace (`camera.*`)

### 7.1 `camera.take_photo`

**Purpose**: Capture a photo using a local camera and save it to a configured directory.

**Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "resolution": {
      "type": "string",
      "enum": ["640x480", "1280x720", "1920x1080"],
      "default": "1280x720"
    },
    "format": {
      "type": "string",
      "enum": ["jpeg", "png"],
      "default": "jpeg"
    }
  },
  "required": [],
  "additionalProperties": false
}
```

**Result schema**:

```json
{
  "type": "object",
  "properties": {
    "file_path": { "type": "string" },
    "public_url": { "type": ["string", "null"] }
  },
  "required": ["file_path"],
  "additionalProperties": false
}
```

Security considerations:

- To avoid path traversal and related attacks, the server must generate `file_path` and restrict it to a configured root directory.
- Clients must not be allowed to provide raw file paths or path fragments.

## 8. Manage Namespace (`manage.*`)

### 8.1 `manage.get_server_status`

**Purpose**: Return the MCP server version, configuration summary, start time, and self-update status for introspection and operations.

**Parameters schema**: None (empty object).

**Result schema** (example, matches `ServerStatus`):

```json
{
  "type": "object",
  "properties": {
    "version": { "type": "string" },
    "build": { "type": ["string", "null"] },
    "started_at": { "type": "string", "format": "date-time" },
    "config_summary": {
      "type": "object",
      "additionalProperties": true
    },
    "last_update": {
      "$ref": "#/definitions/common_status"
    }
  },
  "required": ["version", "started_at"],
  "additionalProperties": false
}
```

### 8.2 `manage.update_server`

**Purpose**: Trigger an update of the MCP server itself (for example, via `uv`/Python packaging and the configured update channel).

**Parameters schema**:

```json
{
  "type": "object",
  "properties": {
    "channel": {
      "type": ["string", "null"],
      "enum": ["stable", "beta", null],
      "default": "stable"
    },
    "target_version": {
      "type": ["string", "null"]
    }
  },
  "required": [],
  "additionalProperties": false
}
```

**Result schema** (example, matches `UpdateStatus`):

```json
{
  "type": "object",
  "properties": {
    "old_version": { "type": ["string", "null"] },
    "new_version": { "type": ["string", "null"] },
    "status": {
      "$ref": "#/definitions/common_status"
    }
  },
  "required": ["status"],
  "additionalProperties": false
}
```

### 8.3 `manage.update_os` (dangerous)

- High‑risk tool; only available when explicitly enabled in configuration.
- Likely to be split into two tools:
  - `manage.preview_os_updates` – preview the OS updates that would be applied.
  - `manage.apply_os_updates` – actually apply the OS updates.
- Both tools must clearly surface the risk and require strong authorization; the configuration and security documents (04 and 10) describe additional safeguards.

### 8.4 Common Status Object

When multiple tools need to return the status of a long‑running operation or update, they should reuse a common status object with the following schema:

```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["pending", "running", "succeeded", "failed"]
    },
    "started_at": { "type": ["string", "null"], "format": "date-time" },
    "finished_at": { "type": ["string", "null"], "format": "date-time" },
    "progress_percent": {
      "type": ["number", "null"],
      "minimum": 0,
      "maximum": 100
    },
    "message": { "type": ["string", "null"] }
  },
  "required": ["status"],
  "additionalProperties": false
}
```

In the full JSON Schema document, this object can be extracted into `definitions.common_status` and reused via `$ref` from tools such as:

- `manage.update_server`
- `manage.preview_os_updates`
- `manage.apply_os_updates`
- `metrics.start_sampling_job`

## 9. Error Codes & Versioning

### 9.1 Standard Error Codes

To help clients (especially AI models) understand and handle errors, we define a stable set of symbolic error codes and map them to JSON‑RPC error fields.

#### 9.1.1 Symbolic Error Codes

Recommended symbolic codes (extendable, but semantics should remain stable):

- `invalid_argument` – invalid or missing arguments (for example type mismatch, value out of range).
- `permission_denied` – caller is authenticated but lacks permission for the operation.
- `unauthenticated` – caller is not authenticated (missing or invalid credentials).
- `not_found` – requested resource does not exist (for example sampling job, service, or process).
- `failed_precondition` – preconditions are not satisfied (for example hardware not ready, GPIO pin not configured).
- `resource_exhausted` – resource limits exceeded (for example rate limit triggered, insufficient disk space).
- `unavailable` – dependency is temporarily unavailable (for example privileged agent offline, system service unreachable).
- `internal` – unexpected internal error (bug or unknown exception).

These symbolic codes are placed in `error.data.error_code` so that clients can classify and handle errors programmatically.

#### 9.1.2 Mapping to JSON‑RPC Error Codes

JSON‑RPC 2.0 defines several reserved error codes (for example `-32600`, `-32601`, `-32602`, `-32603`). We use them as follows:

- Protocol-level errors handled by the JSON‑RPC framework use the standard codes:
  - `-32600` – Invalid Request (malformed JSON‑RPC request).
  - `-32601` – Method not found (unknown tool name).
  - `-32602` – Invalid params (parameters do not match the schema).
  - `-32603` – Internal error (internal framework failure).
- Business-level errors produced by tools or domain logic use custom codes in the `-32000` range. A suggested mapping:

  | `error.data.error_code` | JSON‑RPC `error.code` |
  |-------------------------|-----------------------|
  | `invalid_argument`      | `-32602` or `-32000`  |
  | `permission_denied`     | `-32001`              |
  | `unauthenticated`       | `-32002`              |
  | `not_found`             | `-32003`              |
  | `failed_precondition`   | `-32004`              |
  | `resource_exhausted`    | `-32005`              |
  | `unavailable`           | `-32006`              |
  | `internal`              | `-32099`              |

- For parameter errors, prefer the standard `-32602` while still setting `error.data.error_code` to `invalid_argument` so clients can rely on the symbolic code.

Implementation guidance:

- Maintain a centralized mapping table in `mcp_raspi.server.errors` that maps internal `ToolError.error_code` values to JSON‑RPC `error.code` and default messages.

#### 9.1.3 Python Exceptions & Error Handling

Define a base exception type:

```python
class ToolError(Exception):
    def __init__(self, error_code: str, message: str, details: dict | None = None):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message)
```

Tool implementations raise `ToolError` (or subclasses) when errors occur. The top-level JSON‑RPC layer then:

- Looks up the appropriate `error.code` using the mapping table.
- Uses `ToolError.message` (or a standardized message template) for `error.message`.
- Populates `error.data` with:
  - `error_code`: the symbolic code such as `permission_denied`.
  - `details`: the key-value details from `ToolError.details`.

For severe internal exceptions (uncaught Python exceptions), the top-level layer should:

- Map them to the `internal` error code.
- Log full stack traces for debugging and analysis (see logging design in document 09).

### 9.2 API Versioning

- Initially, API versioning is managed through tool names and documentation rather than a global version field:
  - Stable tools use simple names such as `system.get_basic_info`.
  - Experimental tools are marked as alpha/beta in this document and in the capability matrix.
- When a tool requires a breaking change (violating the compatibility strategy in §2.4.6), we must:
  - Introduce a new tool name (for example, `system.get_basic_info_v2`) or a new namespace prefix (for example, `system_v2.get_basic_info`).
  - Keep the old tool available for a deprecation period to allow clients to migrate.
- Implementation recommendations:
  - Store stability information (alpha/beta/stable) in configuration or metadata used by `system.get_capabilities` so clients can discover it.
  - Maintain a clear changelog for tools, documenting additions, deprecations, and replacements.
  - In CI and tests, enforce stricter compatibility and coverage expectations for tools marked as stable.


---

<!-- Merged from 05-addendum-detailed-schemas.md -->

---

## 1. Network Tools (Enhanced)

### 1.1 `system.get_network_info` (Phase 1 - Enhanced)

**Full Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "interfaces": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string", "description": "Interface name (e.g., eth0, wlan0)"},
          "mac_address": {"type": "string", "description": "MAC address", "pattern": "^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"},
          "mtu": {"type": "integer", "description": "Maximum transmission unit"},
          "state": {"type": "string", "enum": ["up", "down", "unknown"]},
          "ipv4_addresses": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "address": {"type": "string", "description": "IPv4 address"},
                "netmask": {"type": "string", "description": "Netmask"},
                "broadcast": {"type": "string", "description": "Broadcast address"}
              },
              "required": ["address"]
            }
          },
          "ipv6_addresses": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "address": {"type": "string", "description": "IPv6 address"},
                "prefix_length": {"type": "integer", "description": "Prefix length", "minimum": 0, "maximum": 128},
                "scope": {"type": "string", "enum": ["global", "link", "host"]}
              },
              "required": ["address"]
            }
          },
          "statistics": {
            "type": "object",
            "properties": {
              "bytes_sent": {"type": "integer", "minimum": 0},
              "bytes_recv": {"type": "integer", "minimum": 0},
              "packets_sent": {"type": "integer", "minimum": 0},
              "packets_recv": {"type": "integer", "minimum": 0},
              "errors_in": {"type": "integer", "minimum": 0},
              "errors_out": {"type": "integer", "minimum": 0},
              "drops_in": {"type": "integer", "minimum": 0},
              "drops_out": {"type": "integer", "minimum": 0}
            }
          }
        },
        "required": ["name", "mac_address", "state"]
      }
    },
    "default_gateway": {
      "type": "object",
      "properties": {
        "ipv4": {"type": "string", "description": "Default IPv4 gateway"},
        "ipv6": {"type": "string", "description": "Default IPv6 gateway"},
        "interface": {"type": "string", "description": "Interface name"}
      }
    },
    "dns_servers": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Configured DNS servers"
    }
  },
  "required": ["interfaces"]
}
```

### 1.2 `system.get_detailed_network_info` (Phase 2+)

**Parameters**:
```json
{
  "type": "object",
  "properties": {
    "include_routing_table": {"type": "boolean", "default": false},
    "include_connections": {"type": "boolean", "default": false},
    "connection_state_filter": {
      "type": "array",
      "items": {"type": "string", "enum": ["ESTABLISHED", "LISTEN", "TIME_WAIT", "CLOSE_WAIT"]}
    }
  }
}
```

**Response Schema**:
```json
{
  "type": "object",
  "properties": {
    "interfaces": {"$ref": "#/definitions/interfaces"},
    "routing_table": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "destination": {"type": "string"},
          "gateway": {"type": "string"},
          "netmask": {"type": "string"},
          "flags": {"type": "string"},
          "metric": {"type": "integer"},
          "interface": {"type": "string"}
        }
      }
    },
    "connections": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "protocol": {"type": "string", "enum": ["tcp", "udp", "tcp6", "udp6"]},
          "local_address": {"type": "string"},
          "local_port": {"type": "integer"},
          "remote_address": {"type": "string"},
          "remote_port": {"type": "integer"},
          "state": {"type": "string"},
          "pid": {"type": "integer", "description": "Process ID (if available)"}
        }
      }
    }
  }
}
```

---

## 2. Service & Process Schemas (Complete)

### 2.1 ServiceSummary Schema

```json
{
  "type": "object",
  "properties": {
    "name": {"type": "string", "description": "Service name"},
    "display_name": {"type": "string", "description": "Human-readable name"},
    "status": {"type": "string", "enum": ["active", "inactive", "activating", "deactivating", "failed"]},
    "sub_status": {"type": "string", "enum": ["running", "exited", "dead", "failed", "waiting"]},
    "enabled": {"type": "boolean", "description": "Is service enabled (autostart)"},
    "preset": {"type": "string", "enum": ["enabled", "disabled", "static", "masked"], "description": "Preset state"},
    "pid": {"type": "integer", "description": "Main PID (if running)", "minimum": 0},
    "memory_bytes": {"type": "integer", "description": "Memory usage in bytes", "minimum": 0},
    "cpu_percent": {"type": "number", "description": "CPU usage percentage", "minimum": 0, "maximum": 100},
    "uptime_seconds": {"type": "integer", "description": "Seconds since service started", "minimum": 0},
    "restart_count": {"type": "integer", "description": "Number of restarts", "minimum": 0},
    "unit_file_state": {"type": "string", "enum": ["enabled", "enabled-runtime", "linked", "linked-runtime", "masked", "masked-runtime", "static", "disabled", "invalid"]},
    "description": {"type": "string", "description": "Service description"},
    "can_start": {"type": "boolean"},
    "can_stop": {"type": "boolean"},
    "can_reload": {"type": "boolean"}
  },
  "required": ["name", "status", "enabled"]
}
```

### 2.2 ServiceDetail Schema (for get_status)

Extends ServiceSummary with:

```json
{
  "allOf": [
    {"$ref": "#/definitions/ServiceSummary"},
    {
      "type": "object",
      "properties": {
        "unit_file_path": {"type": "string"},
        "fragment_path": {"type": "string"},
        "exec_start": {"type": "array", "items": {"type": "string"}},
        "exec_stop": {"type": "array", "items": {"type": "string"}},
        "working_directory": {"type": "string"},
        "user": {"type": "string"},
        "group": {"type": "string"},
        "environment": {"type": "object", "additionalProperties": {"type": "string"}},
        "restart_policy": {"type": "string"},
        "dependencies": {
          "type": "object",
          "properties": {
            "requires": {"type": "array", "items": {"type": "string"}},
            "wants": {"type": "array", "items": {"type": "string"}},
            "required_by": {"type": "array", "items": {"type": "string"}},
            "wanted_by": {"type": "array", "items": {"type": "string"}},
            "after": {"type": "array", "items": {"type": "string"}},
            "before": {"type": "array", "items": {"type": "string"}}
          }
        },
        "recent_logs": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "timestamp": {"type": "string", "format": "date-time"},
              "level": {"type": "string"},
              "message": {"type": "string"}
            }
          },
          "description": "Last 10 log lines from journald"
        }
      }
    }
  ]
}
```

### 2.3 ProcessSummary Schema

```json
{
  "type": "object",
  "properties": {
    "pid": {"type": "integer", "minimum": 1},
    "name": {"type": "string", "description": "Process name"},
    "cmdline": {"type": "array", "items": {"type": "string"}, "description": "Command line arguments"},
    "exe": {"type": "string", "description": "Executable path"},
    "cwd": {"type": "string", "description": "Current working directory"},
    "status": {"type": "string", "enum": ["running", "sleeping", "disk-sleep", "stopped", "zombie", "idle"]},
    "username": {"type": "string", "description": "User running the process"},
    "create_time": {"type": "number", "description": "Unix timestamp when process started"},
    "cpu_percent": {"type": "number", "minimum": 0, "description": "CPU usage percentage"},
    "memory_percent": {"type": "number", "minimum": 0, "maximum": 100, "description": "Memory usage as % of total"},
    "memory_rss": {"type": "integer", "minimum": 0, "description": "Resident set size in bytes"},
    "memory_vms": {"type": "integer", "minimum": 0, "description": "Virtual memory size in bytes"},
    "num_threads": {"type": "integer", "minimum": 1, "description": "Number of threads"},
    "ppid": {"type": "integer", "minimum": 0, "description": "Parent process ID"},
    "nice": {"type": "integer", "description": "Nice value (-20 to 19)"}
  },
  "required": ["pid", "name", "status"]
}
```

### 2.4 ProcessDetail Schema (for get_info)

Extends ProcessSummary with:

```json
{
  "allOf": [
    {"$ref": "#/definitions/ProcessSummary"},
    {
      "type": "object",
      "properties": {
        "io_counters": {
          "type": "object",
          "properties": {
            "read_count": {"type": "integer", "minimum": 0},
            "write_count": {"type": "integer", "minimum": 0},
            "read_bytes": {"type": "integer", "minimum": 0},
            "write_bytes": {"type": "integer", "minimum": 0}
          }
        },
        "open_files": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "path": {"type": "string"},
              "fd": {"type": "integer"},
              "mode": {"type": "string"}
            }
          }
        },
        "connections": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "fd": {"type": "integer"},
              "family": {"type": "string", "enum": ["AF_INET", "AF_INET6", "AF_UNIX"]},
              "type": {"type": "string", "enum": ["SOCK_STREAM", "SOCK_DGRAM"]},
              "local_address": {"type": "string"},
              "local_port": {"type": "integer"},
              "remote_address": {"type": "string"},
              "remote_port": {"type": "integer"},
              "status": {"type": "string"}
            }
          }
        },
        "memory_maps": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "path": {"type": "string"},
              "rss": {"type": "integer"},
              "size": {"type": "integer"},
              "perms": {"type": "string"}
            }
          }
        },
        "environment": {
          "type": "object",
          "additionalProperties": {"type": "string"},
          "description": "Environment variables (filtered for sensitive data)"
        },
        "cpu_times": {
          "type": "object",
          "properties": {
            "user": {"type": "number", "description": "User mode CPU time"},
            "system": {"type": "number", "description": "System mode CPU time"}
          }
        }
      }
    }
  ]
}
```

---

## 3. Tool Versioning Strategy (Phase 2+)

### 3.1 Versioning Approach

**Tool Interface Versioning**:
- Each tool namespace has a version (e.g., `system@1`, `gpio@1`)
- Tool names can include version: `system.get_basic_info@2`
- Default to latest version if not specified
- Maintain backward compatibility for at least N-1 version

**Version Negotiation**:

Client can query supported versions:
```json
{
  "method": "manage.get_capabilities",
  "params": {}
}
```

Response:
```json
{
  "result": {
    "server_version": "1.2.3",
    "api_version": "1.0",
    "tool_namespaces": {
      "system": {"versions": ["1"], "default": "1"},
      "metrics": {"versions": ["1"], "default": "1"},
      "gpio": {"versions": ["1", "2"], "default": "2"}
    },
    "capabilities": {
      "gpio.event_detection": false,
      "camera.video_recording": false
    }
  }
}
```

### 3.2 Breaking Changes Policy

**What constitutes a breaking change**:
- Removing a tool
- Removing a parameter
- Changing a required parameter to have different validation
- Changing response schema structure (not just adding fields)

**What is NOT a breaking change**:
- Adding new optional parameters
- Adding new fields to responses
- Adding new tools
- Fixing bugs

**Migration path**:
- Announce deprecation at least one version ahead
- Support N-1 versions concurrently
- Document migration in release notes

---

## 4. Network Metrics (Document 06 Extension)

### 4.1 Network Interface Metrics

Added to `system.get_health_snapshot`:

```json
{
  "network": {
    "interfaces": {
      "<interface_name>": {
        "bytes_sent_per_sec": 15420.5,
        "bytes_recv_per_sec": 234567.8,
        "packets_sent_per_sec": 125.3,
        "packets_recv_per_sec": 450.2,
        "error_rate_percent": 0.001,
        "drop_rate_percent": 0.0,
        "utilization_percent": 12.5
      }
    },
    "total_bandwidth_mbps": {"up": 10.2, "down": 98.5}
  }
}
```

### 4.2 Disk I/O Metrics

Added to `system.get_health_snapshot`:

```json
{
  "disk_io": {
    "devices": {
      "mmcblk0": {
        "read_bytes_per_sec": 512000,
        "write_bytes_per_sec": 128000,
        "read_iops": 45,
        "write_iops": 12,
        "busy_percent": 15.5,
        "queue_depth": 2
      }
    },
    "total": {
      "read_mb_per_sec": 0.5,
      "write_mb_per_sec": 0.125
    }
  }
}
```

**Why important for Raspberry Pi**:
- SD card wear monitoring (write amplification detection)
- Performance bottleneck identification
- Early warning of SD card failure

### 4.3 Temperature Source Fallback Chain

**Priority order for temperature reading**:

1. **Primary**: `/sys/class/thermal/thermal_zone0/temp` (CPU thermal zone)
   - Most reliable on Raspberry Pi
   - Returns millidegrees Celsius

2. **Fallback 1**: `vcgencmd measure_temp` (VideoCore GPU temp)
   - Available if vcgencmd is present
   - Parse output: `temp=47.2'C`

3. **Fallback 2**: `/sys/class/hwmon/hwmon*/temp*_input`
   - Hardware monitoring interface
   - May have multiple sensors

4. **Fallback 3**: `psutil.sensors_temperatures()`
   - Cross-platform fallback
   - May not be available on all systems

**Implementation**:
```python
async def get_cpu_temperature() -> Optional[float]:
    """
    Get CPU temperature in Celsius.
    Returns None if no temperature source available.
    """
    # Try thermal zone first
    try:
        temp_mC = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        return float(temp_mC) / 1000.0
    except (FileNotFoundError, ValueError, PermissionError):
        pass

    # Try vcgencmd
    try:
        result = await asyncio.create_subprocess_exec(
            "vcgencmd", "measure_temp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        match = re.match(r"temp=([0-9.]+)'C", stdout.decode())
        if match:
            return float(match.group(1))
    except (FileNotFoundError, ValueError):
        pass

    # Try hwmon
    for hwmon_path in Path("/sys/class/hwmon").glob("hwmon*/temp*_input"):
        try:
            temp_mC = hwmon_path.read_text().strip()
            return float(temp_mC) / 1000.0
        except (ValueError, PermissionError):
            continue

    # Try psutil as last resort
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            return temps[list(temps.keys())[0]][0].current
    except AttributeError:
        pass

    return None
```

---

## 5. Process Filtering Examples (Document 07 Extension)

### 5.1 Common Filter Patterns

**Filter by user**:
```json
{
  "method": "process.list_processes",
  "params": {
    "filter": {
      "username": "pi"
    },
    "limit": 50
  }
}
```

**Filter by name pattern**:
```json
{
  "params": {
    "filter": {
      "name_pattern": "python*"
    }
  }
}
```

**Filter by CPU/memory threshold**:
```json
{
  "params": {
    "filter": {
      "min_cpu_percent": 5.0,
      "min_memory_mb": 100
    },
    "sort_by": "cpu_percent",
    "sort_order": "desc"
  }
}
```

**Filter by status**:
```json
{
  "params": {
    "filter": {
      "status": ["running", "sleeping"]
    }
  }
}
```

### 5.2 Pagination Examples

**First page**:
```json
{
  "params": {
    "limit": 20,
    "offset": 0
  }
}
```

Response includes total count:
```json
{
  "result": {
    "processes": [/* ... */],
    "total_count": 156,
    "returned_count": 20,
    "has_more": true
  }
}
```

**Next page**:
```json
{
  "params": {
    "limit": 20,
    "offset": 20
  }
}
```

---

## 6. Service Dependency Handling (Document 07 Extension)

### 6.1 Dependency Validation

Before stopping/disabling a service, check if other running services depend on it:

**Enhanced `service.control_service` validation**:

```python
async def validate_service_stop(service_name: str) -> tuple[bool, list[str]]:
    """
    Check if stopping this service would break dependencies.
    Returns (safe_to_stop, list_of_dependent_services).
    """
    # Get services that Require or Want this service
    dependents = await get_dependent_services(service_name)

    # Filter to only those that are currently active
    active_dependents = [
        dep for dep in dependents
        if await is_service_active(dep)
    ]

    return (len(active_dependents) == 0, active_dependents)
```

**Error response when dependencies exist**:
```json
{
  "error": {
    "code": "failed_precondition",
    "message": "Cannot stop service 'dbus' because 3 active services depend on it",
    "details": {
      "dependent_services": ["NetworkManager", "bluetooth", "avahi-daemon"],
      "suggestion": "Stop dependent services first, or use force=true to override"
    }
  }
}
```

**Force override** (admin only):
```json
{
  "method": "service.control_service",
  "params": {
    "service_name": "dbus",
    "action": "stop",
    "force": true,
    "confirm_breaking_dependencies": true
  }
}
```

### 6.2 systemd Unit File Validation (Phase 2+)

Before enabling a service, validate its unit file:

```json
{
  "method": "service.validate_unit_file",
  "params": {
    "service_name": "my-custom.service"
  }
}
```

Response:
```json
{
  "result": {
    "valid": true,
    "warnings": [
      "Service does not have Restart= directive",
      "Missing Description="
    ],
    "errors": [],
    "can_enable": true
  }
}
```

Validation checks:
- Unit file syntax (via `systemd-analyze verify`)
- Required sections present ([Unit], [Service], [Install])
- ExecStart is valid and executable exists
- User/Group exist if specified
- WorkingDirectory exists
- Dependencies can be resolved

---

**Document Version**: 1.0
**Last Updated**: 2025-12-03
**Status**: Addendum to Doc 05
**Phase Coverage**: Phase 1 (enhanced schemas) + Phase 2+ (preliminary designs)
