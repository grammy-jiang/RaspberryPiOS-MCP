# 11. Testing, Validation & Sandbox Strategy

## 1. Document Purpose

- Define the testing and validation strategy for the Raspberry Pi MCP Server.
- Describe how to build safe test environments for dangerous operations (reboot, shutdown, service control, hardware access).
- Provide guidance for the implementation phase on test frameworks, automation, and sandboxing.

This document ties together:

- Requirements (document 01).
- Architecture (document 02).
- Module designs (documents 04–10).
- Python development standards (document 13).
- Configuration and test matrix (documents 14, `docs/test-matrix.md`).

## 2. Testing Levels

### 2.1 Unit Tests

Goals:

- Validate the correctness of individual functions, classes, and small modules.
- Cover all normal inputs and key exceptional paths (return values and exceptions).

Scope examples:

- Configuration parsing and validation:
  - Default values.
  - File overrides.
  - Environment variable/CLI overrides.
- JSON Schema validation and parameter parsing.
- `/proc`, `/sys`, and command output parsers:
  - Including missing fields and malformed data.
- GPIO/I2C parameter validation and mapping logic:
  - Valid/invalid pins, addresses, data lengths.
- Logging, JSON formatting, and optional rotation behavior.

Requirements:

- Unit tests must:
  - Not depend on real hardware or external services.
  - Use mocks/stubs for:
    - `psutil`, `gpiozero`, `smbus2`, `dbus-next`, `subprocess`, etc.
  - For each public function/method:
    - At least one success-path test.
    - At least one error/boundary-path test.

#### 2.1.1 Implementation Guidelines

Test layout and naming:

- Place tests under the `tests/` directory.
- Use filenames like `test_<module>.py` (see document 13).
- For each public class/function:
  - Use a `Test<ClassOrFunctionName>` test class, or
  - A group of clearly named standalone test functions.
- For async functions:
  - Use `pytest-asyncio` (`@pytest.mark.asyncio`) or equivalent support.

Mocks and dependency injection:

- Avoid real system calls in unit tests:
  - Use `monkeypatch` or `unittest.mock` to replace:
    - `subprocess.run` / `asyncio.create_subprocess_*`.
    - `psutil`/`gpiozero`/`smbus2`/`dbus-next` APIs.
- For IPC clients (`OpsAgentClient`), config loaders, and logging components:
  - Prefer dependency injection of fakes/mocks.
  - Avoid global monkeypatching where a local injection is possible.

Assertion style:

- Beyond return values, assertions should check:
  - Boundary conditions:
    - Range checks.
    - Empty inputs.
    - Extreme parameter values.
  - Raised `ToolError` types and `error_code` values:
    - Must align with document 05.
  - Logging behavior:
    - Using `caplog` or custom handlers to verify structured fields.

#### 2.1.2 Module Coverage Mapping

Per-module unit test coverage expectations:

- System & metrics module (document 06):
  - All public methods in `SystemInfoService` and `MetricsService`:
    - Success and error paths.
  - Parsers for `/proc` and `/sys`:
    - Missing fields.
    - Malformed values.
- Service & process module (document 07):
  - `ServiceManager` and `ProcessManager`:
    - Whitelist checks.
    - Simulated systemd/`psutil` interactions via mocks.
- Device control module (document 08):
  - GPIO/I2C/camera services:
    - Parameter bounds.
    - Whitelist rejections.
    - Rate limit triggers.
- Logging & diagnostics module (document 09):
  - `get_logger`, JSON formatter, and `AuditLogger`:
    - Structure and field injection.
    - Masking behavior.
- Self‑update module (document 10):
  - State machine transitions.
  - `UpdateBackend` implementations.
  - `version.json` read/write logic.

### 2.2 Integration Tests

Goals:

- Validate behavior when multiple modules and components interact:
  - Ensure key workflows behave as expected.

Scope examples:

- MCP server ↔ privileged agent interactions.
- Tool layer ↔ module implementation integration.
- Interactions with OS components:
  - `systemd`.
  - Filesystem.
  - Network configuration.

Integration tests can run:

- On real Raspberry Pi devices.
- In virtual/CI environments that simulate parts of the OS.

#### 2.2.1 Integration Scope & Setup

Minimum integration units:

- MCP server + in‑memory fake IPC client:
  - No real `raspi-ops-agent`.
  - Verifies:
    - Tool routing.
    - Parameter parsing (JSON → Pydantic).
    - Error mapping.
    - Logging and audit logging.
- MCP server + real `raspi-ops-agent` IPC (Unix socket):
  - Privileged operations use mocked hardware backends (virtual GPIO/I2C/etc.).
  - Verifies:
    - IPC protocol.
    - Error propagation.
    - Agent side parameter validation.

Environment requirements:

- In CI or dev:
  - Use containers or VMs to simulate OS behavior (e.g. `systemd` stubs, network).
- On real Raspberry Pi:
  - Perform key-path validation:
    - See `docs/test-matrix.md` for device/environment coverage.

Configuration strategy:

- Use dedicated test configuration files, for example `config.test.yml`:
  - Enable sandbox mode (see §3).
  - Use test‑specific log/data directories.
- Ensure:
  - High‑risk tools (shutdown, OS updates) are either disabled or redirected to mocks/safe no‑ops in test configs.

#### 2.2.2 Example Integration Scenarios

Example scenarios:

- JSON‑RPC → tool execution chain:
  - Construct full MCP JSON‑RPC requests.
  - Validate the chain:
    - Request parsing → Pydantic models → service methods → result models → JSON serialization.
- Server ↔ Agent ↔ OS:
  - Use Unix socket IPC with simulated responses for:
    - GPIO/I2C/service control.
  - Validate:
    - Error propagation from agent to server.
    - Consistent mapping to `ToolError` and JSON‑RPC errors.
