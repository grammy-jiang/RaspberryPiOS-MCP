# 07. Service & Process Management Module Design

## 1. Document Purpose

- Define the responsibilities, interfaces, and safety boundaries of the service and process management modules.
- Describe how to safely query and control systemd services and processes on Raspberry Pi devices.
- Align the implementation with the `service.*` and `process.*` MCP tools defined in `05-mcp-tools-interface-and-json-schema-specification.md`.

This document is grounded in:

- Functional requirements FR‑5–FR‑8 in `01-raspberry-pi-mcp-server-requirements-specification.md`.
- Architecture decisions in `02-raspberry-pi-mcp-server-high-level-architecture-design.md`.
- Tool contracts in `05-mcp-tools-interface-and-json-schema-specification.md`.
- Security and auditing requirements in `04-security-oauth-integration-and-access-control-design.md`.

## 2. Responsibilities

The Service & Process Management module is responsible for:

- Exposing a filtered list of running processes and basic filtering for diagnostics:
  - Implemented via `process.list_processes` (FR‑5, FR‑6).
- Providing systemd service status and controlled start/stop/restart operations:
  - Implemented via `service.*` tools (FR‑5, FR‑7).
- Under strict safeguards, sending signals to selected processes (Phase 2+):
  - Implemented via `process.send_signal` (FR‑8, Phase 2+).
- Auditing all service and process state-changing actions (start/stop/restart, enable/disable, signals).
- Enforcing safety policies in coordination with the security module:
  - Role-based authorization (viewer/operator/admin).
  - Whitelists and deny-lists for services and processes.
  - Rate limiting for potentially disruptive operations.

## 3. Data Sources & Dependencies

### 3.1 Process Information

Primary sources:

- `/proc` filesystem:
  - `/proc/[pid]/stat`, `/proc/[pid]/cmdline`, `/proc/[pid]/status`, etc.
- `psutil` library (preferred high-level dependency):
  - Process table, CPU and memory usage, start times.
  - If `psutil` is not available or fails, fall back to parsing `/proc` or invoking `ps` via `subprocess`.

Design considerations:

- Iterating large process tables can be expensive:
  - Use filters early (for example by user or name) where possible.
  - Limit the maximum number of processes returned in one call.
- Respect permission boundaries:
  - The module should not attempt to read more detail than necessary.

### 3.2 Service Information

Primary sources:

- systemd D‑Bus interface (recommended):
  - Access via a Python D‑Bus library such as `dbus-next`.
  - Provides structured service metadata and state.
- `systemctl` CLI:
  - Commands such as `systemctl list-units`, `systemctl status <unit>`, `systemctl is-enabled <unit>`.
  - Accessed via `subprocess` as a fallback when D‑Bus is unavailable.

All operations that change system state (start/stop/restart/reload services, enable/disable units) must be executed via the privileged agent (`raspi-ops-agent`) described in document 02:

- The MCP server validates permissions, constructs a safe request, and sends it to the privileged agent over the internal IPC channel.
- The privileged agent performs the actual D‑Bus / `systemctl` calls with appropriate privileges.

Dependency strategy (consistent with `02` §2.2):

- Prefer high-level libraries (for example `dbus-next`, `psutil`) for clarity and robustness.
- If a high-level dependency is missing or not functional, fall back to standard tools (`systemctl`, `ps`, `/proc`) with careful parsing.

### 3.3 Privileged Agent

- All operations that modify system state must go through the privileged agent:
  - Service start/stop/restart/reload.
  - Enable/disable service autostart.
  - Process signals (Phase 2+).
- The MCP server module:
  - Validates authorization and configuration (whitelists, roles, rate limits).
  - Constructs IPC requests according to the IPC protocol in document 02.
  - Parses IPC responses and maps them into `ServiceStatus`, `ProcessDetails`, or appropriate errors.

## 4. Capabilities

### 4.1 Process Management

Key capabilities:

- List running processes with summary information:
  - Typical fields: `pid`, `ppid`, `user`, `command`, `cpu_percent`, `memory_bytes`, `start_time`.
- Filter processes:
  - By process name (exact or pattern-based).
  - By PID range or explicit PID list.
  - By owning user.
- Retrieve detailed information for a single process:
  - Expanded command line, CPU and memory statistics, open files, etc. (as defined in the JSON Schema).
- Under strict constraints, send signals to processes (Phase 2+):
  - Allowed signals: initially only `TERM`; `KILL` may be disallowed or guarded by additional policies.
  - Only allowed for processes matching whitelist policies (for example specific users or names).

The process summary and detail schemas are defined in document 05. This module must implement the matching Pydantic models (`ProcessSummary`, `ProcessDetails`) and keep them aligned with those schemas.

### 4.2 Service Management

Key capabilities:

