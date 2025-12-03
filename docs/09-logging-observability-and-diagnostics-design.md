# 09. Logging, Observability & Diagnostics Design

## 1. Document Purpose

- Define the logging, metrics, and diagnostics strategy for the Raspberry Pi MCP Server.
- Explain how logs and metrics are used to observe system health and troubleshoot issues.
- Coordinate with security and testing documents to support auditing and quality assurance.

This document is aligned with:

- `01-raspberry-pi-mcp-server-requirements-specification.md` – logging/audit requirements (FR‑23, FR‑26, NFR‑logging).
- `02-raspberry-pi-mcp-server-high-level-architecture-design.md` – overall architecture and IPC.
- `04-security-oauth-integration-and-access-control-design.md` – roles, audit logging, and security posture.
- `05-mcp-tools-interface-and-json-schema-specification.md` – tool schemas, error codes, and logs tools.
- `06`–`08` – module designs (system info/metrics, service/process management, device control).
- `10`–`11` – self-update behavior, testing and sandbox strategy.
- `14-configuration-reference-and-examples.md` – central configuration (`logging.*`, `tools.logs.*`).

## 2. Logging Architecture

### 2.1 Log Categories

We distinguish three logical log categories; implementation may map them to loggers/handlers:

- **Application Logs**:
  - Module-level events:
    - startup/shutdown;
    - configuration loading;
    - warnings and errors;
    - notable but non-security-sensitive operational information.
- **Audit Logs**:
  - MCP tool invocations:
    - especially privileged operations (device control, power, updates, service control).
  - Security-related events:
    - authentication and authorization decisions (pass/fail);
    - configuration changes affecting security or operational risk.
- **Diagnostics Logs**:
  - Debug information:
    - stack traces for unexpected exceptions;
    - performance traces;
    - temporary instrumentation during investigations.
  - Typically only enabled at higher log levels or in debug mode.

### 2.2 Log Format & Structure

We recommend structured JSON logs (JSON Lines format: one JSON object per line), with fields:

- `timestamp` – ISO‑8601 UTC timestamp, e.g. `"2025-01-01T12:34:56Z"`.
- `level` – log level, e.g. `"debug"`, `"info"`, `"warn"`, `"error"`.
- `module` – module or subsystem name.
- `message` – human-readable text.
- `fields` – additional contextual key/value data, such as:
  - `request_id`, `tool_name`, `user_id`, `caller_role`, `client_ip`.
  - error codes and other structured attributes.

Example application log entry:

```json
{
  "timestamp": "2025-01-01T12:34:56Z",
  "level": "info",
  "module": "gpio",
  "message": "Pin state updated",
  "fields": {
    "pin": 17,
    "value": "high",
    "request_id": "req-1234"
  }
}
```

### 2.3 Log Destinations

Default local file layout:

- Application logs:
  - `/var/log/mcp-raspi/app.log`
- Audit logs:
  - `/var/log/mcp-raspi/audit.log`

Options and future extensions:

- System logging integration:
  - Journald integration for unified collection and rotation.
- Remote log collection (Phase 2+):
  - Shipping logs to an external system (e.g. via syslog or an agent).
  - Phase 1 focuses on well-structured local logs; remote targets can be added later.

Log rotation and retention:

- May be handled either by:
  - System-wide tooling (logrotate/journald), or
  - Internal rotation (for example Python’s `RotatingFileHandler`) when system tools are unavailable.
- Document 14 contains configuration keys for optional rotation/retention limits.

## 3. Metrics & Tracing

### 3.1 Metrics

Metrics should allow both high-level health monitoring and more detailed troubleshooting. They include:

- MCP request-level metrics:
  - Request counts by tool and outcome.
  - Latency distributions (for example P50/P90/P99) per tool.
- System metrics:
  - CPU, memory, disk, and network metrics provided by the System & Metrics module (document 06).
- Module-specific metrics:
  - Self-update:
    - success/failure counts and rates.
  - Privileged agent:
    - call counts;
    - error rates by error_code.
  - Device control:
    - counts of GPIO/I2C/camera operations by type and outcome.

Labeling recommendation (for internal metrics representation):

- `tool_name` – e.g. `system.get_health_snapshot`.
- `status` – `ok` or `error`.
- `error_code` – e.g. `permission_denied` (only set on errors).
- `caller_role` – `viewer`, `operator`, or `admin`.

The exact metrics backend is left flexible in Phase 1:

- Simple in-memory counters and histograms may suffice.
- Integration with Prometheus/OpenTelemetry can be added in Phase 2+.

### 3.2 Tracing (Optional)

Request-level tracing is optional but recommended for complex troubleshooting:

- For each MCP request:
  - Generate a unique request ID (if not provided by the client).
  - Include this `request_id` in logs, audit entries, and internal calls.
- This allows:
  - Correlating events across modules and between MCP server and privileged agent.

Future (Phase 2+):

- If integrating a tracing system (for example OpenTelemetry):
  - Use `request_id` as a bridge to full distributed traces.

### 3.3 Python Logging & Audit Interfaces

In `mcp_raspi.logging`, define core utilities:

```python
from typing import Any, Dict
from mcp_raspi.server.context import ToolContext


def get_logger(module: str):
    ...


class AuditLogger:
    def log_tool_call(
        self,
        ctx: ToolContext,
        status: str,
        error_code: str | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> None: ...
```

Usage expectations:

- MCP tool handlers must ensure that `AuditLogger.log_tool_call` is invoked:
  - On completion of each tool call (success or failure).
  - With:
    - `status` set to `"ok"` or `"error"`.
    - `error_code` set to a symbolic code (document 05 §9.1) when applicable.
    - `extra` carrying additional fields (for example `danger_level`, `resource_id`, `update_channel`).

Implementation details are elaborated in §8.2.

## 4. Diagnostics Features

### 4.1 Health Check

Provide internal health-check functions and/or endpoints (primarily for operations, not for public exposure):

- MCP server health:
  - Thread count, event loop responsiveness, task queue length (if applicable).
  - Recent critical errors or repeated failures.
- Privileged agent connectivity:
  - IPC connection status and last successful call timestamp.
- Dependencies:
  - Configuration file readability.
  - Log directory writability.
  - Metrics storage health (for example SQLite accessibility).

Health-check outputs can be:

- Exposed via a local-only HTTP endpoint or internal tool.
- Returned as part of a `system.get_capabilities` or dedicated diagnostics tool in Phase 2+.

### 4.2 Logs & Metrics Query

Phase 1 requires limited but useful log query capabilities to aid troubleshooting from an AI client:

- `logs.get_recent_app_logs`:
  - Returns a window of recent application log entries with filters.
- `logs.get_recent_audit_logs`:
  - Returns recent audit log entries for tracking tool calls and privileged operations.

Both tools:

- Must obey:
  - Role-based access control (for example only `admin` can read audit logs).
  - Configurable limits:
    - `limit` on number of entries.
    - A maximum time window (for example last N days).
- Should follow the JSON Schemas in document 05 (parameters and results).

Metrics:

- Are primarily surfaced via:
  - `system.get_health_snapshot` / `metrics.get_realtime_metrics`.
  - `metrics.get_samples`.
- Additional internal metrics exports (for example for Prometheus) may be Phase 2+.

## 5. Log & Metric Content Guidelines

### 5.1 Common Fields

Standard fields that should appear in logs and metrics where applicable:

- Identity:
  - `user_id` – stable identifier for the caller (if known).
  - `caller_role` – `viewer`, `operator`, `admin`.
  - `source` / `client_ip` – where the request originated from, if available.
- Request:
  - `request_id` – unique per JSON‑RPC/MCP request.
  - `tool_name` – e.g. `system.reboot`, `gpio.write_pin`.
  - `danger_level` – classification of operation risk:
    - `read_only`, `safe_control`, `admin` (as defined in document 04).
- Outcome:
  - `status` – `ok` or `error`.
  - `error_code` – symbolic error code (document 05 §9.1).
  - `duration_ms` – optional; execution time of the tool or operation.
- Context-specific fields:
  - For example `pin`, `bus`, `unit_name`, `job_id`, `update_channel`.

These fields:

- Must be consistently populated in:
  - Audit logs.
  - Relevant application logs.
  - Metrics where applicable.

### 5.2 Sensitive Data Handling

Some data must not be logged in plain form:

- Secrets:
  - OAuth/Cloudflare access tokens.
  - API keys, passwords, private keys.
- Personally identifiable information (PII) beyond what is necessary for auditing.

Logging guidelines:

- Do not log:
  - Raw tokens, credentials, or full secrets.
- If logging is necessary for debugging:
  - Log only prefixes/suffixes, e.g. first 4 and last 4 characters.
  - Mark them as masked, e.g. `"token": "abcd...wxyz"`.
- The JSON formatter should:
  - Implement basic masking for fields whose keys suggest secrets (`token`, `secret`, `password`, etc.).

### 5.3 Error Codes & Message Patterns

Error codes:

- Use the symbolic error codes from document 05 §9.1:
  - `invalid_argument`, `permission_denied`, `unauthenticated`, `not_found`,
  - `failed_precondition`, `resource_exhausted`, `unavailable`, `internal`.
