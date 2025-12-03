# 06. System Information & Metrics Module Design

## 1. Document Purpose

- Define the responsibilities, interfaces, and internal design of the system information and metrics modules.
- Describe how these modules collect data from the OS and hardware, and how they expose it via MCP tools.
- Specify the real-time query and historical sampling/storage design, aligned with the tool contracts and JSON Schemas in `05-mcp-tools-interface-and-json-schema-specification.md`.
- Provide implementation guidance for `mcp_raspi.modules.system_info` and `mcp_raspi.modules.metrics` so a developer can start coding.

This document is primarily grounded in:

- Functional requirements FR‑1–FR‑4 in `01-raspberry-pi-mcp-server-requirements-specification.md`.
- Architecture decisions in `02-raspberry-pi-mcp-server-high-level-architecture-design.md`.
- Tool contracts in `05-mcp-tools-interface-and-json-schema-specification.md`.
- Configuration structure in `14-configuration-reference-and-examples.md`.

## 2. Responsibilities

The System Information & Metrics modules are responsible for:

- Providing basic system information:
  - Hardware model, CPU, memory, storage, OS/kernel versions, uptime, hostname, architecture.
  - Exposed via `system.get_basic_info` (FR‑1).
- Providing current runtime health snapshots:
  - CPU utilization, memory/disk usage, temperature, throttling flags, (optionally) basic network metrics.
  - Exposed via `system.get_health_snapshot` (FR‑2).
- Providing real-time metrics compatible with the health snapshot:
  - Exposed via `metrics.get_realtime_metrics` (FR‑3).
- Supporting periodic metrics sampling and local persistence:
  - Exposed via `metrics.start_sampling_job`, `metrics.stop_sampling_job`, `metrics.get_samples` (FR‑3, FR‑4).
- Providing time-window and count-window queries over collected metrics for trend analysis and diagnostics.
- Reporting its own status (sampling failures, missing data sources, degraded capabilities) to the logging/observability module and to capability/introspection tools (for example `system.get_capabilities`).
- Respecting resource and reliability constraints for Raspberry Pi (03 document), including SD card wear and limited memory/CPU.

## 3. Data Sources

### 3.1 System Information

Primary data sources for system information:

- `/proc/cpuinfo`:
  - CPU model, number of cores.
- `/proc/meminfo`:
  - Total and available memory.
- `/proc/uptime`:
  - Uptime in seconds.
- `/etc/os-release`:
  - OS name and version.
- `uname` or equivalent system calls:
  - Kernel version and CPU architecture.
- Raspberry Pi–specific model information:
  - `/proc/device-tree/model` for board model string, when available.
- `psutil` (preferred high-level library):
  - Use where possible for CPU, memory, disk, and uptime abstractions.
  - When `psutil` is not available, fall back to `/proc` and `/sys` as appropriate.

The dependency selection rule follows the guidelines in `02` §2.2:

- Prefer high-level Python libraries (for example `psutil`) if installed and working.
- If a high-level library is missing or fails, fall back to lower-level OS interfaces (`/proc`, `/sys`, shell commands).

### 3.2 Metrics

Metrics extend the system information snapshot with time-series data suitable for trend analysis.

- CPU utilization:
  - Prefer `psutil.cpu_percent` and related calls.
  - Fallback: derive from `/proc/stat` if `psutil` is unavailable.
- Memory usage:
  - Prefer `psutil.virtual_memory`.
  - Fallback: `/proc/meminfo`.
- Disk usage:
  - Prefer `psutil.disk_usage`.
  - Fallback: `os.statvfs` or equivalent.
- CPU temperature and throttling status:
  - `/sys/class/thermal/` sensors.
  - Raspberry Pi tools `vcgencmd measure_temp` and `vcgencmd get_throttled` (if available).
- Basic network throughput and interface state:
  - Prefer `psutil.net_io_counters` and `psutil.net_if_addrs`.
  - Fallback: `/proc/net/dev`, `ip addr` parsing as needed.

For each metric type, the module should:

- Clearly define the units and fields in the `HealthSnapshot` / `MetricSample` models.
- Handle missing or partially available data gracefully (see §6).