- Self‑update:
  - In a controlled environment (e.g. tmp directories):
    - Run an update flow through MCP tools.
    - Validate:
      - State machine transitions.
      - `version.json` changes.
      - systemd restart integration (mocked in CI).

### 2.3 End‑to‑End Tests

End‑to‑end (E2E) tests focus on:

- Real workflows on real hardware where possible.
- From MCP client invocation to physical/hardware behavior or full system effects.

Examples:

- Device control:
  - `gpio.*`, `i2c.*`, `camera.*` on a test board:
    - LED switching.
    - Sensor reads.
    - Photo capture.
- Service & process management:
  - Managing dedicated test services:
    - `mcp-raspi-test.service` units.
  - Confirming whitelist and permission behavior.
- Self‑update and rollback:
  - Controlled updates between “test version A” and “test version B”.
  - Simulated failure and rollback.

Sandbox modes (see §3) determine:

- Whether E2E tests:
  - Actually trigger hardware changes / power operations.
  - Or simulate them safely.

## 3. Sandbox Strategy

### 3.1 Sandbox Modes

The project defines three logical sandbox modes (configured via `testing.sandbox_mode` in `AppConfig`, document 14):

- `full`:
  - All high‑risk operations are simulated or disabled:
    - No real reboot/shutdown, no OS updates, no destructive hardware operations.
  - Suitable for CI and development environments.
- `partial`:
  - Some operations are real, others are simulated:
    - For example:
      - Real GPIO reads/writes on a test board.
      - Simulated reboot/shutdown/OS updates.
  - Useful for hardware‑in‑the‑loop tests.
- `disabled`:
  - Sandbox behavior is disabled:
    - All operations execute as configured.
  - Suitable only for production/fully trusted environments.

Sandbox configuration:

- Controlled via `AppConfig.testing.sandbox_mode`.
- Tool handlers and agents must check this mode before executing high‑risk actions.

### 3.2 High‑Risk Operations

High‑risk operations include:

- Power and OS:
  - `system.reboot`, `system.shutdown`.
  - OS update tools (`manage.preview_os_updates`, `manage.apply_os_updates` – Phase 2+).
- Self‑update:
  - `manage.update_server`.
- Service/process control:
  - `service.control_service`.
  - `service.set_enabled`.
  - `process.send_signal` (Phase 2+).
- Device control:
  - GPIO writes/PWM:
    - `gpio.write_pin`, `gpio.set_pwm`.
  - I2C writes:
    - `i2c.write`.
  - Camera capture:
    - `camera.take_photo` (can impact storage and privacy).

Sandbox rules (examples):

- `full`:
  - Replace all high‑risk operations with:
    - No‑ops.
    - Logged “would have performed X” entries.
  - Ensure no actual system changes occur.
- `partial`:
  - Define per-tool behavior:
    - Real operations for certain devices/boards.
    - Simulated behavior for others.
  - For example:
    - Real GPIO operations on test pins.
    - No real reboot/shutdown.
- `disabled`:
  - No sandbox overrides.
  - Tools follow normal behavior and security constraints.

### 3.3 Implementation Hooks

Sandbox enforcement points:

- MCP tool handlers:
  - Before calling service methods or `OpsAgentClient`:
    - Check `testing.sandbox_mode`.
    - Adjust behavior accordingly (e.g. raise `ToolError(failed_precondition)` in `full` mode for certain tools).
- Privileged agent handlers:
  - Double‑check sandbox mode (derived from configuration supplied at startup).
  - Ensure that:
    - Even if MCP server misses a sandbox check, the agent enforces sandbox policies.

Configuration examples:

- In `AppConfig.testing` (document 14):
  - Fields such as:
    - `sandbox_mode: "full" | "partial" | "disabled"`.
    - Optional per‑tool overrides for test environments.

## 4. Module‑Specific Testing Guidance

### 4.1 System Information & Metrics

Key aspects:

- Based on documents 05 and 06:
  - Use JSON Schema definitions as assertions:
    - For example CPU usage is between 0–100.
    - Memory/disk values are non‑negative.
- Unit tests:
  - Construct synthetic `/proc`/`/sys` outputs and `psutil` return values:
    - Cover missing fields.
    - Cover abnormal data.
- Integration tests:
  - On real devices:
    - Compare `system.get_health_snapshot` results vs `top`/`free`/`df` within a reasonable tolerance.
  - Under load:
    - Measure CPU/memory overhead.
    - Verify that frequent health calls do not starve other operations.

### 4.2 Service & Process Management

Key aspects:

- Service management:
  - Use dedicated test units (e.g. `mcp-raspi-test.service`).
  - Verify:
    - `service.list_services`, `service.get_status`, `service.control_service`, `service.set_enabled` behavior.
- Whitelisting:
  - Ensure:
    - Non‑whitelisted services produce `permission_denied`.
    - Attempts on critical services (e.g. SSH) are rejected and logged/audited.
- Process tools:
  - Test:
    - Filtering and pagination.
    - Error handling for non‑existent PIDs and permission errors.

### 4.3 Device Control

Key aspects:

- Hardware tests:
  - Use LEDs, fans, relays on a test board:
    - Verify whitelists and PWM limits.
    - Confirm state safety after restarts.
- Simulated tests:
  - Use in‑memory simulations for GPIO/I2C devices:
    - Validate:
      - Parameter validation.
      - Whitelist behavior.
      - Rate limiting.

Failure injection:

- Simulate:
  - Missing devices or bus errors.
  - Ensure `ToolError` with:
    - `unavailable`.
    - Or `failed_precondition` as appropriate.
  - Confirm proper logging and audit.

### 4.4 Self‑Update & Rollback

Key aspects:

- End‑to‑end in isolated environments:
  - Test full self‑update and rollback flows.