- Ensure:
  - `error.data.error_code` in JSON‑RPC errors matches these.
  - Log entries include `fields.error_code` mirroring the same value.

Message patterns:

- For common failure modes, define standardized log message templates and helpers, for example:
  - Privileged agent unavailable or timed out.
  - Configuration load failure.
  - Log directory/file not writable.
  - Self-update or rollback failure.
  - Dangerous operation rejected by policy (reboot/shutdown/OS update/service control).
- Modules should use shared helpers for these cases:
  - This makes logs easier to parse and alert on.

## 6. Python Logging & Audit Implementation

### 6.1 Core Logging Module

In `mcp_raspi.logging` implement:

- `configure_logging(app_config: AppConfig) -> None`:
  - Read logging-related settings from `AppConfig.logging` (see document 14 and §6.3).
  - Configure:
    - Application logger:
      - For example `logging.getLogger("mcp_raspi.app")`.
    - Diagnostics/debug logging:
      - Can reuse the application logger with different log levels.
    - Optional stdout/journald handler:
      - Enabled for development or container deployments.
  - For file handlers:
    - Use a JSON formatter that emits the fields as in §2.2.

- `get_logger(module: str) -> logging.Logger`:
  - Returns a logger with module metadata attached:
    - Use `LoggerAdapter` or inject `module` into `fields`.
  - All business modules should obtain loggers via this function instead of using the root logger directly.

JSON formatter:

- Convert each `LogRecord` into a structured dict:
  - `timestamp`: generated from a unified time source (UTC ISO‑8601).
  - `level`: string log level.
  - `module`: derived from logger name or adapter.
  - `message`: `record.getMessage()`.
  - `fields`: merge:
    - Standard contextual fields (`request_id`, `tool_name`, `user_id`, `caller_role`).
    - Module-specific fields (`pin`, `unit_name`, etc.).
- Implement basic masking:
  - For fields that look like secrets (for example `_token`, `_secret`, `password`), log only partial values or a placeholder.

### 6.2 Audit Logging

In `mcp_raspi.logging` implement an `AuditLogger`:

```python
from logging import Logger
from typing import Any, Dict
from mcp_raspi.server.context import ToolContext


class AuditLogger:
    def __init__(self, logger: Logger) -> None: ...

    def log_tool_call(
        self,
        ctx: ToolContext,
        status: str,
        error_code: str | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> None: ...
```

Initialization:

- In `configure_logging`:
  - Create a dedicated audit logger:
    - For example `logging.getLogger("mcp_raspi.audit")`.
  - Attach it to the audit log file path (from `AppConfig.logging.audit_log_path`).
  - Instantiate `AuditLogger` and provide it to the tool routing layer:
    - For example via dependency injection or a shared singleton.

Audit record contents:

- Required fields:
  - `timestamp`.
  - `tool_name`.
  - `status` (`ok`/`error`).
  - `error_code` (for errors).
  - `request_id`.
  - `user_id`.
  - `caller_role`.
  - `client_ip` / `source` (if available).
  - `duration_ms` (if measured).
  - `danger_level` (from tool policy).
- For high-risk operations (reboot, shutdown, self-update, OS update, service control):
  - Include additional fields:
    - Target resource identifiers (for example `unit_name`, `pin`, `bus`).
    - Key arguments (for example `channel`, `delay_seconds`, `force`).
    - Policy evaluation result (for example which rule allowed/denied).

Reliability:

- Use a dedicated audit logger and handler:
  - To isolate audit logging from application logging failures.
- On audit write failure:
  - Write a high-priority error to application logs.
  - Depending on policy:
    - For high-risk operations, consider failing fast (deny the operation).
    - For lower-risk operations, allow continuation but flag an operational issue.

### 6.3 Configuration Integration

In `AppConfig` define a logging configuration section (see document 14 for YAML representation). Example Pydantic model:

```python
from pydantic import BaseModel
from typing import Literal


class LoggingConfig(BaseModel):
    app_log_path: str = "/var/log/mcp-raspi/app.log"
    audit_log_path: str = "/var/log/mcp-raspi/audit.log"
    level: Literal["debug", "info", "warn", "error"] = "info"
    log_to_stdout: bool = True
    use_journald: bool = False
    debug_mode: bool = False
    max_bytes: int | None = None
    backup_count: int | None = None
    retention_days: int | None = None
```

Integration steps:

- Embed `LoggingConfig` in `AppConfig` as `logging`.
- Follow the configuration precedence rules (defaults → YAML → env → CLI) described in documents 02 and 14.
- On startup:
  - Construct `AppConfig`.
  - Then call `configure_logging(app_config)` before:
    - Registering tools.
    - Running long-lived tasks.
- Debug mode:
  - Allow enabling via:
    - `logging.debug_mode` in config.
    - An environment variable such as `MCP_RASPI_DEBUG=1`.

### 6.4 Log Query Tools Implementation

In `mcp_raspi.modules.logs`, implement log query services consistent with document 05:

```python
from mcp_raspi.models.logs import LogsQueryParams, LogsQueryResult


class LogQueryService:
    def get_recent_app_logs(self, params: LogsQueryParams) -> LogsQueryResult: ...

    def get_recent_audit_logs(self, params: LogsQueryParams) -> LogsQueryResult: ...
```

Implementation:

- Align `LogsQueryParams` and `LogsQueryResult` with the schemas in document 05:
  - Parameters include fields such as:
    - `limit`, `since`, `level`, `error_code`.
  - Result includes:
    - A list of structured log entries and possibly pagination info.
- File reading strategy:

  - Read from `AppConfig.logging.app_log_path` and `audit_log_path`.
  - To minimize resource use:
    - Prefer scanning from file end backwards to collect up to `limit` entries.
    - Avoid loading entire large files into memory.
  - On each line:
    - Parse JSON.
    - Apply filters (`since`, `level`, `error_code`, etc.).
    - Skip lines that fail parsing and increment a diagnostic counter.

Security & privacy:

- Before returning log entries:
  - Use the security module to enforce role-based access:
    - For example only `admin` can read audit logs.
  - Apply additional masking:
    - Ensure that even if a mis-logged secret appears, returned entries do not expose full values.
  - Limit:
    - Maximum `limit` per request.
    - Maximum time window (for example only allow querying recent N days).

### 6.5 CI, TDD & Cross-Document Consistency

- Tests:
  - Integrate logging tests with the TDD process defined in documents 11 and 13.
  - Before changing logging behavior or configuration formats:
    - Update or add unit/integration tests for the logging module and `logs.*` tools.
  - Use `uv run pytest` with coverage reporting (including `--cov=mcp_raspi`) to verify that logging and audit paths meet coverage targets.
- Consistency:
  - When changing:
    - Log file paths.
    - Configuration field names.
    - Tool schemas related to logs (`logs.*` tools).
  - Update:
    - This document (sections 2, 4, 6).
    - Document 05 for tool schemas.
    - Document 11 for testing plans.
    - Document 13 and `README.md` for development and operational guidance.

## 7. Testing Strategy

Testing for logging, observability, and diagnostics must ensure:

- Correctness of logging output structure and content.
- Stability under error conditions (for example disk full).
- Compliance with security and privacy requirements.

### 7.1 Unit Tests – Core Logging

Unit tests should cover:

- JSON formatter:
  - Generates required fields (`timestamp`, `level`, `module`, `message`, `fields`).
  - Produces valid JSON for typical and edge-case messages.
  - Masks sensitive values according to simple key heuristics.
- `get_logger`:
  - Returns loggers with consistent `module` field injection.
  - Works across multiple modules without leaking configuration.
- `configure_logging`:
  - Applies `AppConfig.logging` correctly:
    - Respects `log_to_stdout`, `use_journald`, `level`.
    - Creates file handlers pointing to configured paths.

Self-containment:

- Use temporary directories and file paths for log files in tests.
- Do not rely on system-wide logging configuration.

### 7.2 Unit Tests – Audit Logging

Audit logging tests should verify:

- `AuditLogger.log_tool_call`:
  - Writes entries with all required fields populated:
    - `timestamp`, `tool_name`, `status`, `error_code`, `request_id`, `user_id`, `caller_role`, etc.
  - Correctly merges `extra` fields into the structured `fields` map.
  - Supports both success and error scenarios.
- Error behavior:
  - When the underlying logger or handler fails (simulate I/O errors with mocks):
    - Application logs receive a high-priority entry.
    - For high-risk operations:
      - Tests confirm whether policy dictates a hard failure or a soft failure (log and continue), as implemented.

### 7.3 Unit & Integration Tests – Log Rotation & Retention

If internal rotation is implemented (e.g. `RotatingFileHandler` or custom logic):

- Rotation triggers:
  - Configure small size/time thresholds in tests.
  - Write enough entries to trigger rotation.
  - Verify that:
    - New entries go into the new file.
    - The most recent log data is preserved.
- Retention:
  - Configure maximum file count or total size.
  - Write logs beyond thresholds.
  - Verify that:
    - Old files are removed or ignored according to design.
- Error handling:
  - Use tmpfs or mocks to simulate disk full/write failures.
  - Verify:
    - Error logs include `error_code` and descriptive messages.
    - The module avoids tight loops or uncontrolled logging in failure scenarios.