- List a subset of systemd services that are managed by the MCP server:
  - Controlled by whitelist patterns from configuration (document 14).
- Query a single service’s status:
  - States such as `active`, `inactive`, `failed`, plus enabled/disabled status.
- Start, stop, restart, and reload services:
  - Always via the privileged agent.
- Enable or disable services at boot (autostart).
- Audit all changes to service state and enabled/disabled flags.

Service summary and status schemas are defined in document 05. This module must implement corresponding Pydantic models (`ServiceSummary`, `ServiceStatus`) and keep them aligned.

### 4.3 Python Classes & Function Signatures

Define the main interfaces in:

- `mcp_raspi.modules.services`
- `mcp_raspi.modules.processes`

Example interfaces:

```python
from typing import List, Optional
from mcp_raspi.models.services import ServiceSummary, ServiceStatus
from mcp_raspi.models.processes import ProcessSummary, ProcessDetails


class ServiceManager:
    async def list_services(
        self,
        state: Optional[str] = None,
        pattern: Optional[str] = None,
    ) -> List[ServiceSummary]: ...

    async def get_status(self, unit_name: str) -> ServiceStatus: ...

    async def control_service(
        self,
        unit_name: str,
        action: str,
        reason: Optional[str],
    ) -> ServiceStatus: ...

    async def set_enabled(self, unit_name: str, enabled: bool) -> ServiceStatus: ...


class ProcessManager:
    async def list_processes(
        self,
        name: Optional[str] = None,
        user: Optional[str] = None,
        pid_min: Optional[int] = None,
        pid_max: Optional[int] = None,
    ) -> List[ProcessSummary]: ...

    async def get_process_details(self, pid: int) -> ProcessDetails: ...

    async def send_signal(
        self,
        pid: int,
        signal_name: str,
        reason: Optional[str],
    ) -> None: ...
```

To decouple system access from business logic, define lower-level adapters and inject them into the managers:

```python
class SystemdClient:
    async def list_units(
        self,
        state: Optional[str],
        pattern: Optional[str],
    ) -> List[ServiceSummary]: ...

    async def get_unit_status(self, unit_name: str) -> ServiceStatus: ...

    async def control_unit(self, unit_name: str, action: str) -> ServiceStatus: ...

    async def set_unit_enabled(self, unit_name: str, enabled: bool) -> ServiceStatus: ...


class ProcfsClient:
    async def list_processes(self, **filters) -> List[ProcessSummary]: ...

    async def get_process(self, pid: int) -> ProcessDetails: ...
```

`ServiceManager` and `ProcessManager`:

- Aggregate these adapters.
- Apply whitelists, role/permission checks, rate limiting, and audit logging.
- Are invoked from MCP tool handlers that implement the JSON‑RPC/MCP boundary.

## 5. MCP Tools Mapping

### 5.1 Process Namespace (`process.*`)

Tool-to-implementation mapping:

- `process.list_processes`
  - Parameters:
    - Optional filters such as name, user, and PID range, as defined in the JSON Schema (document 05).
  - Result:
    - `List[ProcessSummary]` with fields such as `pid`, `ppid`, `user`, `command`, `cpu_percent`, `memory_bytes`, `start_time`.
  - Implementation:
    - Call `ProcessManager.list_processes(...)`.
    - Internally, `ProcessManager` uses `ProcfsClient` and/or `psutil` to get process data and applies filters and whitelist rules.

- `process.get_process_details`
  - Parameters:
    - `pid` (integer).
  - Result:
    - `ProcessDetails`, including full command line, resource usage, and additional attributes as defined by the JSON Schema.
  - Implementation:
    - Call `ProcessManager.get_process_details(pid)`.

- `process.send_signal` (Phase 2+)
  - Parameters:
    - `pid`, `signal` (for example `"TERM"`, `"KILL"`), optional `reason`.
  - Characteristics:
    - Only allowed for processes matching whitelist rules (for example owned by certain users or matching certain names).
    - Requires elevated roles (for example at least `operator`).
  - Implementation:
    - MCP server validates permissions and whitelists.
    - Constructs a privileged IPC request to the `raspi-ops-agent` process handler.
    - Records success/failure in audit logs (document 04).

### 5.2 Service Namespace (`service.*`)

Tool-to-implementation mapping:

- `service.list_services`
  - Parameters:
    - Optional `state` filter (`active`, `failed`, etc.).
    - Optional `pattern` for unit name matching.
  - Result:
    - A list of `ServiceSummary` for services allowed by configuration whitelists.
  - Implementation:
    - Call `ServiceManager.list_services(state, pattern)`.
    - Internally, `ServiceManager` uses `SystemdClient` over D‑Bus (preferred) or `systemctl` to list units, then applies whitelist filters.