## 4. Module Interfaces

### 4.1 Internal API

The modules provide an internal API (service layer) that other parts of the server use:

- `get_basic_info()` → `BasicInfo`:
  - Collects and returns basic system information.
- `get_health_snapshot()` → `HealthSnapshot`:
  - Collects and returns a one-shot health snapshot.
- `get_realtime_metrics()` → `HealthSnapshot` (or a subtype):
  - Returns real-time metrics, initially equivalent to `HealthSnapshot`.
- `start_sampling_job(config: SamplingJobConfig)` → `SamplingJobStatus`:
  - Starts a background sampling job and returns its current status (including `job_id`).
- `stop_sampling_job(job_id: str)` → `SamplingJobStatus`:
  - Stops a sampling job and returns its latest status.
- `get_samples(job_id, since, until, limit)` → `List[MetricSample]`:
  - Queries historical metrics with optional filters.

These internal interfaces are wrapped by MCP tool handlers (`system.*`, `metrics.*`) as defined in document 05.

### 4.2 Mapping to MCP Tools

Tool-to-service mapping:

- `system.get_basic_info` → `SystemInfoService.get_basic_info()`.
- `system.get_health_snapshot` → `SystemInfoService.get_health_snapshot()`.
- `metrics.get_realtime_metrics` → `MetricsService.get_realtime_metrics()`:
  - The initial implementation may internally call `SystemInfoService.get_health_snapshot()`.
- `metrics.start_sampling_job` → `MetricsService.start_sampling_job()`.
- `metrics.stop_sampling_job` → `MetricsService.stop_sampling_job()`.
- `metrics.get_samples` → `MetricsService.get_samples()`.

All MCP tools must follow the handler signature and error handling conventions in `05` §2.5:

- Handlers accept `ToolContext` and a validated parameter dict (derived from Pydantic `ParametersModel`).
- Handlers return domain models (for example `BasicInfo`, `HealthSnapshot`) which are serialized as JSON‑RPC `result`.
- Domain errors are raised as `ToolError` and mapped centrally to JSON‑RPC errors (05 §9.1).

### 4.3 Python Classes & Function Signatures

Define the primary services in:

- `mcp_raspi.modules.system_info`
- `mcp_raspi.modules.metrics`

Example service definitions:

```python
from typing import List, Optional
from mcp_raspi.models.system import BasicInfo, HealthSnapshot
from mcp_raspi.models.metrics import MetricSample, SamplingJobConfig, SamplingJobStatus


class SystemInfoService:
    async def get_basic_info(self) -> BasicInfo: ...

    async def get_health_snapshot(self) -> HealthSnapshot: ...


class MetricsService:
    async def get_realtime_metrics(self) -> HealthSnapshot: ...

    async def start_sampling_job(self, config: SamplingJobConfig) -> SamplingJobStatus: ...

    async def stop_sampling_job(self, job_id: str) -> SamplingJobStatus: ...

    async def get_samples(
        self,
        job_id: Optional[str],
        since: Optional[str],
        until: Optional[str],
        limit: Optional[int],
    ) -> List[MetricSample]: ...
```

Data models (`BasicInfo`, `HealthSnapshot`, `SamplingJobConfig`, `SamplingJobStatus`, `MetricSample`, etc.) must:

- Be defined as Pydantic models in `mcp_raspi.models.system` and `mcp_raspi.models.metrics`.
- Match the JSON Schemas for the corresponding tools in document 05 (see `05` §2.4.7).
- Be used directly in MCP tool handlers to parse parameters and serialize results.

## 5. Sampling & Storage Design

### 5.1 Sampling Model

The sampling subsystem supports zero or more independent sampling jobs. Each job is defined by:

- A unique `job_id`.
- Sampling interval (seconds).
- Retention policy:
  - Either retention duration (hours) or a maximum number of samples.

Sampling jobs can be:

- Started and stopped dynamically via MCP tools.
- Predefined in configuration (for example `metrics.default_jobs` in document 14, Phase 2+).

Example configuration snippet (illustrative YAML):

```yaml
metrics:
  default_jobs:
    - id: "basic-5s"
      interval_seconds: 5
      retention_hours: 24
    - id: "light-60s"
      interval_seconds: 60
      retention_hours: 168
```