If system-level rotation (logrotate/journald) is relied upon:

- Unit tests focus on:
  - Generating correct configuration snippets (if any).
  - Ensuring log paths and permissions match expectations.

### 7.4 Unit & Integration Tests – Diagnostics & Query Tools

For `logs.get_recent_app_logs` and `logs.get_recent_audit_logs`, and health-check functions:

- Log query tools:
  - Create temporary JSON Lines log files with:
    - Various levels.
    - Different `error_code` values.
    - Different timestamps.
  - Test filter combinations:
    - `limit`, `since`, `level`, `error_code`.
    - Verify ordering (ascending or descending timestamps as designed).
    - Verify that `limit` is enforced.
    - Confirm correct `since` boundary behavior.
  - Test authorization:
    - For callers without required role, verify:
      - The tools return `permission_denied`.
      - Audit logs record the attempted access.
- Health-check and diagnostics:
  - Simulate:
    - Privileged agent offline (mock IPC client failures).
    - Log directory not writable.
    - Config file missing or misconfigured.
  - Verify that health-check functions:
    - Report degraded status.
    - Provide human-readable diagnostic messages.
    - Optionally log relevant diagnostic entries.

### 7.5 Integration & End‑to‑End Tests

Integration tests (see document 11) should cover:

- Full tool invocation path:
  - From an MCP client issuing a tool call (e.g. `system.get_health_snapshot`, `gpio.write_pin`).
  - Verify:
    - Application log contains a corresponding entry.
    - Audit log records the tool call with caller, tool name, status, and `error_code`.
    - `logs.get_recent_app_logs` and `logs.get_recent_audit_logs` can retrieve these entries.
- Failure scenarios:
  - Self-update failure.
  - Power operation rejected by policy.
  - Privileged agent unavailable.
  - Verify that:
    - Logs and audit records share matching request IDs and `error_code` values.
    - Messages follow the standardized templates.
- Resource usage:
  - Under moderate load (several requests per second), confirm:
    - Logging does not cause significant blocking.
    - Log files grow at expected rates given configuration.

Coverage:

- Logging and audit critical paths should:
  - Reach or approximate the global coverage target defined in document 11.
  - Be monitored via coverage reports in CI.

Once the tasks in this document are implemented and tested, the logging and observability subsystem will:

- Provide Phase 1–ready diagnostics.
- Support future Phase 2+ enhancements such as remote log shipping, richer metrics, and advanced auditing.


---

<!-- Merged from 09-addendum-logging-observability-extensions.md -->


## 1. Prometheus Metrics Export (Phase 2+)

### 1.1 Overview

Prometheus metrics export enables integration with modern observability stacks (Prometheus + Grafana, VictoriaMetrics, etc.) for advanced monitoring, alerting, and visualization.

**Phase 1**: SQLite-based metrics with query tools
**Phase 2+**: Optional Prometheus /metrics HTTP endpoint

### 1.2 Metrics Endpoint Design

#### HTTP Endpoint

```yaml
# Configuration
metrics:
  prometheus:
    enabled: false  # Phase 2+
    endpoint: "/metrics"
    listen_address: "127.0.0.1"  # Localhost only by default
    listen_port: 9100  # Standard node_exporter port
    auth_required: true  # Require same auth as MCP tools
    include_system_metrics: true
    include_device_metrics: true
    include_application_metrics: true
    custom_labels:
      environment: "production"
      device_id: "pi-living-room"
```

#### Implementation Approach

```python
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST
)
from fastapi import FastAPI, Response, Depends
from typing import Dict, Any

class PrometheusMetricsExporter:
    """Prometheus metrics exporter for MCP Raspi Server."""

    def __init__(self, config: MetricsConfig, custom_labels: Dict[str, str]):
        self.config = config
        self.registry = CollectorRegistry()
        self.custom_labels = custom_labels

        # System metrics
        self.cpu_usage = Gauge(
            'raspi_cpu_usage_percent',
            'CPU usage percentage',
            labelnames=['core'],
            registry=self.registry
        )
        self.cpu_temperature = Gauge(
            'raspi_cpu_temperature_celsius',
            'CPU temperature in Celsius',
            registry=self.registry
        )
        self.memory_usage = Gauge(
            'raspi_memory_usage_bytes',
            'Memory usage in bytes',
            labelnames=['type'],  # total, used, available, cached
            registry=self.registry
        )
        self.disk_usage = Gauge(
            'raspi_disk_usage_bytes',
            'Disk usage in bytes',
            labelnames=['device', 'mountpoint', 'type'],  # type: total/used/free
            registry=self.registry
        )
        self.disk_io = Counter(
            'raspi_disk_io_bytes_total',
            'Disk I/O bytes',
            labelnames=['device', 'direction'],  # direction: read/write
            registry=self.registry
        )
        self.network_io = Counter(
            'raspi_network_io_bytes_total',
            'Network I/O bytes',
            labelnames=['interface', 'direction'],  # direction: sent/recv
            registry=self.registry
        )

        # GPIO metrics
        self.gpio_state = Gauge(
            'raspi_gpio_pin_value',
            'GPIO pin value (0 or 1)',
            labelnames=['pin'],
            registry=self.registry
        )

        # Application metrics
        self.mcp_requests_total = Counter(
            'raspi_mcp_requests_total',
            'Total MCP tool requests',
            labelnames=['tool', 'status'],  # status: success/error
            registry=self.registry
        )
        self.mcp_request_duration = Histogram(
            'raspi_mcp_request_duration_seconds',
            'MCP request duration',
            labelnames=['tool'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
            registry=self.registry
        )
        self.ipc_requests_total = Counter(
            'raspi_ipc_requests_total',
            'Total IPC requests to privileged agent',
            labelnames=['operation', 'status'],
            registry=self.registry
        )

        # Service metrics
        self.systemd_service_state = Gauge(
            'raspi_systemd_service_state',
            'Systemd service state (1=active, 0=inactive)',
            labelnames=['service'],
            registry=self.registry
        )

    async def update_metrics(self) -> None:
        """Update all metrics from current system state."""
        if self.config.include_system_metrics:
            await self._update_system_metrics()

        if self.config.include_device_metrics:
            await self._update_device_metrics()

        if self.config.include_application_metrics:
            await self._update_application_metrics()

    async def _update_system_metrics(self) -> None:
        """Update system-level Prometheus metrics."""
        import psutil

        # CPU per-core
        cpu_percents = psutil.cpu_percent(percpu=True)
        for i, pct in enumerate(cpu_percents):
            self.cpu_usage.labels(core=f"cpu{i}").set(pct)

        # Temperature
        temp = await self._get_cpu_temperature()
        if temp is not None:
            self.cpu_temperature.set(temp)

        # Memory
        mem = psutil.virtual_memory()
        self.memory_usage.labels(type="total").set(mem.total)
        self.memory_usage.labels(type="used").set(mem.used)
        self.memory_usage.labels(type="available").set(mem.available)
        self.memory_usage.labels(type="cached").set(mem.cached)

        # Disk usage
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                self.disk_usage.labels(
                    device=partition.device,
                    mountpoint=partition.mountpoint,
                    type="total"
                ).set(usage.total)
                self.disk_usage.labels(
                    device=partition.device,
                    mountpoint=partition.mountpoint,
                    type="used"
                ).set(usage.used)
                self.disk_usage.labels(
                    device=partition.device,
                    mountpoint=partition.mountpoint,
                    type="free"
                ).set(usage.free)
            except PermissionError:
                pass

        # Disk I/O
        disk_io = psutil.disk_io_counters(perdisk=True)
        for device, counters in disk_io.items():
            self.disk_io.labels(device=device, direction="read").inc(
                counters.read_bytes
            )
            self.disk_io.labels(device=device, direction="write").inc(
                counters.write_bytes
            )

        # Network I/O
        net_io = psutil.net_io_counters(pernic=True)
        for interface, counters in net_io.items():
            self.network_io.labels(interface=interface, direction="sent").inc(
                counters.bytes_sent
            )
            self.network_io.labels(interface=interface, direction="recv").inc(
                counters.bytes_recv
            )

    def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics in text format."""
        return generate_latest(self.registry)

# FastAPI endpoint
async def metrics_endpoint(
    auth: AuthContext = Depends(require_auth),
    exporter: PrometheusMetricsExporter = Depends()
) -> Response:
    """Prometheus metrics endpoint."""
    # Update metrics before returning
    await exporter.update_metrics()

    # Generate and return metrics
    metrics_data = exporter.generate_metrics()
    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST
    )
```

### 1.3 Metric Types and Labels

#### System Metrics