- Failure scenarios:
  - Network interruptions.
  - Disk full.
  - Signature/hash validation failures (if implemented).

Cross‑references:

- Based on documents 05 and 10:
  - Validate:
    - `manage.update_server` state machine behavior.
    - `version.json` updates.
    - Automatic/manual rollbacks.
  - Use `manage.get_server_status.last_update` and log query tools:
    - Cross‑check update history and outcomes.
- OS updates (Phase 2+):
  - In safe test environments:
    - Test `manage.preview_os_updates` and `manage.apply_os_updates`.
    - Verify APT output consistency and error handling.

## 5. Automation & CI

### 5.1 Recommended Development Commands (Python + uv)

The project uses Python managed by `uv` (see document 13). Example development commands:

```bash
# Create and activate virtual environment (if desired)
uv venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dev dependencies (assuming [project.optional-dependencies].dev in pyproject.toml)
uv pip install -e ".[dev]"

# Run unit and integration tests
uv run pytest

# Run coverage
uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing

# Run linting and formatting
uv run ruff check src tests
uv run ruff format src tests

# (Future) run local MCP server and privileged agent instances
uv run python -m mcp_raspi.server.app
sudo uv run python -m mcp_raspi_ops.main
```

These commands are planning guidance; actual usability depends on later code and configuration, and must stay aligned with `13-python-development-standards-and-tools.md`.

### 5.2 CI Pipeline Structure

Recommended CI jobs:

- `lint`:
  - Run `ruff` (and optionally `mypy`).
- `unit`:
  - Run all unit tests with mocks:
    - No real hardware or OS dependencies.
- `integration`:
  - Run integration tests:
    - In containers or lightweight VMs.
- `hardware-e2e` (optional):
  - Run end‑to‑end tests on real Raspberry Pi devices (self‑hosted runner).

CI simulation strategies:

- For GPIO/I2C and other hardware:
  - Use mocks/stubs; avoid real hardware in CI.
- For `systemd`:
  - Use minimal substitutes or simulated command outputs in containers.

Gating strategy:

- All PRs:
  - Must pass `lint` + `unit`.
- Changes to critical modules:
  - Self‑update.
  - Power control.
  - OS updates.
  - Security and authorization.
  - Should additionally require `integration` or `hardware-e2e` to pass.

## 6. Documentation & Acceptance

### 6.1 Test Artefacts

Each major module/subsystem must have:

- Test implementations:
  - Pytest test files under `tests/`.
- Brief descriptions:
  - Either in the corresponding module design documents (06–10).
  - Or referenced from this document.
- Failure analysis guidance:
  - In the operations runbook (document 12), link common failure cases (self‑update failure, device control issues) to test scenarios:
    - Helps operations reproduce and diagnose issues.

Test outputs:

- CI should retain:
  - Unit and integration test logs.
  - Coverage reports (text or HTML).

### 6.2 Acceptance Criteria

Before a major release, define and execute a concise acceptance checklist (smoke tests) based on FR/NFRs. At minimum:

- Basic usability:
  - MCP server:
    - Starts.
    - Accepts connections.
  - `system.get_basic_info` / `system.get_health_snapshot`:
    - Return reasonable data.
- Security and high‑risk operations:
  - With default configuration:
    - High‑risk tools (shutdown, self‑update, OS updates) are:
      - Disabled, or
      - Restricted to `admin` role.
  - From non‑authorized roles:
    - These tools must:
      - Return `permission_denied` or `failed_precondition`.
      - Emit audit log entries.
- Logging and audit:
  - Application and audit logs:
    - Are written to configured locations.
    - Can be queried via `logs.get_recent_app_logs` and `logs.get_recent_audit_logs`.
  - Critical operations (reboot, self‑update, service control):
    - Always produce audit entries.
- Self‑update and rollback (document 10):
  - In a test environment:
    - Successfully execute `manage.update_server`:
      - Validate version switch and `version.json` update.
  - Simulate a failed update:
    - Verify automatic or manual rollback restores the previous known good version.

The acceptance checklist should be stored in the repository (see `docs/acceptance-checklist.md`) and updated as features evolve.

### 6.3 FR → Test Mapping

For each key functional requirement (FR‑1…FR‑28, document 01), maintain a mapping:

- FR → implementation modules → test cases.

Example:

- `FR‑21 (self‑update capability)` →
  - Implementation:
    - `UpdateService`.
    - `manage.update_server`.
  - Tests:
    - `tests/update/test_update_service.py::test_successful_update`.
    - `tests/update/test_update_rollback.py::test_autorollback_on_boot_failure`.

Uses:

- Ensure each FR has:
  - At least one success-path test.
  - At least one major error‑path test.
- During requirement changes:
  - Quickly locate affected implementation and tests.
- During regression analysis:
  - Determine whether new tests cover the relevant FR.

Maintenance suggestion:

- Start with a simple table:
  - Markdown in `docs/test-matrix.md`, or a dedicated YAML file.
- Over time:
  - CI can validate that referenced tests still exist and pass.

## 7. Minimal Test Matrix

Define a minimal test matrix early in implementation, including:

- Device dimension:
  - At least one lower‑spec device:
    - For example Pi 3 or Zero 2W.
  - At least one higher‑spec device:
    - For example Pi 4 or Pi 5.
- Environment dimension:
  - Development:
    - Local/VM environments.
  - Test:
    - Real devices with sandbox mode enabled.
  - Pre‑production/production:
    - Real devices with sandbox disabled and realistic configuration.
- Functional dimension:
  - System info and metrics.
  - Service and process management.
  - Device control and reboot/shutdown:
    - In sandbox and non‑sandbox modes.
  - Self‑update and rollback.
  - Security and audit (access control, rate limits).

### 7.1 Matrix‑Driven Planning

Use the matrix to plan test execution:

- Not all combinations need full coverage.
- Ensure at least:
  - Each functional dimension is fully validated on:
    - At least one low‑spec device.
    - At least one high‑spec device.
  - Key functions (for example self‑update, power control) are validated in:
    - Sandbox mode.
    - Non‑sandbox mode.
    - Example:
      - Self‑update in sandbox mode:
        - Logs intent only.
      - Self‑update in real mode:
        - Actually switches versions.

Record the matrix as a table in `docs/test-matrix.md` and annotate:

- Which scenarios are covered by automated unit/integration tests in CI.
- Which require manual or semi‑automated execution on real devices.

### 7.2 Example Assignments

- Development/CI:
  - Use local or CI containers to:
    - Cover most unit and integration tests.
    - Simulate basic system info/service management/self‑update state machine flows.
- Real low‑spec device (Pi 3/Zero 2W):
  - Validate:
    - Resource usage (CPU, memory) under realistic load.
    - Self‑update responsiveness and impact.
    - Device control (GPIO/I2C) behavior and stability on constrained hardware.
- Real high‑spec device (Pi 4/5):
  - Run most hardware E2E tests:
    - Camera.
    - Self‑update and rollback.
    - OS update preview (Phase 2+).

This matrix helps ensure reasonable coverage across device and environment combinations with limited hardware.

## 8. Coverage Targets

### 8.1 Global Targets

- Overall line coverage target:
  - **At least 85%**.
- For critical modules (security, configuration loading, self‑update, privileged IPC, dangerous operation safeguards):
  - Aim for **90%+** coverage.

Coverage collection:

- Use `pytest-cov`:
  - Integrated with `uv run` as per §5.1 and document 13.
- In CI:
  - Enforce thresholds:
    - For example:
      - `--cov-fail-under=85`.
  - Fail builds below thresholds.

On resource‑constrained devices:

- Full coverage runs may be limited to:
  - Developer/CI environments.
- On target Raspberry Pi devices:
  - Run only key subsets of tests:
    - Smoke tests.
    - Self‑update and device control E2E.

### 8.2 Per‑Module Targets

Suggested module‑level coverage goals (can be tightened over time):

- Configuration loading and security modules:
  - ≥ 90% line coverage.
  - Emphasis on all decision branches.
- Self‑update and rollback module (document 10):
  - ≥ 90% coverage.
  - All states and transitions of the state machine.
- Privileged IPC modules:
  - ≥ 90% coverage.
  - Normal and error paths.
- Logging and audit modules:
  - ≥ 85% coverage.
  - Structured field injection and error handling.
- Device control and service management:
  - ≥ 80–85% coverage.
  - Recognize that certain hardware behaviors may be difficult to simulate fully.

### 8.3 Practical Considerations

Tools and commands:

- Use:
  - `pytest-cov`.
  - `uv run` (see §5.1) to generate coverage reports.
- In CI:
  - Run with:
    - `--cov=mcp_raspi --cov=mcp_raspi_ops --cov-fail-under=85`.
  - For key modules:
    - Optionally use:
      - `--cov-branch`.
      - Module‑specific thresholds (Phase 2+).

Coverage vs quality:

- Coverage is a minimum bar, not the sole objective:
  - TDD should drive behavior:
    - New features are described in tests first, then implemented.
  - For critical paths (security, self‑update, power control):
    - Regularly review test quality and scenario completeness even if numeric coverage is high.

Resource‑constrained strategy:

- Full tests and coverage on:
  - Development machines.
  - CI infrastructure.
- Subset of tests on:
  - Target Raspberry Pi devices.
  - Focus on critical behavior validation.


---

<!-- Merged from 11-addendum-testing-validation-enhancements.md -->


## 1. Performance Benchmarks & Targets

### 1.1 Overview

Define quantitative performance targets for the MCP server to ensure acceptable responsiveness on constrained Raspberry Pi hardware.

**Testing Approach**:
- Benchmark on all supported devices (Pi 3, 4, 5, Zero 2W)
- Test under various load conditions
- Monitor resource consumption (CPU, memory, I/O)
- Establish baseline and regression detection

### 1.2 Performance Targets by Device

#### Raspberry Pi 5 (Quad-core Cortex-A76, 8GB RAM)

| Metric | Target | Maximum |
|--------|--------|---------|
| **Startup Time** | < 2s | < 3s |
| **MCP Tool Response (simple)** | < 50ms | < 100ms |
| **MCP Tool Response (complex)** | < 200ms | < 500ms |
| **IPC Roundtrip Latency** | < 5ms | < 10ms |
| **Memory Usage (idle)** | < 50MB | < 80MB |
| **Memory Usage (active)** | < 150MB | < 250MB |
| **CPU Usage (idle)** | < 5% | < 10% |
| **Sustained Requests/sec** | > 100 | > 50 |

#### Raspberry Pi 4 (Quad-core Cortex-A72, 4GB RAM)

| Metric | Target | Maximum |
|--------|--------|---------|
| **Startup Time** | < 3s | < 5s |
| **MCP Tool Response (simple)** | < 100ms | < 200ms |
| **MCP Tool Response (complex)** | < 300ms | < 800ms |
| **IPC Roundtrip Latency** | < 8ms | < 15ms |
| **Memory Usage (idle)** | < 50MB | < 80MB |
| **Memory Usage (active)** | < 150MB | < 250MB |
| **CPU Usage (idle)** | < 8% | < 15% |
| **Sustained Requests/sec** | > 50 | > 25 |

#### Raspberry Pi 3 B+ (Quad-core Cortex-A53, 1GB RAM)