- `service.get_status`
  - Parameters:
    - `unit_name`.
  - Result:
    - `ServiceStatus` including state (active/inactive/failed), enabled/disabled, last start time, and last failure details where available.
  - Implementation:
    - Call `ServiceManager.get_status(unit_name)`.

- `service.control_service`
  - Parameters:
    - `unit_name`, `action` (one of `start`, `stop`, `restart`, `reload`), optional `reason`.
  - Behavior:
    - All actions are executed via the privileged agent.
    - Audit logs record each operation (who, which service, action, result).
  - Implementation:
    - MCP handlers call `ServiceManager.control_service(...)`.
    - `ServiceManager` validates whitelists, roles, and rate limits.
    - It then sends a privileged IPC request to `raspi-ops-agent` to perform the actual `systemctl`/D‑Bus operation.

- `service.set_enabled`
  - Parameters:
    - `unit_name`, `enabled` (boolean).
  - Behavior:
    - Controls whether the service starts at boot.
  - Implementation:
    - Call `ServiceManager.set_enabled(unit_name, enabled)` and route through the privileged agent similarly to `control_service`.

## 6. Safety & Guardrails

### 6.1 Whitelisting

Service operations:

- Must be protected by a whitelist:
  - Configuration contains explicit service names and/or patterns that are allowed to be managed.
  - If a requested unit is not whitelisted, the operation is denied and logged.

Process operations:

- Should be restricted by rules such as:
  - Only processes owned by certain users are manageable (for example `mcp`, `www-data`).
  - Certain PIDs (for example PID 1, systemd, the MCP server, and the privileged agent) are always denied.

Example configuration snippet (see document 14 for final structure):

```yaml
tools:
  service:
    allowed_units:
      - "mcp-raspi-*"
      - "nginx.service"
  process:
    allowed_users:
      - "mcp"
      - "www-data"
    deny_pids:
      - 1   # systemd
```

Implementation guidance:

- Centralize whitelist checks in `ServiceManager` and `ProcessManager`.
- For disallowed operations:
  - Raise `ToolError(error_code="permission_denied", ...)`.
  - Include identifiers (service name, PID) in `error.data.details`.
  - Record an audit entry as defined in document 04.

### 6.2 Rate Limiting

To mitigate abuse and accidental disruption:

- Apply rate limits to operations such as:
  - Restarting the same service repeatedly.
  - Sending signals to processes in rapid succession.
- If repeated failures occur in a short time:
  - Treat this as a signal of misconfiguration or possible abuse.
  - Increase log severity and, if configured, emit alerts.

Rate limiting can be implemented:

- In the security module or locally within this module using simple counters:
  - Example policy: “at most one restart per service per minute”.
- When a rate limit is hit:
  - Raise `ToolError(error_code="resource_exhausted", ...)`.
  - Record the event in logs and audit.

### 6.3 Idempotency

Design operations to be as idempotent as possible:

- Calling `stop` on an already stopped service:
  - Should not be treated as a hard error; return a status reflecting that the service is not active.
- Sending a signal to a PID that no longer exists:
  - Should result in a clear `not_found` or `failed_precondition` error, but not corrupt state or crash.

Idempotency simplifies client logic and reduces the risk of repeated or retried operations causing harm.

## 7. Integration with Other Modules

Integration points:

- Security module (document 04):
  - Evaluate caller roles and tool policies to determine whether an operation is allowed.
  - Provide role-based checks for `service.*` and `process.*` tools.
  - Use the audit logging pipeline for all state-changing operations.
- System information & metrics module (document 06):
  - Optionally trigger an additional health snapshot after a service restart to confirm system health.
- Logging & observability module (document 09):
  - Record structured logs for each attempt to control a service or send a signal, including:
    - Service name or PID.
    - Action.
    - Caller identity.
    - Outcome and error codes (if any).

## 8. Testing & Validation

Testing for this module must follow the project’s TDD principles:

- Before implementing or modifying service/process management behavior:
  - Express expected behavior in tests.
  - Then implement or adjust the code until tests pass.
- This ensures long-term consistency and preserves security properties during refactors.

### 8.1 Unit Tests

Coverage targets:

- Parsing of `/proc` and systemd outputs:
  - Include normal, malformed, and missing-field scenarios.
- `SystemdClient` and `ProcfsClient` high-level logic:
  - Use mocks for D‑Bus / `systemctl` and `/proc` data.
- Whitelist and permission checks in `ServiceManager` and `ProcessManager`:
  - Positive cases where operations are allowed.
  - Negative cases for disallowed services, denied PIDs, and insufficient roles.

Self-containment:

- Unit tests must rely only on mocks/stubs:
  - No real systemd or real `/proc` content.
  - Use fake `SystemdClient` / `ProcfsClient` instances or monkeypatch `subprocess` to return fixed outputs.
  - Use static process/service lists for predictable and repeatable tests.