```prometheus
# CPU
raspi_cpu_usage_percent{core="cpu0"} 45.2
raspi_cpu_temperature_celsius 58.5

# Memory (bytes)
raspi_memory_usage_bytes{type="total"} 1073741824
raspi_memory_usage_bytes{type="used"} 536870912
raspi_memory_usage_bytes{type="available"} 536870912
raspi_memory_usage_bytes{type="cached"} 268435456

# Disk (bytes)
raspi_disk_usage_bytes{device="/dev/mmcblk0p2",mountpoint="/",type="total"} 32000000000
raspi_disk_usage_bytes{device="/dev/mmcblk0p2",mountpoint="/",type="used"} 8000000000
raspi_disk_usage_bytes{device="/dev/mmcblk0p2",mountpoint="/",type="free"} 24000000000

# I/O (counters)
raspi_disk_io_bytes_total{device="mmcblk0",direction="read"} 1234567890
raspi_disk_io_bytes_total{device="mmcblk0",direction="write"} 987654321
raspi_network_io_bytes_total{interface="eth0",direction="sent"} 5000000000
raspi_network_io_bytes_total{interface="eth0",direction="recv"} 15000000000
```

#### Device Metrics

```prometheus
# GPIO
raspi_gpio_pin_value{pin="17"} 1
raspi_gpio_pin_value{pin="27"} 0

# I2C devices (Phase 2+)
raspi_i2c_device_present{bus="1",address="0x48"} 1
raspi_i2c_sensor_value{bus="1",address="0x48",sensor="temperature"} 25.3
```

#### Application Metrics

```prometheus
# MCP requests
raspi_mcp_requests_total{tool="system.get_info",status="success"} 1523
raspi_mcp_requests_total{tool="gpio.write_pin",status="error"} 12
raspi_mcp_request_duration_seconds_bucket{tool="system.get_info",le="0.05"} 1500
raspi_mcp_request_duration_seconds_sum{tool="system.get_info"} 45.2
raspi_mcp_request_duration_seconds_count{tool="system.get_info"} 1523

# IPC
raspi_ipc_requests_total{operation="gpio_write",status="success"} 8421
raspi_ipc_requests_total{operation="gpio_write",status="error"} 3

# Services
raspi_systemd_service_state{service="nginx"} 1
raspi_systemd_service_state{service="postgresql"} 0
```

#### Custom Labels

All metrics include custom labels from configuration:

```prometheus
raspi_cpu_usage_percent{core="cpu0",environment="production",device_id="pi-living-room"} 45.2
```

### 1.4 Grafana Dashboard Example

**Phase 2+**: Provide pre-built Grafana dashboard JSON for common monitoring scenarios.

Dashboard panels:
- CPU usage (per-core gauge + time series)
- Memory usage (stacked area chart)
- Disk usage (pie chart + time series)
- Temperature (gauge with thresholds + time series)
- Network I/O (stacked area chart)
- Disk I/O (line chart showing read/write)
- MCP request rate (graph by tool)
- MCP error rate (graph with threshold)
- Service states (status list)
- GPIO states (binary indicators)

---

## 2. Log Shipping & Aggregation (Phase 2+)

### 2.1 Overview

Log shipping enables centralized log management for fleets of Raspberry Pi devices using standard log forwarding tools.

**Supported Backends**:
- **Fluentd/Fluent Bit**: Lightweight log forwarder (recommended for Pi)
- **Vector**: Modern log router with transformations
- **Logstash**: Full ELK stack integration
- **Promtail**: Loki integration
- **Syslog**: Traditional syslog-ng or rsyslog

### 2.2 Log Output Formats

#### Structured JSON (Default)

```json
{
  "timestamp": "2025-12-03T14:23:45.123Z",
  "level": "INFO",
  "logger": "mcp_raspi.server",
  "message": "Tool invoked",
  "context": {
    "tool": "gpio.write_pin",
    "user_id": "user@example.com",
    "request_id": "req-12345",
    "duration_ms": 12.5
  },
  "hostname": "raspberrypi",
  "service": "mcp-raspi-server",
  "pid": 1234
}
```

#### Logfmt (Alternative)

```
timestamp=2025-12-03T14:23:45.123Z level=INFO logger=mcp_raspi.server message="Tool invoked" tool=gpio.write_pin user_id=user@example.com request_id=req-12345 duration_ms=12.5 hostname=raspberrypi service=mcp-raspi-server pid=1234
```

### 2.3 Fluent Bit Configuration

**Recommended for Raspberry Pi** due to minimal resource footprint (~450KB memory).

#### /etc/fluent-bit/fluent-bit.conf

```ini
[SERVICE]
    Flush        5
    Daemon       Off
    Log_Level    info
    Parsers_File parsers.conf

# Read MCP server logs
[INPUT]
    Name              tail
    Path              /var/log/mcp-raspi/server.log
    Parser            json
    Tag               mcp.server
    Mem_Buf_Limit     5MB
    Skip_Long_Lines   On
    Refresh_Interval  10

# Read privileged agent logs
[INPUT]
    Name              tail
    Path              /var/log/mcp-raspi/agent.log
    Parser            json
    Tag               mcp.agent
    Mem_Buf_Limit     5MB
    Skip_Long_Lines   On
    Refresh_Interval  10

# Read audit logs
[INPUT]
    Name              tail
    Path              /var/log/mcp-raspi/audit.log
    Parser            json
    Tag               mcp.audit
    Mem_Buf_Limit     5MB
    Skip_Long_Lines   On
    Refresh_Interval  10

# Add device metadata
[FILTER]
    Name    modify
    Match   mcp.*
    Add     device_type raspberry_pi
    Add     device_model ${DEVICE_MODEL}
    Add     fleet_id ${FLEET_ID}

# Filter out debug logs in production
[FILTER]
    Name    grep
    Match   mcp.*
    Exclude level DEBUG

# Forward to centralized Fluentd/Elasticsearch
[OUTPUT]
    Name            forward
    Match           mcp.*
    Host            logs.example.com
    Port            24224
    Retry_Limit     10
    tls             On
    tls.verify      On
    tls.ca_file     /etc/ssl/certs/ca-bundle.crt

# Fallback: write to local file if forwarding fails
[OUTPUT]
    Name            file
    Match           mcp.*
    Path            /var/log/mcp-raspi/backup/
    Format          json_lines
```

#### /etc/fluent-bit/parsers.conf

```ini
[PARSER]
    Name        json
    Format      json
    Time_Key    timestamp
    Time_Format %Y-%m-%dT%H:%M:%S.%L%z
    Time_Keep   On
```

### 2.4 Vector Configuration

**Modern alternative** with built-in transformations and multiple sinks.

#### /etc/vector/vector.toml

```toml
[sources.mcp_server_logs]
type = "file"
include = ["/var/log/mcp-raspi/server.log"]
read_from = "beginning"

[sources.mcp_agent_logs]
type = "file"
include = ["/var/log/mcp-raspi/agent.log"]
read_from = "beginning"

[sources.mcp_audit_logs]
type = "file"
include = ["/var/log/mcp-raspi/audit.log"]
read_from = "beginning"

[transforms.parse_json]
type = "remap"
inputs = ["mcp_*"]
source = '''
. = parse_json!(.message)
.device_type = "raspberry_pi"
.device_model = "${DEVICE_MODEL}"
.fleet_id = "${FLEET_ID}"
'''

[transforms.filter_debug]
type = "filter"
inputs = ["parse_json"]
condition = '.level != "DEBUG"'

[sinks.elasticsearch]
type = "elasticsearch"
inputs = ["filter_debug"]
endpoint = "https://elasticsearch.example.com:9200"
bulk.index = "mcp-raspi-%Y.%m.%d"
auth.strategy = "basic"
auth.user = "${ES_USER}"
auth.password = "${ES_PASSWORD}"

[sinks.loki]
type = "loki"
inputs = ["filter_debug"]
endpoint = "https://loki.example.com"
labels.service = "{{ service }}"
labels.level = "{{ level }}"
labels.device_id = "{{ hostname }}"
```

### 2.5 Syslog Integration

For traditional syslog-based infrastructure:

#### /etc/rsyslog.d/50-mcp-raspi.conf

```conf
# Forward MCP logs to central syslog server
:programname, isequal, "mcp-raspi-server" @@logs.example.com:514
:programname, isequal, "raspi-ops-agent" @@logs.example.com:514

# Also keep local copies
:programname, isequal, "mcp-raspi-server" /var/log/mcp-raspi/server.log
:programname, isequal, "raspi-ops-agent" /var/log/mcp-raspi/agent.log
```

### 2.6 Configuration in AppConfig

```yaml
logging:
  # ... existing logging config ...

  shipping:
    enabled: false  # Phase 2+
    backend: "fluent-bit"  # fluent-bit | vector | syslog | custom
    config_path: "/etc/fluent-bit/fluent-bit.conf"

    # Metadata to include in shipped logs
    device_metadata:
      device_type: "raspberry_pi"
      device_model: "${DEVICE_MODEL}"  # Env var substitution
      fleet_id: "${FLEET_ID}"
      location: "${DEVICE_LOCATION}"

    # Only ship logs above this level
    min_level: "INFO"

    # Buffer settings for unreliable networks
    buffer_max_size_mb: 50
    buffer_path: "/var/lib/mcp-raspi/log-buffer"
    retry_max_attempts: 10
    retry_backoff_seconds: 60
```

---

## 3. Alerting Mechanisms (Phase 2+)

### 3.1 Alert Rule Configuration