| Metric | Target | Maximum |
|--------|--------|---------|
| **Startup Time** | < 5s | < 8s |
| **MCP Tool Response (simple)** | < 150ms | < 300ms |
| **MCP Tool Response (complex)** | < 500ms | < 1200ms |
| **IPC Roundtrip Latency** | < 12ms | < 25ms |
| **Memory Usage (idle)** | < 40MB | < 60MB |
| **Memory Usage (active)** | < 120MB | < 180MB |
| **CPU Usage (idle)** | < 10% | < 20% |
| **Sustained Requests/sec** | > 20 | > 10 |

#### Raspberry Pi Zero 2 W (Quad-core Cortex-A53, 512MB RAM)

| Metric | Target | Maximum |
|--------|--------|---------|
| **Startup Time** | < 8s | < 12s |
| **MCP Tool Response (simple)** | < 200ms | < 400ms |
| **MCP Tool Response (complex)** | < 800ms | < 2000ms |
| **IPC Roundtrip Latency** | < 20ms | < 40ms |
| **Memory Usage (idle)** | < 30MB | < 50MB |
| **Memory Usage (active)** | < 80MB | < 120MB |
| **CPU Usage (idle)** | < 15% | < 25% |
| **Sustained Requests/sec** | > 10 | > 5 |

### 1.3 Tool-Specific Performance Targets

#### System Information Tools

| Tool | Pi 5 | Pi 4 | Pi 3 | Zero 2W |
|------|------|------|------|---------|
| `system.get_info` | < 20ms | < 30ms | < 50ms | < 80ms |
| `system.get_health` | < 30ms | < 50ms | < 80ms | < 120ms |
| `metrics.get_snapshot` | < 40ms | < 70ms | < 120ms | < 180ms |
| `metrics.query_history` | < 100ms | < 150ms | < 250ms | < 400ms |

#### Device Control Tools

| Tool | Pi 5 | Pi 4 | Pi 3 | Zero 2W |
|------|------|------|------|---------|
| `gpio.read_pin` | < 5ms | < 8ms | < 12ms | < 20ms |
| `gpio.write_pin` | < 8ms | < 12ms | < 20ms | < 35ms |
| `i2c.scan_bus` | < 50ms | < 80ms | < 120ms | < 200ms |
| `i2c.read_device` | < 10ms | < 15ms | < 25ms | < 40ms |
| `camera.capture` | < 500ms | < 800ms | < 1200ms | < 2000ms |

#### Service Management Tools

| Tool | Pi 5 | Pi 4 | Pi 3 | Zero 2W |
|------|------|------|------|---------|
| `service.list` | < 100ms | < 150ms | < 250ms | < 400ms |
| `service.get_status` | < 30ms | < 50ms | < 80ms | < 120ms |
| `service.start` | < 200ms | < 350ms | < 600ms | < 1000ms |
| `process.list` | < 80ms | < 120ms | < 200ms | < 350ms |

### 1.4 Benchmark Test Suite

```python
# tests/benchmarks/test_performance.py

import pytest
import time
import psutil
import statistics
from typing import List

class PerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.fixture
    def device_targets(self):
        """Get performance targets for current device."""
        # Detect device model
        model = self._detect_device_model()

        targets = {
            "pi5": {"simple_tool_ms": 50, "complex_tool_ms": 200},
            "pi4": {"simple_tool_ms": 100, "complex_tool_ms": 300},
            "pi3": {"simple_tool_ms": 150, "complex_tool_ms": 500},
            "zero2w": {"simple_tool_ms": 200, "complex_tool_ms": 800},
        }

        return targets.get(model, targets["pi3"])  # Default to Pi 3

    @pytest.mark.benchmark
    @pytest.mark.repeat(100)
    async def test_system_get_info_latency(self, mcp_client, device_targets):
        """Benchmark system.get_info latency."""
        latencies: List[float] = []

        for _ in range(100):
            start = time.perf_counter()
            result = await mcp_client.call_tool("system.get_info", {})
            end = time.perf_counter()

            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

        # Calculate statistics
        p50 = statistics.median(latencies)
        p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p99 = statistics.quantiles(latencies, n=100)[98]  # 99th percentile

        print(f"\nsystem.get_info latency (ms):")
        print(f"  p50: {p50:.2f}")
        print(f"  p95: {p95:.2f}")
        print(f"  p99: {p99:.2f}")

        # Assert p95 meets target
        assert p95 < device_targets["simple_tool_ms"], \
            f"p95 latency {p95:.2f}ms exceeds target {device_targets['simple_tool_ms']}ms"

    @pytest.mark.benchmark
    async def test_memory_usage_idle(self, mcp_server_process):
        """Benchmark idle memory usage."""
        # Wait for server to stabilize
        await asyncio.sleep(5)

        # Measure memory
        process = psutil.Process(mcp_server_process.pid)
        mem_info = process.memory_info()
        rss_mb = mem_info.rss / (1024 * 1024)

        print(f"\nMemory usage (idle): {rss_mb:.2f} MB")

        # Get target for device
        model = self._detect_device_model()
        targets = {
            "pi5": 80,
            "pi4": 80,
            "pi3": 60,
            "zero2w": 50
        }
        max_mb = targets.get(model, 80)

        assert rss_mb < max_mb, \
            f"Idle memory {rss_mb:.2f}MB exceeds target {max_mb}MB"

    @pytest.mark.benchmark
    async def test_sustained_throughput(self, mcp_client, device_targets):
        """Benchmark sustained request throughput."""
        duration_seconds = 30
        start_time = time.time()
        request_count = 0
        errors = 0

        while time.time() - start_time < duration_seconds:
            try:
                await mcp_client.call_tool("system.get_info", {})
                request_count += 1
            except Exception as e:
                errors += 1

        elapsed = time.time() - start_time
        throughput = request_count / elapsed

        print(f"\nSustained throughput:")
        print(f"  Requests: {request_count}")
        print(f"  Errors: {errors}")
        print(f"  Duration: {elapsed:.2f}s")
        print(f"  Throughput: {throughput:.2f} req/s")

        # Get minimum throughput target
        model = self._detect_device_model()
        targets = {
            "pi5": 50,
            "pi4": 25,
            "pi3": 10,
            "zero2w": 5
        }
        min_rps = targets.get(model, 10)

        assert throughput >= min_rps, \
            f"Throughput {throughput:.2f} req/s below target {min_rps} req/s"

    @pytest.mark.benchmark
    async def test_startup_time(self, mcp_server_launcher):
        """Benchmark server startup time."""
        measurements = []

        for _ in range(5):
            start = time.perf_counter()
            proc = await mcp_server_launcher.start()
            # Wait for health check
            await self._wait_for_health(proc)
            end = time.perf_counter()

            startup_time = end - start
            measurements.append(startup_time)

            await mcp_server_launcher.stop(proc)
            await asyncio.sleep(2)  # Cool down

        avg_startup = statistics.mean(measurements)
        print(f"\nAverage startup time: {avg_startup:.2f}s")

        # Get target
        model = self._detect_device_model()
        targets = {
            "pi5": 3.0,
            "pi4": 5.0,
            "pi3": 8.0,
            "zero2w": 12.0
        }
        max_seconds = targets.get(model, 8.0)

        assert avg_startup < max_seconds, \
            f"Startup time {avg_startup:.2f}s exceeds target {max_seconds}s"

    def _detect_device_model(self) -> str:
        """Detect Raspberry Pi model."""
        try:
            with open("/proc/device-tree/model", "r") as f:
                model_str = f.read().lower()

            if "raspberry pi 5" in model_str:
                return "pi5"
            elif "raspberry pi 4" in model_str:
                return "pi4"
            elif "raspberry pi 3" in model_str:
                return "pi3"
            elif "raspberry pi zero 2" in model_str:
                return "zero2w"
        except:
            pass

        return "unknown"
```