- For each public method (`list_services`, `get_status`, `control_service`, `set_enabled`, `list_processes`, `get_process_details`, `send_signal`):
  - At least one success-path test.
  - At least one failure-path test (for example unauthorized service, denied PID, rate limit hit).

Pydantic model consistency:

- Verify that `ServiceSummary`, `ServiceStatus`, `ProcessSummary`, `ProcessDetails`:
  - Have field names, types, and required/optional flags matching the JSON Schemas in document 05.

### 8.2 Integration & End‑to‑End Tests

Integration tests on a test device:

- Create dedicated test service units (for example `mcp-test-*.service`).
- Verify that:
  - `service.list_services`, `service.get_status`, `service.control_service`, and `service.set_enabled` control the full lifecycle of these units in accordance with the design.
  - Attempts to operate on services that are not whitelisted are rejected with a proper `ToolError` and audit records.

End-to-end tests:

- Use MCP/JSON‑RPC to invoke `service.*` and `process.*` tools and verify the full pipeline:
  - JSON‑RPC request parsing → auth/role checks → whitelist and rate checks → privileged agent call → JSON‑RPC response.
- For `process.list_processes`:
  - Verify that filters (name, user, PID range) behave exactly as documented in the JSON Schema and tool specification.

### 8.3 Security & Abuse‑Resilience Tests

Security-focused tests:

- Attempt to perform `service.control_service` or `process.send_signal` on critical system services/processes:
  - Examples: `sshd`, `systemd`, the MCP server, the privileged agent.
  - Verify that:
    - Operations are rejected by whitelist/permission checks.
    - The error code is `permission_denied`.
    - `error.data.details` includes the target service or PID.
    - Audit logs record the attempted action.

Abuse scenarios:

- High-frequency restart attempts on the same service:
  - Verify that rate limiting triggers and returns `resource_exhausted`.
  - Confirm that warning or higher-severity logs are generated.
- Simulate privileged agent unavailability (IPC connection fails):
  - Verify that tools return `unavailable`.
  - Confirm that logs contain error details for diagnosis.

### 8.4 TDD & Coverage Requirements

Process for adding new features or fixing bugs in this module:

1. Add or update unit/integration tests to express the new behavior or fix.
2. Run tests (they should fail initially).
3. Implement or modify code until all relevant tests pass.

Coverage:

- This module must meet the project-wide coverage target:
  - At least 85% line coverage overall.
  - Critical paths (whitelist and permission checks, rate limiting, privileged call error handling) should aim for ≥90%.
- CI should:
  - Produce coverage reports for `mcp_raspi.modules.services` and `mcp_raspi.modules.processes`.
  - Enforce coverage thresholds and block merges when thresholds are not met.

## 9. Implementation Checklist

- Define stable data models for service and process information:
  - `ServiceSummary`, `ServiceStatus`, `ProcessSummary`, `ProcessDetails`.
  - Ensure they match the JSON Schemas in document 05 (fields, types, required/optional).
  - Use these models directly in MCP tool handlers to avoid duplicated schema definitions.
- Abstract systemd and process access:
  - Implement `SystemdClient` and `ProcfsClient` (and optional `PsutilClient` wrapper).
  - Prefer D‑Bus (`dbus-next`) and `psutil` for structured access.
  - Fall back to `systemctl` / `ps` / `/proc` when dependencies are unavailable, following the dependency strategy in document 02 §2.2.
- Implement whitelist and rules configuration:
  - Configuration must support:
    - Exact service names and simple patterns (for example prefix matches).
    - Allowed users for process operations.
    - Deny-list of PIDs.
  - Centralize checks in the module entry points:
    - For disallowed operations, raise `ToolError(error_code="permission_denied")` and record audit logs.
- Implement `process.send_signal` with multiple layers of protection:
  - Always deny destructive signals to:
    - The MCP server.
    - The privileged agent.
    - Core system processes such as PID 1 (`systemd`).
  - Optionally restrict signals to a safe subset (for example allow `TERM`, disallow `KILL`).
- Integrate with audit logging:
  - For all state-changing operations (service control, signal sending), call the audit log interface with:
    - Timestamp.
    - Caller identity.
    - Target service or PID.
    - Action and parameters.
    - Result (success or error code).
  - Ensure alignment with the audit log structure in document 04.
- Standardize error handling:
  - Use `ToolError` and the error codes from document 05 §9.1:
    - Avoid constructing JSON‑RPC error objects directly in this module.
  - Ensure that error codes and messages are consistent across similar failure modes.
- Maintain TDD discipline:
  - Before introducing new behavior or changing existing behavior, update or add tests based on this design.
  - Keep tests ahead of implementation to prevent regressions in safety behavior.