```yaml
# /etc/mcp-raspi/alerts.yml
alerts:
  enabled: false  # Phase 2+

  # Alert delivery channels
  channels:
    - type: "email"
      name: "ops-team"
      smtp_host: "smtp.example.com"
      smtp_port: 587
      smtp_user: "${SMTP_USER}"
      smtp_password: "${SMTP_PASSWORD}"
      from: "alerts@example.com"
      to: ["ops@example.com"]

    - type: "webhook"
      name: "slack"
      url: "https://hooks.slack.com/services/XXX/YYY/ZZZ"
      method: "POST"
      headers:
        Content-Type: "application/json"

    - type: "webhook"
      name: "pagerduty"
      url: "https://events.pagerduty.com/v2/enqueue"
      method: "POST"
      headers:
        Authorization: "Token token=${PAGERDUTY_TOKEN}"
        Content-Type: "application/json"

  # Alert rules
  rules:
    - name: "high_cpu_temperature"
      description: "CPU temperature exceeds safe threshold"
      condition:
        metric: "system.temperature"
        operator: ">"
        threshold: 75.0
        duration_seconds: 300  # Sustained for 5 minutes
      severity: "warning"
      channels: ["ops-team", "slack"]

    - name: "critical_cpu_temperature"
      description: "CPU temperature critically high"
      condition:
        metric: "system.temperature"
        operator: ">"
        threshold: 85.0
        duration_seconds: 60
      severity: "critical"
      channels: ["ops-team", "slack", "pagerduty"]
      actions:
        - type: "tool_call"
          tool: "manage.reboot"
          params:
            force: false

    - name: "low_disk_space"
      description: "Root filesystem below 10% free"
      condition:
        metric: "disk.usage_percent"
        filter:
          mountpoint: "/"
        operator: ">"
        threshold: 90.0
      severity: "warning"
      channels: ["ops-team"]

    - name: "high_error_rate"
      description: "MCP tool error rate above 5%"
      condition:
        metric: "mcp.error_rate"
        operator: ">"
        threshold: 0.05
        duration_seconds: 600
      severity: "warning"
      channels: ["ops-team", "slack"]

    - name: "service_failed"
      description: "Critical systemd service failed"
      condition:
        event: "service.state_changed"
        filter:
          service: "nginx|postgresql"
          new_state: "failed"
      severity: "critical"
      channels: ["ops-team", "pagerduty"]

    - name: "unauthorized_access_attempt"
      description: "Multiple failed auth attempts"
      condition:
        event: "auth.failed"
        count: 5
        window_seconds: 300
      severity: "critical"
      channels: ["ops-team", "pagerduty"]
      actions:
        - type: "tool_call"
          tool: "security.lockdown"
          params:
            duration_seconds: 3600
```

### 3.2 Alert Evaluation Engine

```python
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio

@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    description: str
    condition: Dict[str, Any]
    severity: str  # info, warning, critical
    channels: List[str]
    actions: Optional[List[Dict[str, Any]]] = None
    enabled: bool = True

@dataclass
class AlertEvent:
    """Fired alert event."""
    rule_name: str
    severity: str
    timestamp: datetime
    message: str
    metric_value: Optional[float] = None
    context: Optional[Dict[str, Any]] = None

class AlertEvaluator:
    """Evaluates alert rules against metrics and events."""

    def __init__(
        self,
        rules: List[AlertRule],
        metrics_store: MetricsStore,
        channels: Dict[str, AlertChannel]
    ):
        self.rules = rules
        self.metrics_store = metrics_store
        self.channels = channels
        self.active_alerts: Dict[str, AlertEvent] = {}
        self.alert_history: List[AlertEvent] = []

    async def evaluate_all(self) -> None:
        """Evaluate all enabled alert rules."""
        for rule in self.rules:
            if not rule.enabled:
                continue

            try:
                if rule.condition.get("metric"):
                    await self._evaluate_metric_rule(rule)
                elif rule.condition.get("event"):
                    await self._evaluate_event_rule(rule)
            except Exception as e:
                logger.error(
                    "Alert rule evaluation failed",
                    rule=rule.name,
                    error=str(e)
                )

    async def _evaluate_metric_rule(self, rule: AlertRule) -> None:
        """Evaluate metric-based alert rule."""
        condition = rule.condition
        metric_name = condition["metric"]
        operator = condition["operator"]
        threshold = condition["threshold"]
        duration = condition.get("duration_seconds", 0)

        # Query recent metric values
        end_time = datetime.now()
        start_time = end_time - timedelta(seconds=duration or 60)

        values = await self.metrics_store.query_metric(
            metric_name=metric_name,
            start_time=start_time,
            end_time=end_time,
            filters=condition.get("filter")
        )

        if not values:
            return

        # Check if condition is met
        breaching_duration = self._calculate_breach_duration(
            values, operator, threshold
        )

        if breaching_duration >= duration:
            # Condition met - fire alert
            current_value = values[-1]["value"]

            if rule.name not in self.active_alerts:
                # New alert
                event = AlertEvent(
                    rule_name=rule.name,
                    severity=rule.severity,
                    timestamp=datetime.now(),
                    message=self._format_alert_message(rule, current_value),
                    metric_value=current_value,
                    context={
                        "metric": metric_name,
                        "threshold": threshold,
                        "duration": duration
                    }
                )

                self.active_alerts[rule.name] = event
                self.alert_history.append(event)

                await self._send_alert(event, rule.channels)
                await self._execute_actions(rule.actions)
        else:
            # Condition not met - resolve if active
            if rule.name in self.active_alerts:
                await self._resolve_alert(rule)

    def _calculate_breach_duration(
        self,
        values: List[Dict[str, Any]],
        operator: str,
        threshold: float
    ) -> int:
        """Calculate how long the condition has been breaching."""
        breach_start = None

        for point in values:
            value = point["value"]
            timestamp = point["timestamp"]

            is_breaching = self._check_operator(value, operator, threshold)

            if is_breaching:
                if breach_start is None:
                    breach_start = timestamp
            else:
                breach_start = None

        if breach_start is None:
            return 0

        return (datetime.now() - breach_start).total_seconds()

    def _check_operator(self, value: float, operator: str, threshold: float) -> bool:
        """Check if value meets operator condition."""
        if operator == ">":
            return value > threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<":
            return value < threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "==":
            return value == threshold
        elif operator == "!=":
            return value != threshold
        return False

    async def _send_alert(self, event: AlertEvent, channel_names: List[str]) -> None:
        """Send alert to specified channels."""
        for channel_name in channel_names:
            channel = self.channels.get(channel_name)
            if channel:
                try:
                    await channel.send(event)
                except Exception as e:
                    logger.error(
                        "Failed to send alert",
                        channel=channel_name,
                        error=str(e)
                    )

    async def _execute_actions(self, actions: Optional[List[Dict[str, Any]]]) -> None:
        """Execute automated remediation actions."""
        if not actions:
            return

        for action in actions:
            if action["type"] == "tool_call":
                # Call MCP tool for remediation
                tool = action["tool"]
                params = action["params"]

                logger.info(
                    "Executing alert remediation action",
                    tool=tool,
                    params=params
                )

                # TODO: Implement safe tool calling with confirmation
                # await self.tool_router.invoke_tool(tool, params)
```

### 3.3 Alert Channels