### 1.5 Running Benchmarks

```bash
# Run all benchmarks
pytest tests/benchmarks/ -v --benchmark

# Run specific benchmark
pytest tests/benchmarks/test_performance.py::test_system_get_info_latency -v

# Generate benchmark report
pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark-results.json

# Compare with baseline
pytest-benchmark compare baseline.json benchmark-results.json
```

---

## 2. Load Testing Strategy

### 2.1 Overview

Load testing validates system behavior under high concurrent load and identifies breaking points.

**Goals**:
- Identify maximum sustainable load
- Detect resource leaks
- Validate rate limiting
- Test graceful degradation

### 2.2 Load Testing Tools

**Tool**: Locust (Python-based load testing)

```python
# tests/load/locustfile.py

from locust import User, task, between, events
import json
import random

class MCPClient:
    """MCP JSON-RPC client for load testing."""

    def __init__(self):
        # Initialize stdio communication with MCP server
        pass

    def call_tool(self, method: str, params: dict) -> dict:
        """Call MCP tool and return result."""
        request = {
            "jsonrpc": "2.0",
            "id": random.randint(1, 1000000),
            "method": method,
            "params": params
        }

        # Send request and get response
        # ...
        return response

class MCPUser(User):
    """Simulated MCP client user."""

    wait_time = between(1, 5)  # Wait 1-5 seconds between requests

    def on_start(self):
        """Initialize client."""
        self.client = MCPClient()

    @task(10)  # Weight: 10 (most common)
    def get_system_info(self):
        """Call system.get_info."""
        with events.request.measure("mcp", "system.get_info"):
            self.client.call_tool("system.get_info", {})

    @task(5)
    def get_health(self):
        """Call system.get_health."""
        with events.request.measure("mcp", "system.get_health"):
            self.client.call_tool("system.get_health", {})

    @task(3)
    def read_gpio(self):
        """Call gpio.read_pin."""
        pin = random.choice([17, 27, 22])
        with events.request.measure("mcp", "gpio.read_pin"):
            self.client.call_tool("gpio.read_pin", {"pin": pin})

    @task(2)
    def list_processes(self):
        """Call process.list."""
        with events.request.measure("mcp", "process.list"):
            self.client.call_tool("process.list", {})

    @task(1)
    def query_metrics(self):
        """Call metrics.query_history."""
        with events.request.measure("mcp", "metrics.query_history"):
            self.client.call_tool("metrics.query_history", {
                "metric_name": "cpu.percent",
                "limit": 100
            })
```

### 2.3 Load Test Scenarios

#### Scenario 1: Baseline Load (Normal Operation)

```bash
# 10 concurrent users, 5 minute duration
locust -f tests/load/locustfile.py --users 10 --spawn-rate 2 --run-time 5m --headless
```

**Expected**:
- All requests succeed
- Response times within targets
- No memory leaks
- CPU < 50% on Pi 4

#### Scenario 2: Peak Load

```bash
# 50 concurrent users, 10 minute duration
locust -f tests/load/locustfile.py --users 50 --spawn-rate 5 --run-time 10m --headless
```

**Expected**:
- 95%+ requests succeed
- Some increased latency acceptable
- Rate limiting engages if configured
- Graceful degradation (no crashes)

#### Scenario 3: Stress Test (Beyond Capacity)

```bash
# 100 concurrent users, ramp up over 5 minutes
locust -f tests/load/locustfile.py --users 100 --spawn-rate 10 --run-time 15m --headless
```

**Expected**:
- Identify breaking point
- Server remains stable (no crashes)
- Rate limiting protects system
- Recovery after load decrease

### 2.4 Load Test Success Criteria

| Metric | Baseline Load | Peak Load | Stress Test |
|--------|---------------|-----------|-------------|
| **Success Rate** | > 99% | > 95% | > 80% |
| **p95 Latency** | < 200ms | < 500ms | < 2s |
| **Memory Growth** | < 10MB | < 30MB | < 50MB |
| **CPU (avg)** | < 30% | < 60% | < 90% |
| **Errors/min** | < 5 | < 20 | < 100 |
| **Recovery Time** | N/A | < 30s | < 2min |

