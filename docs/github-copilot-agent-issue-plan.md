# GitHub Copilot Agent Issue Plan - Raspberry Pi MCP Server

## Document Purpose

This document provides a strategic breakdown of Phase 1 implementation into GitHub Issues optimized for GitHub Copilot Agent's **6-hour maximum runtime limit**. Each issue is designed to be a cohesive, completeable unit of work within a single 6-hour session.

**Target Audience**: GitHub Copilot Agent (AI developer) + Human project manager

---

## Strategy Overview

### Design Principles

1. **6-Hour Optimization**: Each issue targets 5-6 hours of work, leaving buffer for debugging and testing
2. **Dependency-Aware**: Issues are sequenced to respect dependencies (Core → Security → Tools)
3. **Self-Contained**: Each issue includes all context needed (design doc references, acceptance criteria)
4. **Test-Inclusive**: All issues include unit test requirements (TDD approach)
5. **Hardware-Separated**: Hardware-dependent features grouped to minimize context switching

### Effort Mapping to 6-Hour Sessions

From [phase-1-scope-matrix.md](phase-1-scope-matrix.md):
- **XS (1-3h)**: Bundle 2-3 XS features per issue
- **S (4-8h)**: 1 S feature per issue (ideal fit)
- **M (1-2 days)**: Split into 2 issues or pair with XS features
- **L (3-5 days)**: Split into 3-4 issues with clear milestones
- **XL (1-2 weeks)**: Split into 5-7 issues with incremental delivery

### Issue Sequencing