#### Email Channel

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailAlertChannel:
    """Email alert delivery channel."""

    def __init__(self, config: Dict[str, Any]):
        self.smtp_host = config["smtp_host"]
        self.smtp_port = config["smtp_port"]
        self.smtp_user = config["smtp_user"]
        self.smtp_password = config["smtp_password"]
        self.from_address = config["from"]
        self.to_addresses = config["to"]

    async def send(self, event: AlertEvent) -> None:
        """Send alert via email."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{event.severity.upper()}] {event.rule_name}"
        msg["From"] = self.from_address
        msg["To"] = ", ".join(self.to_addresses)

        # Plain text version
        text = self._format_plain_text(event)
        part1 = MIMEText(text, "plain")
        msg.attach(part1)

        # HTML version
        html = self._format_html(event)
        part2 = MIMEText(html, "html")
        msg.attach(part2)

        # Send email
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(
                self.from_address,
                self.to_addresses,
                msg.as_string()
            )
```

#### Webhook Channel (Slack/PagerDuty)

```python
import httpx

class WebhookAlertChannel:
    """Generic webhook alert delivery channel."""

    def __init__(self, config: Dict[str, Any]):
        self.url = config["url"]
        self.method = config.get("method", "POST")
        self.headers = config.get("headers", {})

    async def send(self, event: AlertEvent) -> None:
        """Send alert via webhook."""
        payload = self._format_payload(event)

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=self.method,
                url=self.url,
                json=payload,
                headers=self.headers,
                timeout=10.0
            )
            response.raise_for_status()

    def _format_payload(self, event: AlertEvent) -> Dict[str, Any]:
        """Format alert as webhook payload."""
        # Slack format
        return {
            "text": event.message,
            "attachments": [{
                "color": self._severity_color(event.severity),
                "fields": [
                    {"title": "Rule", "value": event.rule_name, "short": True},
                    {"title": "Severity", "value": event.severity.upper(), "short": True},
                    {"title": "Time", "value": event.timestamp.isoformat(), "short": True},
                    {"title": "Value", "value": str(event.metric_value), "short": True},
                ]
            }]
        }

    def _severity_color(self, severity: str) -> str:
        """Map severity to Slack color."""
        return {
            "info": "#36a64f",      # green
            "warning": "#ff9900",   # orange
            "critical": "#ff0000"   # red
        }.get(severity, "#808080")  # gray
```

---

## 4. Real-Time Log Streaming (Phase 2+)

### 4.1 WebSocket Log Stream

Enables real-time log viewing in web UIs or CLI tools.

```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Set
import asyncio

class LogStreamer:
    """Real-time log streaming via WebSocket."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.log_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket connection."""
        self.active_connections.discard(websocket)

    async def broadcast_log(self, log_entry: Dict[str, Any]) -> None:
        """Broadcast log entry to all connected clients."""
        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_json(log_entry)
            except WebSocketDisconnect:
                disconnected.add(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

# FastAPI endpoint
@app.websocket("/ws/logs")
async def websocket_logs(
    websocket: WebSocket,
    auth: AuthContext = Depends(require_auth),
    streamer: LogStreamer = Depends()
):
    """WebSocket endpoint for real-time log streaming."""
    # Require at least 'viewer' role
    if "viewer" not in auth.roles:
        await websocket.close(code=1008, reason="Insufficient permissions")
        return

    await streamer.connect(websocket)

    try:
        while True:
            # Keep connection alive, wait for client messages (filters, etc.)
            data = await websocket.receive_json()

            # Handle filter updates
            if data.get("action") == "set_filter":
                # Update client-specific filters
                pass

    except WebSocketDisconnect:
        streamer.disconnect(websocket)
```

### 4.2 MCP Tool for Log Streaming

```json
{
  "method": "logs.stream",
  "params": {
    "follow": true,
    "tail_lines": 100,
    "filter": {
      "level": ["WARNING", "ERROR", "CRITICAL"],
      "logger": "mcp_raspi.gpio"
    }
  }
}
```

**Response**: Streaming JSON-RPC notifications with log entries.

---

## 5. Log Parsing & Analysis Tools

### 5.1 CLI Log Analysis Tool

```bash
# Install
sudo pip install mcp-raspi-logtools

# Recent errors
mcp-raspi-logs errors --since 1h

# Top error messages
mcp-raspi-logs top-errors --since 24h --limit 10

# Audit trail for user
mcp-raspi-logs audit --user user@example.com --since 7d

# Tool invocation statistics
mcp-raspi-logs stats --tool gpio.write_pin --since 24h

# Search logs
mcp-raspi-logs search "GPIO pin 17" --since 1h --context 5

# Follow logs (like tail -f)
mcp-raspi-logs follow --level INFO
```

### 5.2 Built-in Log Analysis MCP Tool

```json
{
  "method": "logs.analyze",
  "params": {
    "analysis_type": "error_summary",
    "time_range": {
      "start": "2025-12-03T00:00:00Z",
      "end": "2025-12-03T23:59:59Z"
    }
  }
}
```

**Response**:

```json
{
  "result": {
    "total_errors": 42,
    "error_by_logger": {
      "mcp_raspi.gpio": 15,
      "mcp_raspi.i2c": 12,
      "mcp_raspi.camera": 10,
      "mcp_raspi.service": 5
    },
    "top_error_messages": [
      {
        "message": "Failed to open I2C bus 1",
        "count": 12,
        "first_seen": "2025-12-03T08:23:11Z",
        "last_seen": "2025-12-03T16:45:32Z"
      },
      {
        "message": "GPIO pin 17 already in use",
        "count": 8,
        "first_seen": "2025-12-03T10:15:22Z",
        "last_seen": "2025-12-03T18:20:11Z"
      }
    ],
    "recommendations": [
      "Check I2C bus permissions and hardware connections",
      "Review GPIO pin allocation to avoid conflicts"
    ]
  }
}
```

---

## 6. Implementation Checklist

### Phase 1 (Current)
- ✅ Structured JSON logging with context
- ✅ Rotating file handlers
- ✅ Audit logging for privileged operations
- ✅ `logs.query` MCP tool
- ✅ Configurable log levels and filters

### Phase 2+ (Future)
- ⏭️ Prometheus metrics export endpoint
- ⏭️ Fluent Bit / Vector log shipping integration
- ⏭️ Alert rule engine with multiple channels
- ⏭️ Real-time log streaming via WebSocket
- ⏭️ CLI log analysis tools
- ⏭️ Grafana dashboard templates
- ⏭️ PagerDuty / Slack / Email alert channels
- ⏭️ Automated remediation actions
- ⏭️ Log aggregation for multi-device fleets

---

**End of Document**

---

<!-- Merged from 09-addendum-observability-advanced-topics.md -->


## 1. Distributed Tracing (Phase 2+)

### 1.1 Overview

Distributed tracing tracks requests across multiple components (MCP server → IPC → privileged agent → hardware) to identify performance bottlenecks and debug complex issues.

**Benefits**:
- End-to-end request visibility
- Performance bottleneck identification
- Dependency mapping
- Error attribution

**Technology**: OpenTelemetry (industry standard)

### 1.2 Trace Architecture

```
[Client Request] → [MCP Server] → [IPC Client] → [Privileged Agent] → [Hardware]
     trace_id          span_1         span_2          span_3            span_4
```

Each span captures:
- Operation name
- Start/end timestamps
- Parent span ID
- Attributes (tool name, parameters, user)
- Events (errors, state changes)
- Status (OK, Error)

### 1.3 Implementation with OpenTelemetry

```python
# src/mcp_raspi/observability/tracing.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from typing import Optional
from contextlib import contextmanager

class DistributedTracing:
    """Distributed tracing with OpenTelemetry."""

    def __init__(self, config: TracingConfig):
        self.config = config

        # Create resource (identifies this service)
        resource = Resource.create({
            "service.name": "mcp-raspi-server",
            "service.version": get_version(),
            "deployment.environment": config.environment,
            "device.id": config.device_id,
            "device.model": get_device_model(),
        })

        # Set up tracer provider
        provider = TracerProvider(resource=resource)

        # Add exporter (OTLP to collector)
        if config.enabled:
            otlp_exporter = OTLPSpanExporter(
                endpoint=config.collector_endpoint,
                headers=config.headers
            )
            provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )

        trace.set_tracer_provider(provider)
        self.tracer = trace.get_tracer(__name__)

    @contextmanager
    def trace_tool_invocation(
        self,
        tool_name: str,
        params: dict,
        user_email: str
    ):
        """Trace MCP tool invocation."""
        with self.tracer.start_as_current_span(
            name=f"mcp.tool.{tool_name}",
            kind=trace.SpanKind.SERVER,
            attributes={
                "mcp.tool": tool_name,
                "mcp.user": user_email,
                # Don't log sensitive params
                "mcp.params.count": len(params),
            }
        ) as span:
            try:
                yield span
                span.set_status(trace.Status(trace.StatusCode.OK))
            except Exception as e:
                span.set_status(
                    trace.Status(
                        trace.StatusCode.ERROR,
                        str(e)
                    )
                )
                span.record_exception(e)
                raise

    @contextmanager
    def trace_ipc_call(self, operation: str, params: dict):
        """Trace IPC call to privileged agent."""
        with self.tracer.start_as_current_span(
            name=f"ipc.{operation}",
            kind=trace.SpanKind.CLIENT,
            attributes={
                "ipc.operation": operation,
                "ipc.transport": "unix_socket",
            }
        ) as span:
            yield span

    @contextmanager
    def trace_hardware_operation(self, hw_type: str, details: dict):
        """Trace hardware operation."""
        with self.tracer.start_as_current_span(
            name=f"hw.{hw_type}",
            kind=trace.SpanKind.INTERNAL,
            attributes={
                "hw.type": hw_type,
                **details
            }
        ) as span:
            yield span

# Usage example
async def handle_gpio_write(request: GpioWriteRequest, auth: AuthContext):
    """Handle GPIO write with tracing."""
    with tracing.trace_tool_invocation("gpio.write_pin", request.dict(), auth.user_email) as span:
        # Add custom attributes
        span.set_attribute("gpio.pin", request.pin)
        span.set_attribute("gpio.value", request.value)

        # Trace IPC call
        with tracing.trace_ipc_call("gpio_write", {"pin": request.pin}):
            result = await ipc_client.gpio_write(request.pin, request.value)

        # Trace hardware operation (in privileged agent)
        # This would be done in the agent code
        # with tracing.trace_hardware_operation("gpio", {"pin": request.pin}):
        #     GPIO.output(request.pin, request.value)

        return result
```

### 1.4 Trace Configuration

```yaml
# /etc/mcp-raspi/config.yml

tracing:
  enabled: false  # Phase 2+
  collector_endpoint: "http://localhost:4317"  # OTLP gRPC endpoint
  sampling_rate: 1.0  # 100% sampling (adjust for production)
  environment: "production"

  # Custom attributes
  device_id: "${DEVICE_ID}"

  # Authentication for collector
  headers:
    authorization: "Bearer ${TRACING_TOKEN}"