---

## 3. Fuzz Testing Strategy

### 3.1 Overview

Fuzz testing sends malformed, unexpected, or random inputs to discover crashes, hangs, or security vulnerabilities.

**Tools**:
- **Atheris**: Python fuzzing engine (libFuzzer-based)
- **Hypothesis**: Property-based testing
- **Custom fuzzer**: MCP protocol fuzzer

### 3.2 MCP Protocol Fuzzer

```python
# tests/fuzz/test_mcp_fuzzer.py

import atheris
import sys
import json
from mcp_raspi.server import MCPServer

def TestOneInput(data):
    """Fuzz MCP server with random input."""
    try:
        # Try to parse as JSON
        try:
            request = json.loads(data)
        except:
            # Send raw bytes
            request = data

        # Create server instance
        server = MCPServer()

        # Process request (should not crash)
        try:
            result = server.handle_request(request)
        except Exception as e:
            # Expected exceptions are OK (validation errors, etc.)
            # Only crashes/hangs are failures
            pass

    except Exception as e:
        # Unexpected exception - report
        print(f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
```

### 3.3 Input Validation Fuzzing

```python
# tests/fuzz/test_input_validation.py

from hypothesis import given, strategies as st, settings
from mcp_raspi.models import GpioPinRequest
from pydantic import ValidationError

@given(
    pin=st.integers(),
    pull_mode=st.text(),
    bounce_time_ms=st.floats()
)
@settings(max_examples=1000)
def test_gpio_pin_request_fuzzing(pin, pull_mode, bounce_time_ms):
    """Fuzz GPIO pin request validation."""
    try:
        request = GpioPinRequest(
            pin=pin,
            pull_mode=pull_mode,
            bounce_time_ms=bounce_time_ms
        )

        # If validation passed, check values are sane
        assert 1 <= request.pin <= 40
        assert request.pull_mode in ["up", "down", "none"]
        assert 0 <= request.bounce_time_ms <= 1000

    except ValidationError:
        # Validation error is expected for invalid input
        pass
    except Exception as e:
        # Any other exception is a bug
        pytest.fail(f"Unexpected exception: {e}")

@given(
    address=st.integers(),
    register=st.integers(),
    data=st.binary()
)
@settings(max_examples=1000)
def test_i2c_request_fuzzing(address, register, data):
    """Fuzz I2C request validation."""
    try:
        request = I2CWriteRequest(
            bus=1,
            address=address,
            register=register,
            data=list(data)
        )

        # Check validation passed with valid values
        assert 0x00 <= request.address <= 0x7F
        assert 0x00 <= request.register <= 0xFF
        assert len(request.data) <= 32

    except ValidationError:
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e}")
```

### 3.4 Security-Focused Fuzzing

```python
# tests/fuzz/test_security_fuzzing.py

from hypothesis import given, strategies as st
import json

# SQL injection attempts (even though we use SQLite params)
SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE users--",
    "1' OR '1'='1",
    "admin'--",
    "' UNION SELECT NULL--"
]

# Command injection attempts
COMMAND_INJECTION_PAYLOADS = [
    "; ls -la",
    "| cat /etc/passwd",
    "$(whoami)",
    "`reboot`",
    "&& rm -rf /"
]

# Path traversal attempts
PATH_TRAVERSAL_PAYLOADS = [
    "../../etc/passwd",
    "/etc/shadow",
    "../../../root/.ssh/id_rsa",
    "....//....//etc/passwd"
]

@given(payload=st.sampled_from(SQL_INJECTION_PAYLOADS))
async def test_sql_injection_resistance(mcp_client, payload):
    """Test resistance to SQL injection."""
    try:
        # Try injecting into various string parameters
        await mcp_client.call_tool("metrics.query_history", {
            "metric_name": payload,
            "limit": 100
        })

        await mcp_client.call_tool("logs.query", {
            "search_text": payload
        })

    except Exception as e:
        # Should fail validation, not execute SQL
        assert "syntax error" not in str(e).lower()

@given(payload=st.sampled_from(COMMAND_INJECTION_PAYLOADS))
async def test_command_injection_resistance(mcp_client, payload):
    """Test resistance to command injection."""
    try:
        # Try injecting into service names, GPIO pin labels, etc.
        await mcp_client.call_tool("service.get_status", {
            "service_name": f"nginx{payload}"
        })

    except Exception as e:
        # Should fail validation, not execute command
        pass

@given(payload=st.sampled_from(PATH_TRAVERSAL_PAYLOADS))
async def test_path_traversal_resistance(mcp_client, payload):
    """Test resistance to path traversal."""
    try:
        # Try reading arbitrary files
        await mcp_client.call_tool("logs.query", {
            "log_file": payload
        })

    except Exception as e:
        # Should block access to unauthorized paths
        assert "permission denied" in str(e).lower() or \
               "invalid path" in str(e).lower()
```

### 3.5 Running Fuzz Tests

```bash
# Hypothesis-based fuzzing (quick)
pytest tests/fuzz/ -v

# Atheris-based fuzzing (long-running)
python tests/fuzz/test_mcp_fuzzer.py -atheris_runs=1000000

# Security fuzzing
pytest tests/fuzz/test_security_fuzzing.py -v --hypothesis-show-statistics
```

---

## 4. Security Testing Tools (Phase 2+)

### 4.1 Overview

Automated security testing identifies common vulnerabilities before deployment.

**Tools**:
- **Bandit**: Python security linter
- **Safety**: Dependency vulnerability scanner
- **OWASP ZAP**: Web application security scanner (for HTTP endpoints)
- **Custom**: MCP-specific security tests

### 4.2 Static Security Analysis