**Critical Path** (must be sequential):
1. Core Infrastructure (Issues #1-3) → ~3 sessions
2. Security Foundation (Issue #4) → ~1 session
3. Basic Tools (Issues #5-6) → ~2 sessions
4. Advanced Features (Issues #7-10) → ~4 sessions

**Parallel Opportunities**: After Issue #4, Issues #5-8 can be worked in any order.

---

## Quick Start Example

Here's how to create Issue #1 with GitHub Copilot Agent:

1. **Go to GitHub** → Your repository → Issues → New Issue

2. **Set Title**:
   ```
   [Phase 1] Project Foundation & Configuration System
   ```

3. **Paste Issue Description** (from Issue #1 below - the "📋 Issue Description" section)

4. **Add Labels**: `copilot-agent`, `phase-1`, `effort-6h`, `complexity-medium`

5. **Assign to GitHub Copilot Agent**:
   - Click "Assign" button
   - Select "GitHub Copilot Agent" from dropdown
   - In the **"Custom Prompt"** field, paste the entire "🤖 GitHub Copilot Agent Custom Prompt" section from Issue #1 below

6. **Submit** and monitor progress!

GitHub Copilot Agent will:
- Read the custom prompt
- Read all referenced design documents
- Implement the feature
- Run tests and linting
- Commit code with descriptive messages
- Post status updates to the issue

---

## GitHub Issue Structure

Each GitHub issue has three distinct parts:

### 1. **Title** (One Line)
Example: `[Phase 1] Project Foundation & Configuration System`

### 2. **Description** (Issue Body - For Human Review)
The main issue description contains:
- Scope and deliverables
- Acceptance criteria
- Design document references
- Human review checklist
- Implementation notes

This is what humans see when reviewing the issue and tracking progress.

### 3. **GitHub Copilot Agent Custom Prompt** (Separate Field)
When assigning the issue to GitHub Copilot Agent, you provide a custom prompt that:
- Gives context about the project
- Lists specific design documents to read
- Specifies implementation requirements
- Provides development process steps
- Defines success criteria

**Important**: The custom prompt is entered in a separate field when assigning to Copilot Agent, NOT in the issue description.

### How to Create an Issue with Copilot Agent

1. **Create GitHub Issue**:
   - Use the title from the issue specification below
   - Copy the "Issue Description" section as the issue body
   - Add labels: `copilot-agent`, `phase-1`, `effort-<hours>`, `complexity-<level>`
   - Link dependencies if applicable

2. **Assign to GitHub Copilot Agent**:
   - Click "Assign" → Select GitHub Copilot Agent
   - In the **"Custom Prompt"** field, paste the "Copilot Agent Custom Prompt" from the issue specification
   - Submit the assignment

3. **Monitor Progress**:
   - Copilot Agent will comment on the issue with status updates
   - Review commits and test results as they're posted
   - Provide feedback if needed

---

## GitHub Issues Breakdown

For each issue below, you'll find:
- **Title**: Use as the GitHub issue title
- **Issue Description**: Copy as the issue body (for humans)
- **Copilot Agent Custom Prompt**: Use when assigning to Copilot Agent (separate field)

### Issue #1: Project Foundation & Configuration System

#### 📌 Title
```
[Phase 1] Project Foundation & Configuration System
```

#### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 5-6 hours
**Complexity**: Medium
**Dependencies**: None
**Requires Hardware**: No

**Scope**: Initialize project structure, setup development tools, and implement the configuration management system.

**Deliverables**:
- [ ] Repository structure: `src/mcp_raspi/`, `src/mcp_raspi_ops/`, `tests/`
- [ ] `pyproject.toml` with `uv` packaging, all dependencies configured
- [ ] Pydantic models: `AppConfig`, `SecurityConfig`, `DeviceConfig`
- [ ] Configuration loading: YAML file + environment variables + CLI argument overrides
- [ ] Structured logging framework (JSON format)
- [ ] CI/CD pipeline: GitHub Actions for lint (ruff), test (pytest), coverage (≥85%)
- [ ] Unit tests for all config loading paths

**Acceptance Criteria**:
- ✅ `uv run pytest` passes all tests with ≥85% coverage
- ✅ `uv run ruff check` passes with zero errors
- ✅ Config loading precedence works: defaults < YAML < env vars < CLI args
- ✅ All Pydantic models validate correctly with invalid inputs
- ✅ Structured logging outputs valid JSON to stdout
- ✅ CI pipeline runs on push/PR and reports status

**Design Documents**:
- [Doc 02](02-raspberry-pi-mcp-server-high-level-architecture-design.md) §3: Configuration Management
- [Doc 13](13-python-development-standards-and-tools.md): Python standards
- [Doc 14](14-configuration-reference-and-examples.md): Complete config reference

**Implementation Notes**:
```python
# Expected core structure:
src/mcp_raspi/
  __init__.py
  config.py         # AppConfig, load_config()
  logging.py        # setup_logging()
  errors.py         # ToolError base class
tests/
  test_config.py
  test_logging.py
```

**Time Breakdown**:
- Project setup & dependencies: 1 hour
- Pydantic models & validation: 1.5 hours
- Config loading logic: 1.5 hours
- Logging framework: 1 hour
- CI/CD pipeline: 1 hour
- Testing & debugging: 1 hour

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] Documentation updated (if needed)

#### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing the Project Foundation & Configuration System for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #1 - the foundation that all other features depend on
- Design docs are in docs/ directory - read them thoroughly before coding
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: uv (package manager), pytest (testing), ruff (linting), Pydantic (models)
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/02-raspberry-pi-mcp-server-high-level-architecture-design.md §3 (Configuration Management)
- docs/13-python-development-standards-and-tools.md (Python standards)
- docs/14-configuration-reference-and-examples.md (Complete config reference)

DELIVERABLES:
1. Repository structure: src/mcp_raspi/, src/mcp_raspi_ops/, tests/
2. pyproject.toml with uv packaging, all dependencies
3. Pydantic models: AppConfig, SecurityConfig, DeviceConfig
4. Configuration loading: YAML + env vars + CLI args (layered precedence)
5. Structured logging framework (JSON format)
6. CI/CD pipeline: GitHub Actions for lint/test/coverage
7. Unit tests for all config loading paths

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/
  __init__.py
  config.py         # AppConfig, load_config()
  logging.py        # setup_logging()
  errors.py         # ToolError base class
tests/
  test_config.py
  test_logging.py
pyproject.toml      # uv packaging config
.github/
  workflows/
    ci.yml          # GitHub Actions
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- uv run pytest passes all tests with ≥85% coverage
- uv run ruff check passes with zero errors
- Config loading precedence works: defaults < YAML < env vars < CLI args
- All Pydantic models validate correctly with invalid inputs
- Structured logging outputs valid JSON to stdout
- CI pipeline runs on push/PR and reports status

DEVELOPMENT PROCESS:
1. Read all linked design documents in docs/ directory first
2. Write tests FIRST (TDD approach) - create test files before implementation
3. Implement features following design specifications exactly
4. Use Python 3.11+ type hints on ALL functions
5. Add docstrings for all public functions/classes
6. Follow docs/13-python-development-standards-and-tools.md for code style
7. Commit frequently with conventional commit messages (feat:, fix:, test:)
8. Run `uv run pytest --cov` after each commit - must pass ≥85% coverage
9. Run `uv run ruff check` before final commit - must have zero errors

CONFIGURATION LOADING PRECEDENCE (from design docs):
1. Hard-coded defaults in Pydantic models
2. YAML config file (config.yml)
3. Environment variables (MCP_RASPI_*)
4. CLI arguments (--config, --log-level, etc.)
Each layer overrides the previous.

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report: `uv run pytest --cov --cov-report=term`
- Highlight any deviations from design docs with rationale
- List all created files and their purposes
- Mark issue as ready for human review

IF STUCK OR TIME RUNNING OUT:
- Document current state and remaining work in issue comment
- Ask clarifying questions in comments
- Reference design docs for guidance
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria above must be met for this issue to be considered complete. This is the foundation - it must be solid before any other issues can proceed.
```

---

**Note on Issue Format**: Issue #1 above shows the complete 3-part structure (Title, Description, Custom Prompt). Issues #2-12 below follow a similar detailed format with all the same sections. Each issue can be created following the same process shown in the Quick Start Example above.

---

### Issue #2: MCP Server Core & JSON-RPC Protocol
**Effort**: 5-6 hours | **Complexity**: High | **Dependencies**: Issue #1

#### Scope
Implement the MCP server that communicates via JSON-RPC 2.0 over stdio, with request routing and error handling.

#### Deliverables
- [ ] JSON-RPC 2.0 request parser (validate `jsonrpc`, `id`, `method`, `params`)
- [ ] JSON-RPC 2.0 response formatter (success/error responses)
- [ ] Request routing framework: `@tool_handler("namespace.method")` decorator
- [ ] Tool registry: register handlers, dispatch requests
- [ ] `ToolContext` extraction from MCP protocol headers
- [ ] `ToolError` → JSON-RPC error code mapping (see Doc 05 §2)
- [ ] First dummy tool: `system.get_basic_info` (stub returning mock data)
- [ ] Comprehensive unit tests for protocol edge cases

#### Acceptance Criteria
- ✅ Server reads JSON-RPC requests from stdin, writes responses to stdout
- ✅ Valid requests route to correct handler and return success response
- ✅ Invalid requests return proper JSON-RPC error responses
- ✅ `ToolError` exceptions map to correct error codes (4001-4999 range)
- ✅ Malformed JSON handled gracefully with error response
- ✅ `system.get_basic_info` stub callable and returns expected structure
- ✅ All tests pass with ≥85% coverage

#### Design Documents
- [Doc 02](02-raspberry-pi-mcp-server-high-level-architecture-design.md) §5: MCP Server Process
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §1-2: Protocol & Error Codes

#### Implementation Notes
```python
# Core components:
src/mcp_raspi/
  server.py          # MCPServer class, main loop
  protocol.py        # parse_request(), format_response()
  routing.py         # ToolRegistry, @tool_handler
  context.py         # ToolContext dataclass
  tools/
    __init__.py
    system.py        # system.get_basic_info stub
```

#### JSON-RPC Example
```json
// Request
{"jsonrpc": "2.0", "id": "1", "method": "system.get_basic_info", "params": {}}

// Success Response
{"jsonrpc": "2.0", "id": "1", "result": {"hostname": "raspberrypi", ...}}

// Error Response
{"jsonrpc": "2.0", "id": "1", "error": {"code": 4003, "message": "Tool not found"}}
```

#### Time Breakdown
- JSON-RPC parser/formatter: 1.5 hours
- Routing framework: 1.5 hours
- Error handling & mapping: 1 hour
- Tool context extraction: 1 hour
- Stub tool implementation: 0.5 hours
- Testing & debugging: 1.5 hours

---

### Issue #3: Privileged Agent & IPC Communication
**Effort**: 5-6 hours | **Complexity**: Medium-High | **Dependencies**: Issue #2

#### Scope
Implement the privileged agent process and Unix domain socket IPC between MCP server and agent.

#### Deliverables
- [ ] Privileged agent process: `mcp_raspi_ops` (runs as root/privileged user)
- [ ] Unix domain socket IPC server in agent (listens on `/var/run/mcp-raspi-ops.sock`)
- [ ] IPC protocol: JSON request/response over socket
- [ ] IPC client in MCP server: `OpsAgentClient` class
- [ ] Request forwarding: MCP server → agent for privileged operations
- [ ] Error propagation: agent errors → MCP server → JSON-RPC errors
- [ ] Connection handling: reconnect on disconnect, timeout handling
- [ ] Test IPC command: `ping` command that agent echoes back
- [ ] Unit tests for IPC protocol, integration tests for full flow

#### Acceptance Criteria
- ✅ Agent starts and listens on Unix socket
- ✅ MCP server connects to agent socket on startup
- ✅ Test `ping` command works end-to-end (server → agent → server)
- ✅ Agent errors propagate correctly to MCP server
- ✅ Connection failure handled gracefully (retry logic)
- ✅ Timeout handling prevents hung requests
- ✅ Integration tests validate full MCP → IPC → agent flow
- ✅ All tests pass with ≥85% coverage

#### Design Documents
- [Doc 02](02-raspberry-pi-mcp-server-high-level-architecture-design.md) §6: Privileged Agent, §7: IPC Protocol
- [Doc 02](02-raspberry-pi-mcp-server-high-level-architecture-design.md) §12: IPC Robustness

#### Implementation Notes
```python
# Agent structure:
src/mcp_raspi_ops/
  __init__.py
  agent.py           # Main agent process, socket server
  handlers.py        # Command handlers (ping, etc.)
  ipc_protocol.py    # JSON over socket protocol

# Server IPC client:
src/mcp_raspi/
  ipc_client.py      # OpsAgentClient class
```

#### IPC Protocol Example
```json
// Request from server to agent
{"request_id": "uuid-1234", "command": "ping", "params": {}}

// Response from agent to server
{"request_id": "uuid-1234", "status": "success", "result": "pong"}

// Error response
{"request_id": "uuid-1234", "status": "error", "error_code": 5001, "message": "..."}
```

#### Time Breakdown
- Agent socket server: 1.5 hours
- IPC client implementation: 1.5 hours
- Connection handling & retries: 1 hour
- Error propagation: 1 hour
- Integration testing: 1.5 hours
- Debugging & edge cases: 0.5 hours

---

### Issue #4: Security Foundation - OAuth, RBAC & Audit Logging
**Effort**: 6 hours | **Complexity**: High | **Dependencies**: Issue #3

#### Scope
Implement Cloudflare Access JWT validation, role-based access control, and audit logging.

#### Deliverables
- [ ] JWT validation: extract from MCP headers, verify signature via JWKS
- [ ] JWKS fetching: download and cache Cloudflare's public keys
- [ ] RBAC roles: `viewer`, `operator`, `admin` (see Doc 04 §5)
- [ ] `ToolContext` population: user ID, email, roles from JWT claims
- [ ] Policy enforcement: check role requirements before tool execution
- [ ] Audit logging: structured logs for all privileged operations
- [ ] Local auth mode: static token or permissive mode for LAN/dev
- [ ] Configuration: `auth_mode: cloudflare|local`, JWKS URL, allowed roles
- [ ] Unit tests for JWT validation, RBAC checks, audit log format

#### Acceptance Criteria
- ✅ Valid Cloudflare JWT authenticates user and extracts roles
- ✅ Invalid/expired JWT rejected with proper error
- ✅ Tools enforce role requirements (e.g., `admin` only for reboot)
- ✅ Audit logs contain: timestamp, user, action, result, parameters
- ✅ Local auth mode bypasses JWT validation (for dev/testing)
- ✅ JWKS keys cached and refreshed on expiry
- ✅ All tests pass with mocked JWT/JWKS endpoints
- ✅ Test coverage ≥85% on security module

#### Design Documents
- [Doc 04](04-security-oauth-integration-and-access-control-design.md): Complete security design
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §1.3: ToolContext
- [Doc 09](09-logging-observability-and-diagnostics-design.md) §4: Audit Logging

#### Implementation Notes
```python
# Security module:
src/mcp_raspi/
  security/
    __init__.py
    jwt_validator.py      # JWTValidator class
    jwks_fetcher.py       # fetch & cache JWKS
    rbac.py               # @require_role decorator
    audit_logger.py       # AuditLogger class
```

#### Role Permissions (from Doc 04)
- **viewer**: Read-only (system info, metrics query, logs read)
- **operator**: Read + device control (GPIO, I2C, service start/stop)
- **admin**: Full access (reboot, shutdown, updates, config changes)

#### Time Breakdown
- JWT validation & JWKS: 2 hours
- RBAC implementation: 1.5 hours
- Audit logging: 1 hour
- Local auth mode: 0.5 hours
- Configuration integration: 0.5 hours
- Testing (mocked endpoints): 1.5 hours

---

### Issue #5: System Information & Power Management Tools
**Effort**: 5-6 hours | **Complexity**: Medium | **Dependencies**: Issue #4

#### Scope
Implement system information retrieval and power management tools (reboot/shutdown).

#### Deliverables
- [ ] `system.get_basic_info`: hostname, model, OS, kernel, uptime (Doc 06 §3.1)
- [ ] `system.get_health_snapshot`: CPU, memory, disk, temp, network (Doc 06 §3.2)
- [ ] Temperature reading: `/sys/class/thermal/thermal_zone*/temp`
- [ ] `system.get_network_info`: IP addresses, interfaces, MAC addresses
- [ ] `system.reboot`: with safety checks, audit logging, RBAC (admin only)
- [ ] `system.shutdown`: with safety checks, audit logging, RBAC (admin only)
- [ ] Sandbox mode handling: full=mock, partial=log-only, disabled=execute
- [ ] Agent implementation: actual reboot/shutdown via `subprocess`
- [ ] Unit tests for all tools, integration tests for agent operations

#### Acceptance Criteria
- ✅ `system.get_basic_info` returns accurate system information
- ✅ `system.get_health_snapshot` returns CPU/memory/disk/temp metrics
- ✅ Temperature reading handles multiple thermal zones
- ✅ `system.reboot` requires admin role, logs to audit log
- ✅ `system.shutdown` requires admin role, logs to audit log
- ✅ Sandbox modes work: full=mocked, partial=logged, disabled=executed
- ✅ Reboot/shutdown actually execute when sandbox=disabled (test on dev device!)
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

#### Design Documents
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §3: system.* namespace
- [Doc 06](06-system-information-and-metrics-module-design.md) §3: System info tools
- [Doc 08](08-device-control-and-reboot-shutdown-safeguards-design.md) §3: Reboot/shutdown

#### Implementation Notes
```python
# System tools:
src/mcp_raspi/tools/
  system.py          # All system.* tools
src/mcp_raspi_ops/handlers/
  system.py          # Agent handlers for reboot/shutdown
```

#### Time Breakdown
- Basic info tool: 1 hour
- Health snapshot tool: 1.5 hours
- Network info tool: 0.5 hours
- Reboot/shutdown tools: 1.5 hours
- Sandbox mode integration: 0.5 hours
- Agent handlers: 1 hour
- Testing: 1 hour

---

### Issue #6: GPIO & I2C Device Control
**Effort**: 5-6 hours | **Complexity**: Medium | **Dependencies**: Issue #4 | **Requires Hardware**: Yes

#### Scope
Implement GPIO and I2C device control tools with safety guardrails (whitelists).

#### Deliverables
- [ ] `gpio.read_pin`: read digital state (BCM pin numbering)
- [ ] `gpio.write_pin`: write digital state with whitelist enforcement
- [ ] `gpio.configure_pin`: set mode (in/out), pull-up/down
- [ ] `gpio.set_pwm`: basic PWM output (fixed frequency initially)
- [ ] `gpio.get_all_states`: bulk read all configured pins
- [ ] `i2c.scan_bus`: detect devices on I2C bus
- [ ] `i2c.read`: read bytes from I2C device with address whitelist
- [ ] `i2c.write`: write bytes to I2C device with address whitelist
- [ ] Configuration: GPIO pin whitelist, I2C address whitelist/blacklist
- [ ] Agent implementation: use `gpiozero` for GPIO, `smbus2` for I2C
- [ ] Unit tests (mocked), hardware validation tests (optional, documented)

#### Acceptance Criteria
- ✅ GPIO tools work on test hardware (LED blink test recommended)
- ✅ I2C tools detect devices on bus (scan_bus returns addresses)
- ✅ Pin/address whitelists enforced (reject non-whitelisted operations)
- ✅ PWM generates correct frequency (measure with oscilloscope/LED if available)
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Sandbox mode supported (full=mocked, disabled=real hardware)
- ✅ Operator role required for GPIO/I2C write operations
- ✅ Test coverage ≥85% (unit tests with mocks)

#### Design Documents
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §7: gpio.*, i2c.* namespaces
- [Doc 08](08-device-control-and-reboot-shutdown-safeguards-design.md) §4-5: GPIO & I2C

#### Implementation Notes
```python
# Device tools:
src/mcp_raspi/tools/
  gpio.py            # All gpio.* tools
  i2c.py             # All i2c.* tools
src/mcp_raspi_ops/handlers/
  gpio.py            # Agent GPIO handlers (gpiozero)
  i2c.py             # Agent I2C handlers (smbus2)
```

#### Hardware Testing Notes
- **GPIO**: Connect LED to GPIO 17 (BCM numbering) + resistor, test write_pin
- **I2C**: Connect any I2C sensor (e.g., BME280), test scan_bus and read
- **Safety**: Test whitelist rejection (try non-whitelisted pin/address)

#### Time Breakdown
- GPIO implementation: 2 hours
- I2C implementation: 2 hours
- Whitelist logic: 0.5 hours
- Agent hardware integration: 1 hour
- Testing (unit + hardware): 1.5 hours

---

### Issue #7: Service & Process Management Tools
**Effort**: 5-6 hours | **Complexity**: Medium | **Dependencies**: Issue #4

#### Scope
Implement systemd service management and process monitoring tools.

#### Deliverables
- [ ] `service.list_services`: query systemd, filter by whitelist
- [ ] `service.get_status`: get status of single service
- [ ] `service.control_service`: start/stop/restart with whitelist
- [ ] `service.set_enabled`: enable/disable autostart
- [ ] Service whitelist enforcement: configurable list of manageable services
- [ ] `process.list_processes`: list processes with filtering (name, user, CPU%)
- [ ] `process.get_info`: detailed info for single PID
- [ ] Pagination support: offset/limit for large result sets
- [ ] Agent implementation: systemd via D-Bus, processes via `psutil`
- [ ] Unit tests, integration tests with real systemd (safe test service)

#### Acceptance Criteria
- ✅ `service.list_services` returns only whitelisted services
- ✅ `service.control_service` starts/stops/restarts services successfully
- ✅ Service whitelist prevents control of non-whitelisted services
- ✅ `process.list_processes` returns accurate process list
- ✅ Filtering works (by name, user, CPU%, etc.)
- ✅ Pagination works correctly (offset/limit parameters)
- ✅ Operator role required for service control
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

#### Design Documents
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §5-6: service.*, process.*
- [Doc 07](07-service-and-process-management-module-design.md): Complete design

#### Implementation Notes
```python
# Service/process tools:
src/mcp_raspi/tools/
  service.py         # All service.* tools
  process.py         # All process.* tools
src/mcp_raspi_ops/handlers/
  service.py         # Agent systemd handlers (D-Bus)
  process.py         # Agent process handlers (psutil)
```

#### Safe Testing
Create a test systemd service for testing:
```ini
[Unit]
Description=MCP Test Service
[Service]
ExecStart=/bin/sleep 3600
[Install]
WantedBy=multi-user.target
```

#### Time Breakdown
- Service management tools: 2 hours
- Process management tools: 1.5 hours
- Whitelist enforcement: 0.5 hours
- Pagination logic: 0.5 hours
- Agent systemd/psutil integration: 1 hour
- Testing: 1.5 hours

---

### Issue #8: Metrics Sampling & Query System
**Effort**: 5-6 hours | **Complexity**: Medium | **Dependencies**: Issue #4

#### Scope
Implement background metrics sampling with SQLite storage and time-series queries.

#### Deliverables
- [ ] SQLite schema design: metrics table with timestamp, metric type, value
- [ ] `metrics.start_sampling`: start background sampling job (asyncio)
- [ ] `metrics.stop_sampling`: stop background job gracefully
- [ ] `metrics.get_status`: return sampling state (active, interval, metrics)
- [ ] `metrics.query`: time range queries with basic aggregation (min/max/avg)
- [ ] Background job: sample CPU, memory, disk, temp every N seconds
- [ ] Retention policy: delete metrics older than configured days
- [ ] Configuration: sampling interval, retention days, metrics to collect
- [ ] Unit tests, integration tests with real SQLite DB

#### Acceptance Criteria
- ✅ `metrics.start_sampling` starts background job
- ✅ Metrics written to SQLite database at configured interval
- ✅ `metrics.query` returns correct data for time ranges
- ✅ Aggregation functions work (min/max/avg)
- ✅ Retention policy deletes old data correctly
- ✅ Sampling can be stopped and restarted
- ✅ Database handles concurrent access (sampling + queries)
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

#### Design Documents
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §4: metrics.* namespace
- [Doc 06](06-system-information-and-metrics-module-design.md) §4: Metrics module
- [Doc 09](09-logging-observability-and-diagnostics-design.md) §3: Metrics storage

#### Implementation Notes
```python
# Metrics module:
src/mcp_raspi/
  metrics/
    __init__.py
    sampler.py         # Background sampling job
    storage.py         # SQLite storage layer
    query.py           # Query logic with aggregation
  tools/
    metrics.py         # All metrics.* tools
```

#### SQLite Schema
```sql
CREATE TABLE metrics (
  id INTEGER PRIMARY KEY,
  timestamp REAL,          -- Unix timestamp
  metric_type TEXT,        -- 'cpu_percent', 'memory_percent', etc.
  value REAL,
  metadata TEXT            -- JSON metadata
);
CREATE INDEX idx_timestamp ON metrics(timestamp);
CREATE INDEX idx_type_timestamp ON metrics(metric_type, timestamp);
```

#### Time Breakdown
- SQLite schema & storage: 1.5 hours
- Background sampling job: 2 hours
- Query & aggregation logic: 1.5 hours
- Retention policy: 0.5 hours
- Testing: 1.5 hours

---

### Issue #9: Logging Tools & Camera Support
**Effort**: 5-6 hours | **Complexity**: Medium | **Dependencies**: Issue #4 | **Requires Hardware**: Camera (optional)

#### Scope
Implement log query tools and basic camera capture functionality.

#### Deliverables
- [ ] `logs.get_recent_app_logs`: query application logs with filters
- [ ] `logs.get_recent_audit_logs`: query audit logs with filters
- [ ] Time range filtering: start/end timestamps
- [ ] Level filtering: filter by log level (DEBUG, INFO, WARNING, ERROR)
- [ ] Pagination: offset/limit for large log sets
- [ ] Log rotation: file-based or journald integration
- [ ] Sensitive data masking: redact secrets in logs
- [ ] `camera.get_info`: detect camera, return capabilities
- [ ] `camera.take_photo`: capture JPEG with basic resolution/quality params
- [ ] Rate limiting: max photos per minute (configurable)
- [ ] Agent implementation: log reading, camera via `picamera2`
- [ ] Unit tests, hardware tests (camera optional, documented)

#### Acceptance Criteria
- ✅ Log query tools return correct logs with filters applied
- ✅ Time range and level filtering work correctly
- ✅ Pagination works (offset/limit)
- ✅ Sensitive data masked (e.g., API keys, tokens)
- ✅ `camera.get_info` detects camera or returns "not detected"
- ✅ `camera.take_photo` captures photo (if camera present)
- ✅ Photos saved to configured media directory
- ✅ Rate limiting enforced (reject if limit exceeded)
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

#### Design Documents
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §9-10: logs.*, camera.*
- [Doc 08](08-device-control-and-reboot-shutdown-safeguards-design.md) §6: Camera
- [Doc 09](09-logging-observability-and-diagnostics-design.md) §5: Log query

#### Implementation Notes
```python
# Logging & camera tools:
src/mcp_raspi/tools/
  logs.py            # All logs.* tools
  camera.py          # All camera.* tools
src/mcp_raspi_ops/handlers/
  logs.py            # Agent log reading
  camera.py          # Agent camera capture (picamera2)
```

#### Camera Testing
- If no camera: `camera.get_info` returns `{"detected": false}`
- If camera present: Capture test photo, verify JPEG file created

#### Time Breakdown
- Log query tools: 2 hours
- Sensitive data masking: 0.5 hours
- Camera info tool: 0.5 hours
- Camera capture tool: 1.5 hours
- Rate limiting: 0.5 hours
- Testing: 1.5 hours

---

### Issue #10: Self-Update Mechanism - Part 1 (Foundation)
**Effort**: 6 hours | **Complexity**: High | **Dependencies**: Issue #4

#### Scope
Implement foundation for self-update: version management, directory structure, and basic update backend.

#### Deliverables
- [ ] `version.json` structure: current, previous, history
- [ ] Version directory layout: `/opt/mcp-raspi/releases/v1.0.0/`, `current` symlink
- [ ] `manage.get_server_status`: return version, uptime, last_update timestamp
- [ ] `UpdateBackend` abstraction: interface for different update sources
- [ ] `PythonPackageBackend`: download new version via `uv`/`pip`
- [ ] Version validation: semantic versioning checks
- [ ] Atomic directory operations: safe symlink switching
- [ ] Configuration: update source, version directory, rollback settings
- [ ] Unit tests for version management, backend abstraction

#### Acceptance Criteria
- ✅ Version directory structure created correctly
- ✅ `version.json` tracks current/previous versions
- ✅ `manage.get_server_status` returns accurate version info
- ✅ `PythonPackageBackend` can fetch package info (mock in tests)
- ✅ Symlink operations are atomic (no race conditions)
- ✅ Version validation rejects invalid version strings
- ✅ Configuration fully integrated
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

#### Design Documents
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §8: manage.* namespace
- [Doc 10](10-self-update-mechanism-and-rollback-strategy-design.md) §3-4: Version & backends

#### Implementation Notes
```python
# Self-update module (Part 1):
src/mcp_raspi/
  updates/
    __init__.py
    version.py           # Version management, version.json
    backends.py          # UpdateBackend abstraction
    python_backend.py    # PythonPackageBackend
    operations.py        # Atomic directory operations
  tools/
    manage.py            # manage.* tools
```

#### Version Directory Structure
```
/opt/mcp-raspi/
  releases/
    v1.0.0/            # First release
    v1.0.1/            # New release
  current -> v1.0.0    # Symlink to active version
  version.json         # Version tracking
```

#### Time Breakdown
- Version management: 1.5 hours
- Directory structure & operations: 1 hour
- UpdateBackend abstraction: 1 hour
- PythonPackageBackend: 1.5 hours
- manage.get_server_status tool: 0.5 hours
- Testing: 1.5 hours

---

### Issue #11: Self-Update Mechanism - Part 2 (State Machine)
**Effort**: 6 hours | **Complexity**: Very High | **Dependencies**: Issue #10

#### Scope
Implement the complete self-update state machine with rollback capability.

#### Deliverables
- [ ] Update state machine: idle → checking → preparing → switching → verifying → success/failed
- [ ] `manage.update_server`: implement full state machine
- [ ] Update process: download → validate → switch symlink → restart service → verify
- [ ] Systemd service restart integration: graceful restart after update
- [ ] Automatic rollback: trigger on repeated failures (health checks)
- [ ] Manual rollback: CLI tool to rollback to previous version
- [ ] Health check system: verify service working after update
- [ ] State persistence: track update state across restarts
- [ ] Comprehensive state machine tests (all transitions, error cases)

#### Acceptance Criteria
- ✅ `manage.update_server` completes full update cycle
- ✅ Service restarts automatically after update
- ✅ Health checks detect broken updates
- ✅ Automatic rollback triggers on repeated failures
- ✅ Manual rollback CLI tool works
- ✅ State machine handles all error cases gracefully
- ✅ `version.json` updated correctly throughout process
- ✅ Symlink switching is atomic (no downtime)
- ✅ Admin role required for update operations
- ✅ Test coverage ≥85% (including error paths)

#### Design Documents
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §8: manage.update_server
- [Doc 10](10-self-update-mechanism-and-rollback-strategy-design.md) §5-8: State machine & rollback

#### Implementation Notes
```python
# Self-update module (Part 2):
src/mcp_raspi/updates/
  state_machine.py     # UpdateStateMachine class
  rollback.py          # Rollback logic
  health_check.py      # Post-update health checks
  systemd_restart.py   # Service restart integration
```

#### State Machine Diagram
```
idle → checking → preparing → switching → verifying
                      ↓            ↓         ↓
                   failed ←─────────┴────────┘
                      ↓
                  rollback
```

#### Critical Testing
- **Test on real device**: Update from v1.0.0 to v1.0.1 (test versions)
- **Test rollback**: Simulate failure, verify automatic rollback
- **Test service restart**: Ensure no downtime during update

#### Time Breakdown
- State machine core: 2 hours
- Update process integration: 1.5 hours
- Rollback logic: 1 hour
- Health checks: 0.5 hours
- Systemd restart: 0.5 hours
- Testing (including E2E): 2 hours

---

### Issue #12: Deployment & Final Integration
**Effort**: 5-6 hours | **Complexity**: Medium | **Dependencies**: All previous issues

#### Scope
Create deployment artifacts, systemd integration, and operations documentation.

#### Deliverables
- [ ] Systemd unit files: `mcp-raspi-server.service`, `raspi-ops-agent.service`
- [ ] Installation script: `install.sh` for automated setup
- [ ] Configuration templates: `config.example.yml` with all options documented
- [ ] Cloudflare Tunnel setup guide
- [ ] Operations runbook: troubleshooting, common issues, recovery procedures
- [ ] Acceptance checklist: validate all Phase 1 requirements (see `docs/acceptance-checklist.md`)
- [ ] CI/CD integration: ensure all tests pass in pipeline
- [ ] Final E2E tests on clean Raspberry Pi OS install

#### Acceptance Criteria
- ✅ Systemd services start/stop/restart correctly
- ✅ Services restart on boot automatically
- ✅ Installation script works on clean Raspberry Pi OS
- ✅ Cloudflare Tunnel setup documented and tested
- ✅ Operations runbook covers all troubleshooting scenarios
- ✅ Acceptance checklist passes on Pi 3, Pi 4, Pi 5 (if available)
- ✅ All CI/CD tests passing
- ✅ Test coverage ≥85% overall project
- ✅ No high/critical security vulnerabilities
- ✅ README updated with getting started guide

#### Design Documents
- [Doc 12](12-deployment-systemd-integration-and-operations-runbook.md): Complete deployment guide
- [acceptance-checklist.md](acceptance-checklist.md): Phase 1 release criteria

#### Implementation Notes
```
# Deployment artifacts:
deployment/
  systemd/
    mcp-raspi-server.service
    raspi-ops-agent.service
  install.sh
  config.example.yml
docs/
  cloudflare-tunnel-setup.md
  operations-runbook.md
  troubleshooting.md
```

#### Systemd Service Example
```ini
[Unit]
Description=Raspberry Pi MCP Server
After=network.target raspi-ops-agent.service
Requires=raspi-ops-agent.service

[Service]
Type=simple
User=mcp-raspi
ExecStart=/opt/mcp-raspi/current/bin/mcp-raspi-server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Time Breakdown
- Systemd unit files: 1 hour
- Installation script: 1.5 hours
- Configuration templates: 0.5 hours
- Operations runbook: 1.5 hours
- Acceptance testing: 2 hours
- Documentation updates: 1 hour

---

## Implementation Timeline

### Sequential Timeline (One Issue at a Time)
Assuming 6 hours per issue + 2 hours overhead per issue (reviews, breaks):

| Week | Issue(s) | Focus Area | Total Hours |
|------|----------|------------|-------------|
| **Week 1** | #1, #2 | Foundation & MCP Server | 16h |
| **Week 2** | #3, #4 | IPC & Security | 16h |
| **Week 3** | #5, #6 | System Tools & GPIO/I2C | 16h |
| **Week 4** | #7, #8 | Services & Metrics | 16h |
| **Week 5** | #9, #10 | Logging/Camera & Update Pt1 | 16h |
| **Week 6** | #11, #12 | Update Pt2 & Deployment | 16h |

**Total**: ~6 weeks, ~96 hours of Copilot Agent time (16 x 6-hour sessions)

### Parallel Timeline (Where Possible)
After Issue #4 completes, Issues #5-9 can be worked in any order:

| Week | Issue(s) | Parallelization | Total Hours |
|------|----------|-----------------|-------------|
| **Week 1-2** | #1, #2, #3, #4 | Sequential (critical path) | 32h |
| **Week 3-4** | #5, #6, #7, #8, #9 | Parallel (can work any order) | 40h |
| **Week 5-6** | #10, #11, #12 | Sequential (dependencies) | 24h |

**Total**: ~6 weeks, but more flexible sequencing

---

## Using This Plan with GitHub Copilot Agent

### Issue Creation Workflow

1. **Create GitHub Issues**: Copy each issue section (1-12) into a GitHub issue
2. **Add Labels**: `copilot-agent`, `phase-1`, `effort:<hours>`, `complexity:<level>`
3. **Set Dependencies**: Link dependent issues ("depends on #N")
4. **Assign to Copilot**: Use `@copilot` or GitHub Copilot Agent workflow trigger
5. **Monitor Progress**: Copilot Agent will update issue with status/comments

### Copilot Agent Instructions

Include this in each issue description:

```markdown
## Instructions for GitHub Copilot Agent

**Estimated Time**: 5-6 hours
**Design Documents**: [See "Design Documents" section above]
**Dependencies**: [See "Dependencies" section above]

### Before Starting
1. Read linked design documents thoroughly
2. Understand acceptance criteria
3. Review dependencies (wait for prerequisite issues to complete)

### Development Process
1. **TDD Approach**: Write tests first, then implementation
2. **Follow Standards**: Use Python type hints, docstrings, follow Doc 13
3. **Incremental Commits**: Commit frequently with clear messages
4. **Run Tests**: `uv run pytest --cov` must pass with ≥85% coverage
5. **Lint Check**: `uv run ruff check` must pass with zero errors

### When Complete
1. Update this issue with summary of implementation
2. Post test coverage report
3. Highlight any deviations from design docs (with rationale)
4. Mark issue as complete
```

### Monitoring Copilot Agent

**Expected outputs from Copilot Agent**:
- Commits to feature branch (e.g., `copilot/issue-5-system-tools`)
- Test results posted to issue comments
- Coverage reports
- Status updates ("completed X, working on Y")
- Questions/clarifications (if design ambiguous)

**Human review triggers**:
- After each issue completes (code review)
- If Copilot Agent gets stuck (timeout > 30 minutes)
- For hardware testing (Issues #6, #9)
- Before deployment (Issue #12)

---

## Risk Mitigation

### High-Risk Issues

| Issue | Risk | Mitigation |
|-------|------|------------|
| **#3** | IPC complexity | Extra testing, consider simpler protocol if needed |
| **#4** | Security bugs | Security-focused code review, penetration testing |
| **#6** | Hardware dependencies | Use mocks extensively, hardware tests optional |
| **#11** | Update/rollback failure | Extensive E2E testing, manual validation required |

### Fallback Plans

**If 6-hour limit exceeded**:
- Split issue into smaller parts (Part 1, Part 2)
- Defer non-critical acceptance criteria to later issue
- Simplify implementation (mark as "basic implementation")

**If dependencies block progress**:
- Work on independent issues (#5-9 can be done in any order after #4)
- Create mock implementations of dependencies for testing

**If hardware unavailable**:
- Use GPIO/I2C/Camera mocks (already in plan)
- Document hardware validation steps for manual testing
- Mark as "tested with mocks, needs hardware validation"

---

## Success Metrics

### Per-Issue Metrics
- ✅ All acceptance criteria met
- ✅ Test coverage ≥85%
- ✅ Zero linting errors
- ✅ All CI/CD checks passing
- ✅ Code review approved by human

### Overall Phase 1 Metrics (Issue #12)
- ✅ All 12 issues completed
- ✅ Acceptance checklist passes
- ✅ Self-update tested on real hardware
- ✅ Deployment successful on clean Pi OS
- ✅ Security review complete (no high/critical vulnerabilities)
- ✅ Operations runbook validated

---

## References

### Design Documents
- [phase-1-scope-matrix.md](phase-1-scope-matrix.md): Complete feature matrix
- [acceptance-checklist.md](acceptance-checklist.md): Release criteria
- [test-matrix.md](test-matrix.md): Testing requirements
- Doc 01-14: Complete design specifications

### Tools & Standards
- **Python**: 3.11+, type hints, docstrings
- **Packaging**: `uv` for dependency management
- **Linting**: `ruff` for code quality
- **Testing**: `pytest` with `pytest-cov` for coverage
- **CI/CD**: GitHub Actions for automation

---

**Document Version**: 1.0
**Last Updated**: 2025-12-04
**Optimized For**: GitHub Copilot Agent (6-hour sessions)
**Total Estimated Time**: 96 hours (16 x 6-hour sessions)
**Expected Duration**: 6 weeks (2 issues per week)