```

### 1.5 Trace Visualization

**Tools**:
- **Jaeger**: Open-source tracing backend
- **Zipkin**: Alternative tracing backend
- **Grafana Tempo**: Lightweight tracing backend
- **Honeycomb**: Commercial observability platform

**Example Trace**:
```
trace_id: 7af4e8c2b3d1a5f6

┌─ mcp.tool.gpio.write_pin (250ms) ──────────────────────────────┐
│  user: user@example.com                                         │
│  ├─ auth.validate_jwt (15ms)                                    │
│  ├─ auth.check_permission (5ms)                                 │
│  ├─ ipc.gpio_write (200ms)                                      │
│  │  └─ hw.gpio (180ms)                                          │
│  │     └─ gpiozero.output_device.on (175ms)                     │
│  └─ audit.log_operation (30ms)                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. SLA/SLO Definitions

### 2.1 Overview

**SLI (Service Level Indicator)**: Quantitative measure of service level
**SLO (Service Level Objective)**: Target value for an SLI
**SLA (Service Level Agreement)**: Contractual commitment (with consequences)

### 2.2 Service Level Indicators (SLIs)

#### Availability

**Definition**: Percentage of time the service is operational and able to handle requests.

```
Availability = (Total Time - Downtime) / Total Time × 100%
```

**Measurement**:
```python
# Calculate availability from health checks
successful_checks = db.count_health_checks(status="healthy", period="30d")
total_checks = db.count_health_checks(period="30d")
availability = successful_checks / total_checks * 100
```

#### Latency

**Definition**: Time to complete a request.

**Measurement**:
- p50 (median): 50% of requests complete within this time
- p95: 95% of requests complete within this time
- p99: 99% of requests complete within this time

```python
# Calculate latency percentiles from metrics
latencies = db.query_metric("mcp.request.duration_ms", period="24h")
p50 = percentile(latencies, 50)
p95 = percentile(latencies, 95)
p99 = percentile(latencies, 99)
```

#### Error Rate

**Definition**: Percentage of requests that fail.

```
Error Rate = Failed Requests / Total Requests × 100%
```

**Measurement**:
```python
# Calculate error rate
failed = db.count_requests(status="error", period="1h")
total = db.count_requests(period="1h")
error_rate = failed / total * 100 if total > 0 else 0
```

### 2.3 Service Level Objectives (SLOs)

#### Production Environment SLOs

| SLI | SLO Target | Measurement Window | Alerting Threshold |
|-----|------------|-------------------|-------------------|
| **Availability** | ≥ 99.5% | 30 days | < 99.0% |
| **Latency (p95)** | ≤ 500ms | 24 hours | > 750ms |
| **Latency (p99)** | ≤ 1000ms | 24 hours | > 1500ms |
| **Error Rate** | ≤ 1% | 1 hour | > 2% |
| **Tool Success Rate** | ≥ 99% | 24 hours | < 98% |

#### Per-Device SLOs (by model)

**Raspberry Pi 5**:
- Availability: ≥ 99.9%
- Latency p95: ≤ 200ms
- Error Rate: ≤ 0.5%

**Raspberry Pi 4**:
- Availability: ≥ 99.5%
- Latency p95: ≤ 500ms
- Error Rate: ≤ 1%

**Raspberry Pi 3**:
- Availability: ≥ 99.0%
- Latency p95: ≤ 1000ms
- Error Rate: ≤ 2%

**Raspberry Pi Zero 2W**:
- Availability: ≥ 98.5%
- Latency p95: ≤ 2000ms
- Error Rate: ≤ 3%

### 2.4 Error Budgets

**Error Budget** = Amount of downtime/errors allowed while still meeting SLO.

**Example**:
- SLO: 99.5% availability over 30 days
- Total time: 30 days = 720 hours = 43,200 minutes
- Allowed downtime: 0.5% × 43,200 = 216 minutes = 3.6 hours

**Error Budget Policy**:
```yaml
error_budget:
  # If error budget exhausted
  policies:
    - trigger: "budget_exhausted"
      actions:
        - "halt_rollouts"           # Stop new deployments
        - "focus_on_reliability"    # Prioritize bug fixes
        - "alert_oncall"            # Page on-call engineer

    - trigger: "budget_50_percent"
      actions:
        - "review_recent_changes"   # Audit recent deploys
        - "increase_monitoring"     # More frequent health checks

    - trigger: "budget_75_percent"
      actions:
        - "slow_rollouts"           # Smaller deployment batches
```

### 2.5 SLO Monitoring

```python
# src/mcp_raspi/observability/slo.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

@dataclass
class SLO:
    """Service Level Objective definition."""
    name: str
    sli_name: str  # Which SLI to measure
    target: float  # Target value
    comparison: str  # ">", "<", ">=", "<="
    window_hours: int  # Measurement window

@dataclass
class SLOStatus:
    """Current SLO status."""
    slo: SLO
    current_value: float
    target_value: float
    is_meeting: bool
    error_budget_remaining: float  # 0.0 to 1.0
    last_updated: datetime

class SLOMonitor:
    """Monitors SLOs and calculates error budgets."""

    SLOS = [
        SLO("availability", "health.availability", 99.5, ">=", 720),  # 30 days
        SLO("latency_p95", "request.latency.p95", 500, "<=", 24),
        SLO("error_rate", "request.error_rate", 1.0, "<=", 1),
    ]

    def __init__(self, metrics_store: MetricsStore):
        self.metrics_store = metrics_store

    async def check_all_slos(self) -> List[SLOStatus]:
        """Check all SLO statuses."""
        statuses = []

        for slo in self.SLOS:
            status = await self.check_slo(slo)
            statuses.append(status)

            # Alert if SLO violated
            if not status.is_meeting:
                await self._alert_slo_violation(status)

        return statuses

    async def check_slo(self, slo: SLO) -> SLOStatus:
        """Check a single SLO."""
        # Get metric values for window
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=slo.window_hours)

        values = await self.metrics_store.query_metric(
            slo.sli_name,
            start_time,
            end_time
        )

        # Calculate current value (depends on SLI)
        if slo.sli_name == "health.availability":
            current_value = self._calculate_availability(values)
        elif ".p95" in slo.sli_name:
            current_value = self._calculate_percentile(values, 95)
        elif "error_rate" in slo.sli_name:
            current_value = self._calculate_error_rate(values)
        else:
            current_value = values[-1]["value"] if values else 0

        # Check if meeting SLO
        is_meeting = self._compare(current_value, slo.comparison, slo.target)

        # Calculate error budget
        error_budget_remaining = self._calculate_error_budget(
            slo,
            current_value
        )

        return SLOStatus(
            slo=slo,
            current_value=current_value,
            target_value=slo.target,
            is_meeting=is_meeting,
            error_budget_remaining=error_budget_remaining,
            last_updated=datetime.now()
        )

    def _calculate_error_budget(self, slo: SLO, current_value: float) -> float:
        """Calculate remaining error budget (0.0 = exhausted, 1.0 = full)."""
        if slo.comparison in [">=", ">"]:
            # Availability-style (want high value)
            allowed_error = 100 - slo.target  # e.g., 0.5% for 99.5%
            actual_error = 100 - current_value
            return 1.0 - (actual_error / allowed_error) if allowed_error > 0 else 1.0
        else:
            # Latency/error-rate style (want low value)
            if current_value <= slo.target:
                return 1.0  # Under budget
            else:
                # Over budget - calculate how much
                over_budget = current_value - slo.target
                return max(0.0, 1.0 - (over_budget / slo.target))

    async def _alert_slo_violation(self, status: SLOStatus):
        """Alert when SLO is violated."""
        logger.error(
            "SLO violation detected",
            slo=status.slo.name,
            current=status.current_value,
            target=status.target_value,
            error_budget_remaining=status.error_budget_remaining
        )

        # Send alert (integrate with alerting system)
        # await alerting.send_alert(...)
```

---

## 3. Grafana Dashboard Templates

### 3.1 Overview

Pre-built Grafana dashboards provide instant visibility into system health, performance, and usage.

### 3.2 System Health Dashboard

```json
{
  "dashboard": {
    "title": "MCP Raspi - System Health",
    "panels": [
      {
        "title": "CPU Temperature",
        "type": "gauge",
        "targets": [{
          "expr": "raspi_cpu_temperature_celsius",
          "legendFormat": "CPU Temp"
        }],
        "fieldConfig": {
          "min": 0,
          "max": 100,
          "thresholds": [
            {"value": 0, "color": "green"},
            {"value": 70, "color": "yellow"},
            {"value": 80, "color": "red"}
          ]
        }
      },
      {
        "title": "CPU Usage",
        "type": "timeseries",
        "targets": [{
          "expr": "raspi_cpu_usage_percent",
          "legendFormat": "{{core}}"
        }]
      },
      {
        "title": "Memory Usage",
        "type": "timeseries",
        "targets": [
          {
            "expr": "raspi_memory_usage_bytes{type='used'} / raspi_memory_usage_bytes{type='total'} * 100",
            "legendFormat": "Memory %"
          }
        ]
      },
      {
        "title": "Disk Usage",
        "type": "gauge",
        "targets": [{
          "expr": "raspi_disk_usage_bytes{type='used',mountpoint='/'} / raspi_disk_usage_bytes{type='total',mountpoint='/'} * 100",
          "legendFormat": "Disk %"
        }],
        "fieldConfig": {
          "min": 0,
          "max": 100,
          "thresholds": [
            {"value": 0, "color": "green"},
            {"value": 80, "color": "yellow"},
            {"value": 90, "color": "red"}
          ]
        }
      },
      {
        "title": "System Uptime",
        "type": "stat",
        "targets": [{
          "expr": "time() - process_start_time_seconds",
          "legendFormat": "Uptime"
        }],
        "fieldConfig": {
          "unit": "s"
        }
      }
    ]
  }
}
```