```bash
# Bandit - scan for security issues
bandit -r src/ -f json -o bandit-report.json

# Safety - check dependencies for known vulnerabilities
safety check --json
```

#### Common Security Issues to Check

```python
# tests/security/test_static_analysis.py

def test_no_hardcoded_secrets():
    """Check for hardcoded secrets in codebase."""
    import re
    from pathlib import Path

    # Patterns for common secrets
    patterns = [
        r'password\s*=\s*["\'][^"\']+["\']',
        r'api_key\s*=\s*["\'][^"\']+["\']',
        r'secret\s*=\s*["\'][^"\']+["\']',
        r'token\s*=\s*["\'][^"\']+["\']',
    ]

    violations = []
    for py_file in Path("src").rglob("*.py"):
        content = py_file.read_text()
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                violations.append((py_file, match.group()))

    assert len(violations) == 0, f"Found hardcoded secrets: {violations}"

def test_secure_random_usage():
    """Ensure secure random is used for crypto/security."""
    import ast
    from pathlib import Path

    insecure_randoms = []

    for py_file in Path("src").rglob("*.py"):
        tree = ast.parse(py_file.read_text())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "random":  # Non-crypto random
                        insecure_randoms.append((py_file, node.lineno))

    # Allow random for non-security purposes, but flag for review
    if insecure_randoms:
        print(f"Warning: Found {len(insecure_randoms)} uses of non-crypto random")
```

### 4.3 Dynamic Security Testing

```python
# tests/security/test_dynamic_security.py

@pytest.mark.security
async def test_authentication_bypass_attempts(mcp_server):
    """Test for authentication bypass vulnerabilities."""
    # Try without auth token
    try:
        client = UnauthenticatedMCPClient()
        await client.call_tool("system.get_info", {})
        pytest.fail("Should require authentication")
    except AuthenticationError:
        pass  # Expected

    # Try with invalid token
    try:
        client = MCPClient(token="invalid_token_12345")
        await client.call_tool("system.get_info", {})
        pytest.fail("Should reject invalid token")
    except AuthenticationError:
        pass  # Expected

@pytest.mark.security
async def test_privilege_escalation_attempts(mcp_client_viewer):
    """Test for privilege escalation vulnerabilities."""
    # Viewer role tries to perform admin action
    try:
        await mcp_client_viewer.call_tool("manage.reboot", {})
        pytest.fail("Viewer should not be able to reboot")
    except PermissionError:
        pass  # Expected

@pytest.mark.security
async def test_rate_limit_enforcement(mcp_client):
    """Test that rate limits are enforced."""
    # Rapidly call rate-limited tool
    success_count = 0
    rate_limited_count = 0

    for _ in range(100):
        try:
            await mcp_client.call_tool("gpio.write_pin", {
                "pin": 17,
                "value": 1
            })
            success_count += 1
        except RateLimitError:
            rate_limited_count += 1

    assert rate_limited_count > 0, "Rate limiting not enforced"

@pytest.mark.security
async def test_audit_logging_completeness(mcp_client_admin, audit_log_path):
    """Verify all privileged operations are audited."""
    # Perform privileged operation
    await mcp_client_admin.call_tool("service.start", {
        "service_name": "nginx"
    })

    # Check audit log
    audit_entries = parse_audit_log(audit_log_path)
    assert any(
        entry["tool"] == "service.start" and
        entry["params"]["service_name"] == "nginx"
        for entry in audit_entries
    ), "Privileged operation not audited"
```

---

## 5. Regression Testing & CI Integration

### 5.1 Automated Regression Detection

```yaml
# .github/workflows/regression-tests.yml

name: Regression Tests

on: [push, pull_request]

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"

      - name: Run unit tests
        run: pytest tests/unit/ -v --cov --cov-report=xml

      - name: Run integration tests
        run: pytest tests/integration/ -v

      - name: Run benchmarks
        run: pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark.json

      - name: Compare benchmarks
        run: |
          pytest-benchmark compare main-benchmark.json benchmark.json --fail-if-slower=10%

      - name: Security scan
        run: |
          bandit -r src/ -f json -o bandit-report.json
          safety check --json

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

### 5.2 Hardware-in-the-Loop Testing

For actual Raspberry Pi hardware validation:

```yaml
# .github/workflows/hardware-tests.yml

name: Hardware Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Nightly at 2 AM
  workflow_dispatch:

jobs:
  test-on-hardware:
    runs-on: [self-hosted, raspberry-pi]
    strategy:
      matrix:
        device: [pi3, pi4, pi5, zero2w]
    steps:
      - uses: actions/checkout@v3

      - name: Run full test suite
        run: |
          pytest tests/ -v --device=${{ matrix.device }}

      - name: Run benchmarks
        run: |
          pytest tests/benchmarks/ --benchmark-only --device=${{ matrix.device }}

      - name: Store results
        run: |
          cp benchmark-results.json results/${{ matrix.device }}-benchmark.json
```

---

## 6. Implementation Checklist

### Phase 1 (Current)
- ✅ Unit tests for all modules (85%+ coverage)
- ✅ Integration tests for MCP tools
- ✅ Sandbox mode for safe testing
- ✅ Mock IPC for unit testing
- ⚠️ **ADD**: Basic performance benchmarks
- ⚠️ **ADD**: Hypothesis-based property testing for input validation

### Phase 2+ (Future)
- ⏭️ Comprehensive load testing with Locust
- ⏭️ Fuzz testing with Atheris
- ⏭️ Security testing suite (Bandit, Safety, OWASP ZAP)
- ⏭️ Hardware-in-the-loop CI pipeline
- ⏭️ Automated regression detection
- ⏭️ Performance monitoring and alerting
- ⏭️ Chaos engineering (random failures, network issues)
- ⏭️ Continuous benchmarking dashboard

---

**End of Document**