Implementation notes:

- Represent job configuration with a `SamplingJobConfig` Pydantic model.
- Represent running job status with `SamplingJobStatus`, including fields such as `job_id`, `interval_seconds`, `retention_hours`, `status`, `started_at`, `last_sample_at`.
- A scheduler component (see §10) is responsible for triggering sampling at configured intervals and writing samples to the storage backend.

### 5.2 Storage Backend

Initial storage backend options:

- SQLite database (preferred, for example `metrics.db` under the `metrics.storage_path` from document 14).
- (Optional, Phase 2+) Time-partitioned JSON/CSV files for extremely lightweight deployments.

Design considerations:

- Write frequency vs. SD card lifetime:
  - Avoid excessively small intervals on SD-backed devices.
  - Allow configuration of minimum sampling interval and max concurrent jobs.
- Read performance:
  - Optimize for time-range queries (by `timestamp` and `job_id`), especially for `metrics.get_samples`.
- Cleanup policy:
  - Implement retention based on time (e.g. `retention_hours`) and/or database size.

For SQLite:

- Use a long-lived connection or a small connection pool to avoid frequent open/close.
- Use WAL (Write‑Ahead Logging) mode to improve write throughput and reduce lock contention.
- Batch inserts in transactions when sampling at high frequency, to reduce `fsync` frequency.
- Consider adding indices on `(job_id, timestamp)` for efficient query.

### 5.3 Data Model

Example SQLite table for metrics samples:

- Table `metrics_samples`:
  - `id` – auto-increment primary key.
  - `timestamp` – ISO 8601 string or integer Unix timestamp.
  - `cpu_usage_percent`.
  - `memory_used_bytes`.
  - `memory_total_bytes`.
  - `disk_used_bytes`.
  - `disk_total_bytes`.
  - `cpu_temperature_celsius`.
  - `net_rx_bytes_per_sec`.
  - `net_tx_bytes_per_sec`.
  - `job_id` – optional; identifies the sampling job that produced the sample.

Mapping to models:

- `MetricSample` should mirror the logical fields above.
- `MetricSamplesResponse` (used by `metrics.get_samples`) should contain an array of `MetricSample` objects, as per the schema in document 05.

## 6. Reliability & Error Handling

The module must be resilient to partial failures and missing data sources.

- When some data sources are temporarily unavailable (for example `vcgencmd` missing, some `/sys` paths absent):
  - Log warnings via the logging module (document 09).
  - Update the capability matrix maintained by the introspection module to mark specific metrics as unavailable (for example “temperature unavailable”, “throttling flags unavailable”).
  - For `system.get_health_snapshot` and `metrics.get_realtime_metrics`:
    - Return partial results when possible.
    - Explicitly set missing fields to `null` rather than failing the entire request.
- For severe errors where meaningful results cannot be produced (for example no metrics sources accessible, unrecoverable SQLite corruption):
  - Raise `ToolError` with an appropriate `error_code` (`failed_precondition`, `unavailable`, or `internal` as defined in document 05 §9.1).
  - Let the JSON‑RPC layer convert this into an error response and log full stack traces.
- When sampling jobs encounter write failures (disk full, I/O errors):
  - Log error-level messages and audit events.
  - Optionally auto-pause the job based on configuration.
  - Reflect the error in `SamplingJobStatus` so that `metrics.get_samples` and introspection tools report the degraded state.
- On startup, perform environment self-checks:
  - Verify presence of key files and commands (`vcgencmd`, `ip`, etc.) and important Python dependencies such as `psutil`.
  - Record capabilities for use by `system.get_capabilities` and related tools.

Error behavior must be consistent with:

- The error model in document 05 (§2.3 and §9).
- Security and hardening strategies in document 04.
- Logging and diagnostics expectations in document 09.

## 7. Performance Considerations

To respect Raspberry Pi resource constraints (document 03), the implementation should:

- Avoid heavy operations per request:
  - No full disk scans or unbounded queries on `metrics_samples` in a single call.