### 3.3 Request Performance Dashboard

```json
{
  "dashboard": {
    "title": "MCP Raspi - Request Performance",
    "panels": [
      {
        "title": "Request Rate",
        "type": "timeseries",
        "targets": [{
          "expr": "rate(raspi_mcp_requests_total[5m])",
          "legendFormat": "{{tool}} - {{status}}"
        }]
      },
      {
        "title": "Request Latency (p95)",
        "type": "timeseries",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(raspi_mcp_request_duration_seconds_bucket[5m]))",
          "legendFormat": "p95 - {{tool}}"
        }]
      },
      {
        "title": "Error Rate",
        "type": "timeseries",
        "targets": [{
          "expr": "rate(raspi_mcp_requests_total{status='error'}[5m]) / rate(raspi_mcp_requests_total[5m]) * 100",
          "legendFormat": "Error %"
        }],
        "alert": {
          "conditions": [
            {
              "evaluator": {"type": "gt", "params": [2]},
              "operator": {"type": "and"},
              "query": {"params": ["A", "5m", "now"]},
              "reducer": {"type": "avg"}
            }
          ],
          "name": "High Error Rate"
        }
      },
      {
        "title": "Top Slow Tools",
        "type": "table",
        "targets": [{
          "expr": "topk(5, histogram_quantile(0.95, rate(raspi_mcp_request_duration_seconds_bucket[1h])))",
          "format": "table"
        }]
      }
    ]
  }
}
```

### 3.4 SLO Monitoring Dashboard

```json
{
  "dashboard": {
    "title": "MCP Raspi - SLO Monitoring",
    "panels": [
      {
        "title": "Availability SLO",
        "type": "gauge",
        "targets": [{
          "expr": "(1 - (sum(rate(up{job='mcp-raspi'}[30d])) / count(up{job='mcp-raspi'}[30d]))) * 100",
          "legendFormat": "Availability"
        }],
        "fieldConfig": {
          "min": 99.0,
          "max": 100,
          "thresholds": [
            {"value": 99.0, "color": "red"},
            {"value": 99.5, "color": "yellow"},
            {"value": 99.9, "color": "green"}
          ]
        }
      },
      {
        "title": "Error Budget Remaining",
        "type": "bargauge",
        "targets": [{
          "expr": "slo_error_budget_remaining",
          "legendFormat": "{{slo}}"
        }],
        "fieldConfig": {
          "min": 0,
          "max": 1,
          "thresholds": [
            {"value": 0, "color": "red"},
            {"value": 0.2, "color": "yellow"},
            {"value": 0.5, "color": "green"}
          ]
        }
      },
      {
        "title": "SLO Status",
        "type": "table",
        "targets": [{
          "expr": "slo_status",
          "format": "table"
        }]
      }
    ]
  }
}
```

---

## 4. Common Failure Patterns Playbook

### 4.1 Overview

Document common failure patterns with symptoms, root causes, and resolution steps.

### 4.2 Failure Pattern: High CPU Temperature

**Symptoms**:
- CPU temperature > 80°C
- Thermal throttling active
- Performance degradation

**Root Causes**:
- Inadequate cooling/ventilation
- High ambient temperature
- CPU-intensive operations
- Failed cooling fan

**Detection**:
```promql
raspi_cpu_temperature_celsius > 80
```

**Resolution Steps**:
1. Check current temperature: `vcgencmd measure_temp`
2. Check throttling status: `vcgencmd get_throttled`
3. Improve ventilation or add cooling fan
4. Reduce CPU load (stop non-critical services)
5. If persistent, investigate for hardware failure

**Prevention**:
- Install heatsink or fan
- Monitor temperature trends
- Alert at 75°C threshold
- Schedule intensive tasks during cool periods

### 4.3 Failure Pattern: Memory Exhaustion

**Symptoms**:
- OOM (Out of Memory) killer active
- Services crashing randomly
- `dmesg` shows "Out of memory" messages

**Root Causes**:
- Memory leak in application
- Metrics database too large
- Too many concurrent requests
- Insufficient RAM for workload

**Detection**:
```promql
raspi_memory_usage_bytes{type="used"} / raspi_memory_usage_bytes{type="total"} > 0.95
```

**Resolution Steps**:
1. Check memory usage: `free -h`
2. Identify memory hogs: `ps aux --sort=-%mem | head`
3. Check for memory leaks in logs
4. Restart affected services: `systemctl restart mcp-raspi-server`
5. Reduce metrics retention: edit `config.yml`
6. Add swap space (temporary): `sudo dd if=/dev/zero of=/swapfile bs=1M count=1024`

**Prevention**:
- Implement memory limits in systemd unit
- Regular memory profiling
- Aggressive metrics retention policy
- Consider device upgrade (more RAM)

### 4.3 Failure Pattern: SD Card Corruption

**Symptoms**:
- Read-only filesystem errors
- Database corruption
- Boot failures

**Root Causes**:
- Power loss during write
- SD card wear/failure
- Excessive writes

**Detection**:
```bash
# Check for read-only filesystem
mount | grep "ro,"

# Check SD card health
sudo badblocks -v /dev/mmcblk0
```

**Resolution Steps**:
1. Reboot to fix temporary read-only state
2. Run filesystem check: `sudo fsck /dev/mmcblk0p2`
3. Restore from backup if corrupted
4. Replace SD card if failing

**Prevention**:
- Use high-quality SD cards (Class 10, A1/A2)
- Enable write caching: `sync` before power off
- Implement automated backups
- Use overlayfs for read-only root (Phase 2+)
- Monitor disk I/O for excessive writes

### 4.4 Failure Pattern: IPC Timeout

**Symptoms**:
- Tool requests timeout
- "IPC timeout" errors in logs
- Privileged agent unresponsive

**Root Causes**:
- Privileged agent crashed
- Unix socket permissions incorrect
- Agent blocked on hardware operation
- System overloaded

**Detection**:
```promql
rate(raspi_ipc_requests_total{status="timeout"}[5m]) > 0.1
```

**Resolution Steps**:
1. Check agent status: `systemctl status raspi-ops-agent`
2. Check agent logs: `journalctl -u raspi-ops-agent -n 50`
3. Restart agent: `systemctl restart raspi-ops-agent`
4. Check socket permissions: `ls -l /var/run/mcp-raspi/agent.sock`
5. If recurring, investigate hardware issue (e.g., I2C device hung)

**Prevention**:
- Implement IPC health checks
- Automatic agent restart on failure
- Hardware operation timeouts
- Better error handling in agent

### 4.5 Failure Pattern: Rate Limit Exceeded

**Symptoms**:
- Requests rejected with 429 status
- "Rate limit exceeded" errors
- Legitimate requests blocked

**Root Causes**:
- Misconfigured rate limits (too strict)
- Client retry loops
- Malicious activity
- Burst traffic

**Detection**:
```promql
rate(raspi_mcp_requests_total{status="rate_limited"}[1m]) > 1
```

**Resolution Steps**:
1. Identify affected client: check audit logs
2. If legitimate, increase rate limits temporarily
3. If malicious, block client (Cloudflare Access)
4. Fix client retry logic

**Prevention**:
- Tune rate limits based on usage patterns
- Implement exponential backoff in clients
- Per-user rate limits
- Monitor rate limit hit rate

### 4.6 Failure Patterns Matrix

| Pattern | Frequency | Severity | MTTR | Prevention Cost |
|---------|-----------|----------|------|-----------------|
| High CPU temp | Common | Medium | 30 min | Low (heatsink) |
| Memory exhaust | Occasional | High | 15 min | Medium (upgrade) |
| SD card corrupt | Rare | Critical | 2 hrs | Medium (quality card) |
| IPC timeout | Occasional | Medium | 10 min | Low (monitoring) |
| Rate limit hit | Common | Low | 5 min | Low (tuning) |
| Update failed | Rare | High | 30 min | Low (rollback) |
| Auth failure | Occasional | Medium | 15 min | Low (monitoring) |

---

## 5. Implementation Checklist

### Phase 1 (Current)
- ✅ Structured logging
- ✅ Basic metrics collection
- ✅ Audit logging
- ⚠️ **ADD**: SLO definitions and monitoring
- ⚠️ **ADD**: Basic Grafana dashboards

### Phase 2+ (Future)
- ⏭️ Distributed tracing with OpenTelemetry
- ⏭️ Error budget tracking and policies
- ⏭️ Automated SLO alerting
- ⏭️ Comprehensive Grafana dashboards
- ⏭️ Failure pattern detection (ML-based)
- ⏭️ Automated runbook execution
- ⏭️ Chaos engineering experiments

---

**End of Document**