- Use lightweight caching for frequently requested endpoints (health snapshots):
  - Cache the last `HealthSnapshot` along with a timestamp.
  - If a second request arrives within a very short window (for example 1–2 seconds), return the cached snapshot instead of re-sampling.
- Run sampling jobs in background tasks (threads or async tasks):
  - Do not block the main event loop or JSON‑RPC request handling.
- Enforce configuration limits:
  - Maximum number of concurrent sampling jobs.
  - Minimum allowed sampling interval (e.g. 5 seconds).

Optional optimizations:

- Maintain an in-memory cache of the latest few samples for fast `metrics.get_realtime_metrics` responses.
- Add pagination or time-window constraints to `metrics.get_samples` to avoid returning excessive data in one response.
- Consider separate “light” and “full” sample profiles if necessary for very constrained devices.

## 8. Security & Privacy

Security design for this module follows the general security architecture in document 04:

- Scope:
  - The module only accesses and exposes system-level metrics.
  - It must not read or expose application-sensitive data unless explicitly covered in other module designs.
- Output constraints:
  - Avoid exposing detailed file paths, usernames, or other sensitive context in metrics unless required and explicitly documented.
  - Default metrics are coarse (percentages, aggregate counters) rather than detailed resource listings.
- Access control:
  - All MCP tools using this module must pass through the authorization layer described in document 04:
    - Read-only metrics are generally allowed for `viewer` roles.
    - Potentially sensitive operations (for example detailed process views; Phase 2+) may require higher roles.
- Storage security:
  - Metrics storage (SQLite or files) should have appropriate file permissions (see documents 09 and 12).
  - No secrets are stored in metrics; any paths or identifiers written must comply with the overall privacy posture.

## 9. Testing Strategy

The testing strategy for this module must follow the project’s test-driven development (TDD) principles (documents 01 and 11). Tests should be written before or alongside implementation and must be self-contained, using mocks where appropriate.

### 9.1 Unit Tests

High-level goals:

- Cover all public methods of `SystemInfoService`, `MetricsService`, and their helper functions for both success and error paths.
- Ensure that metric calculations and field semantics remain stable over time (tests protect against behavioral regressions).

Specific requirements:

- Parsing functions:
  - For every data source parser (`/proc`, `/sys`, `vcgencmd` output, etc.), write tests that:
    - Validate correct parsing for typical inputs.
    - Cover error and missing-data scenarios.
- Dependency isolation:
  - Use mocks/stubs for `psutil`, SQLite, and time functions to avoid dependency on real hardware, real time, or real disks.
- Model validation:
  - For each Pydantic model (`BasicInfo`, `HealthSnapshot`, `SamplingJobConfig`, `SamplingJobStatus`, `MetricSample`, etc.):
    - Verify field names match the JSON Schemas in document 05.
    - Verify required/optional fields and default values behave as expected.
    - Verify invalid inputs raise validation errors.
- Sampling scheduler:
  - Use a fake `MetricsStore` and virtual time to test:
    - Correct enforcement of sampling intervals and retention policies.
    - Correct state transitions for `SamplingJobStatus` when starting/stopping jobs.

All unit tests must be self-contained:

- Do not depend on real hardware, real network, or actual disk state.
- Use mocks/fixtures to supply alternative implementations and example data.

### 9.2 Integration & End‑to‑End Tests

Integration tests (on actual Raspberry Pi hardware) should verify:

- `SystemInfoService.get_basic_info`:
  - Results are consistent with `uname`, `cat /etc/os-release`, `/proc/cpuinfo`, allowing for minor formatting differences.
- `SystemInfoService.get_health_snapshot` and `MetricsService.get_realtime_metrics`:
  - Values are within a reasonable error range compared to commands such as `top`, `free`, and `df`.

End-to-end tests:

- Invoke MCP tool handlers via JSON‑RPC (for example `system.get_health_snapshot`, `metrics.get_realtime_metrics`) and verify the full pipeline:
  - JSON‑RPC parsing → authentication/authorization → service methods → JSON‑RPC response.
- For `metrics.start_sampling_job` and `metrics.get_samples`:
  - Verify that configured sampling behavior is honored on a real device and that time-window queries return expected samples.

Even when using real hardware, tests should strive for repeatability:

- Use dedicated test sampling jobs.
- Use isolated SQLite database paths for tests to avoid interfering with production data.

### 9.3 Stress & Performance Tests

Stress and performance tests should:

- Measure CPU/memory overhead and response latency under:
  - Fixed QPS for `metrics.get_realtime_metrics`.
  - One or more sampling jobs running concurrently.
- Confirm that under 1 GB RAM and SD/TF card constraints the module remains stable and responsive.

Implementation options:

- Use simple benchmarking scripts or `pytest` with a benchmarking plugin to collect timing data for:
  - Snapshot computation.
  - Sampling write paths (SQLite or file I/O).
  - Metrics query operations.

### 9.4 Resilience & Fault Injection Tests

Fault injection scenarios:

- Disk full or write operations rejected:
  - Simulate via mocked SQLite or filesystem errors.
- `psutil` unavailable or raising exceptions:
  - Replace `psutil` with a failing stub in tests.
- `vcgencmd` missing or returning malformed output:
  - Mock the subprocess calls to simulate different failure modes.

Expected behavior (matching §6):

- When only part of the data is missing:
  - Return partial results with missing fields represented as `null`.
- For severe failures:
  - Raise appropriate `ToolError` with the correct `error_code`.
  - Ensure existing data is not corrupted or lost.
- Capabilities:
  - Verify that the capability matrix is updated appropriately (for example marking “temperature unavailable”) when fault conditions are detected.

### 9.5 TDD & Coverage Requirements

- TDD:
  - When adding new features or changing behavior, update or add tests in this module’s test suite first.
  - For example, when extending `HealthSnapshot` fields or changing sampling strategy, encode the new behavior in tests before changing implementation.
- Coverage:
  - The module should meet the overall coverage target defined in documents 01 and 11:
    - At least 85% line coverage for the module as a whole.
    - Critical paths (configuration parsing, snapshot computation, sampling logic, error handling) should aim for ≥90% coverage.
  - CI must generate coverage reports for `mcp_raspi.modules.system_info` and `mcp_raspi.modules.metrics`, and fail if coverage drops below the configured thresholds.

## 10. Implementation Checklist

- Define and implement unified Pydantic models for:
  - Health snapshots (`HealthSnapshot`).
  - Sampling configuration (`SamplingJobConfig`).
  - Sampling job status (`SamplingJobStatus`).
  - Individual metric samples (`MetricSample`).
  - Ensure they match the JSON Schemas in document 05 for all `system.*` and `metrics.*` tools.
- Implement parsing/adapter functions for each data source:
  - `psutil` abstractions.
  - `/proc`, `/sys`, `vcgencmd`, and other OS-level sources.
  - Keep these adapters separate from service classes to simplify unit testing and future adaptation when dependencies change.
- Implement a metrics storage abstraction:
  - Define a `MetricsStore` interface for inserting, querying, and cleaning up samples.
  - Provide at least a SQLite-based implementation.
  - Encapsulate WAL mode, batch inserts, and other database details inside the store; service layers should only deal with domain concepts.
- Wire configuration into the module:
  - Add metrics-related configuration to `AppConfig` (sampling defaults, max job count, minimum sampling interval, retention policy, SQLite path, etc.) as described in document 14.
  - Load this configuration at startup and pass derived `SamplingJobConfig` instances to the scheduler.
- Implement a sampling scheduler component:
  - Accepts a collection of `SamplingJobConfig` instances.
  - Triggers samples at the configured intervals and writes to `MetricsStore`.
  - Exposes start/stop/query operations which `MetricsService` wraps and exposes via MCP tools.
  - Ensures clean shutdown, stopping jobs and flushing outstanding writes when the process exits.
- Integrate with logging and capabilities:
  - Log warnings and errors when data sources are unavailable or when sampling fails.
  - Update the capability matrix with flags for available metrics and sampling features.
  - Provide capability information to introspection tools such as `system.get_capabilities`.
- Ensure all public APIs (service methods and MCP tool handlers) are covered by tests:
  - Normal and error paths must be exercised.
  - CI must enforce coverage thresholds and TDD expectations as defined in documents 01 and 11.

