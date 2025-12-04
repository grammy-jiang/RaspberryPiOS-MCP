# GitHub Copilot Agent Issues #5-12 - Complete Specifications

This document contains the **complete 3-part specifications** (Title, Description, Custom Prompt) for GitHub Issues #5-12.

**For Issues #1-4**: See [github-copilot-agent-issue-plan.md](github-copilot-agent-issue-plan.md)

---

## Issue #5: System Information & Power Management Tools

### 📌 Title
```
[Phase 1] System Information & Power Management Tools
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 5-6 hours
**Complexity**: Medium
**Dependencies**: Issue #4
**Requires Hardware**: No

**Scope**: Implement system information retrieval and power management tools (reboot/shutdown).

**Deliverables**:
- [ ] `system.get_basic_info`: hostname, model, OS, kernel, uptime
- [ ] `system.get_health_snapshot`: CPU, memory, disk, temp, network
- [ ] Temperature reading: `/sys/class/thermal/thermal_zone*/temp`
- [ ] `system.get_network_info`: IP addresses, interfaces, MAC addresses
- [ ] `system.reboot`: with safety checks, audit logging, RBAC (admin only)
- [ ] `system.shutdown`: with safety checks, audit logging, RBAC (admin only)
- [ ] Sandbox mode handling: full=mock, partial=log-only, disabled=execute
- [ ] Agent implementation: actual reboot/shutdown via `subprocess`
- [ ] Unit tests for all tools, integration tests for agent operations

**Acceptance Criteria**:
- ✅ `system.get_basic_info` returns accurate system information
- ✅ `system.get_health_snapshot` returns CPU/memory/disk/temp metrics
- ✅ Temperature reading handles multiple thermal zones
- ✅ `system.reboot` requires admin role, logs to audit log
- ✅ `system.shutdown` requires admin role, logs to audit log
- ✅ Sandbox modes work: full=mocked, partial=logged, disabled=executed
- ✅ Reboot/shutdown actually execute when sandbox=disabled (test on dev device!)
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

**Design Documents**:
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §3: system.* namespace
- [Doc 06](06-system-information-and-metrics-module-design.md) §3: System info tools
- [Doc 08](08-device-control-and-reboot-shutdown-safeguards-design.md) §3: Reboot/shutdown

**Implementation Notes**:
```python
src/mcp_raspi/tools/
  system.py          # All system.* tools
src/mcp_raspi_ops/handlers/
  system.py          # Agent handlers for reboot/shutdown
```

**Time Breakdown**:
- Basic info tool: 1 hour
- Health snapshot tool: 1.5 hours
- Network info tool: 0.5 hours
- Reboot/shutdown tools: 1.5 hours
- Sandbox mode integration: 0.5 hours
- Agent handlers: 1 hour
- Testing: 1 hour

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] Hardware-specific code has sandbox mode handling

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing System Information & Power Management Tools for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #5 - implementing system monitoring and power management tools
- Depends on: Issue #4 (Security foundation) must be complete
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: psutil for system info, subprocess for reboot/shutdown
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/05-mcp-tools-interface-and-json-schema-specification.md §3 (system.* namespace)
- docs/06-system-information-and-metrics-module-design.md §3 (System info tools)
- docs/08-device-control-and-reboot-shutdown-safeguards-design.md §3 (Reboot/shutdown)

DELIVERABLES:
1. system.get_basic_info: hostname, model, OS, kernel, uptime
2. system.get_health_snapshot: CPU, memory, disk, temp, network
3. Temperature reading from /sys/class/thermal/thermal_zone*/temp
4. system.get_network_info: IP addresses, interfaces, MAC addresses
5. system.reboot: with safety checks, audit logging, RBAC (admin only)
6. system.shutdown: with safety checks, audit logging, RBAC (admin only)
7. Sandbox mode handling: full=mock, partial=log-only, disabled=execute
8. Agent implementation: actual reboot/shutdown via subprocess
9. Unit tests for all tools, integration tests for agent operations

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/tools/
  system.py          # All system.* tools
src/mcp_raspi_ops/handlers/
  system.py          # Agent handlers for reboot/shutdown
tests/
  test_tools_system.py
  test_handlers_system.py
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- system.get_basic_info returns accurate system information
- system.get_health_snapshot returns CPU/memory/disk/temp metrics
- Temperature reading handles multiple thermal zones
- system.reboot requires admin role, logs to audit log
- system.shutdown requires admin role, logs to audit log
- Sandbox modes work: full=mocked, partial=logged, disabled=executed
- Reboot/shutdown actually execute when sandbox=disabled (test carefully!)
- All JSON schemas match Doc 05 specifications exactly
- Test coverage ≥85%

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Implement system.get_basic_info using platform module + psutil
3. Implement system.get_health_snapshot using psutil for metrics
4. Read temperature from /sys/class/thermal (handle multiple zones)
5. Implement system.get_network_info using psutil.net_if_addrs()
6. Implement reboot/shutdown tools with @require_role("admin") decorator
7. Add sandbox mode checks (from config)
8. Implement agent handlers for actual reboot/shutdown
9. Add audit logging for all power management operations
10. Write comprehensive tests (unit + integration)
11. Run `uv run pytest --cov` - must pass ≥85% coverage
12. Run `uv run ruff check` - zero errors

SANDBOX MODE HANDLING:
- full: Mock all operations, return success without executing
- partial: Log operations but don't execute
- disabled: Actually execute operations (CAREFUL with reboot!)

JSON SCHEMA (from Doc 05 §3):
system.get_basic_info returns:
{
  "hostname": str,
  "model": str,  // "Raspberry Pi 4 Model B"
  "os": str,
  "kernel": str,
  "uptime_seconds": int,
  "serial": str,
  "timestamp": str  // ISO 8601
}

SECURITY REQUIREMENTS:
- Reboot/shutdown MUST require admin role
- MUST log to audit log before executing
- MUST check sandbox mode before executing
- Agent must validate commands before executing

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Show system info tools returning accurate data
- Demonstrate sandbox modes working
- Mark ready for human review

IF STUCK:
- Review Doc 06 §3 for complete specifications
- Start with read-only tools (get_basic_info) first
- Test sandbox mode thoroughly before testing real reboot
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. These are the first working MCP tools - they validate the entire stack (MCP server → IPC → agent → privileged operations).
```

---

## Issue #6: GPIO & I2C Device Control

### 📌 Title
```
[Phase 1] GPIO & I2C Device Control
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 5-6 hours
**Complexity**: Medium
**Dependencies**: Issue #4
**Requires Hardware**: Yes (LED for GPIO, I2C sensor optional)

**Scope**: Implement GPIO and I2C device control tools with safety guardrails (whitelists).

**Deliverables**:
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

**Acceptance Criteria**:
- ✅ GPIO tools work on test hardware (LED blink test recommended)
- ✅ I2C tools detect devices on bus (scan_bus returns addresses)
- ✅ Pin/address whitelists enforced (reject non-whitelisted operations)
- ✅ PWM generates correct frequency
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Sandbox mode supported (full=mocked, disabled=real hardware)
- ✅ Operator role required for GPIO/I2C write operations
- ✅ Test coverage ≥85% (unit tests with mocks)

**Design Documents**:
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §7: gpio.*, i2c.* namespaces
- [Doc 08](08-device-control-and-reboot-shutdown-safeguards-design.md) §4-5: GPIO & I2C

**Implementation Notes**:
```python
src/mcp_raspi/tools/
  gpio.py            # All gpio.* tools
  i2c.py             # All i2c.* tools
src/mcp_raspi_ops/handlers/
  gpio.py            # Agent GPIO handlers (gpiozero)
  i2c.py             # Agent I2C handlers (smbus2)
```

**Hardware Testing Notes**:
- **GPIO**: Connect LED to GPIO 17 (BCM numbering) + resistor, test write_pin
- **I2C**: Connect any I2C sensor (e.g., BME280), test scan_bus and read
- **Safety**: Test whitelist rejection (try non-whitelisted pin/address)

**Time Breakdown**:
- GPIO implementation: 2 hours
- I2C implementation: 2 hours
- Whitelist logic: 0.5 hours
- Agent hardware integration: 1 hour
- Testing (unit + hardware): 1.5 hours

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] Hardware-specific code has sandbox mode handling
- [ ] Whitelists properly enforced

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing GPIO & I2C Device Control for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #6 - implementing hardware control with safety guardrails
- Depends on: Issue #4 (Security) must be complete
- Requires hardware: LED for GPIO testing, I2C sensor optional
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: gpiozero for GPIO, smbus2 for I2C
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/05-mcp-tools-interface-and-json-schema-specification.md §7 (gpio.*, i2c.* namespaces)
- docs/08-device-control-and-reboot-shutdown-safeguards-design.md §4-5 (GPIO & I2C)

DELIVERABLES:
1. gpio.read_pin: read digital state (BCM pin numbering)
2. gpio.write_pin: write digital state with whitelist enforcement
3. gpio.configure_pin: set mode (in/out), pull-up/down
4. gpio.set_pwm: basic PWM output (fixed frequency initially)
5. gpio.get_all_states: bulk read all configured pins
6. i2c.scan_bus: detect devices on I2C bus
7. i2c.read: read bytes from I2C device with address whitelist
8. i2c.write: write bytes to I2C device with address whitelist
9. Configuration: GPIO pin whitelist, I2C address whitelist/blacklist
10. Agent implementation using gpiozero and smbus2
11. Unit tests (mocked), hardware validation tests (documented)

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/tools/
  gpio.py            # All gpio.* tools
  i2c.py             # All i2c.* tools
src/mcp_raspi_ops/handlers/
  gpio.py            # Agent GPIO handlers (gpiozero)
  i2c.py             # Agent I2C handlers (smbus2)
tests/
  test_tools_gpio.py
  test_tools_i2c.py
  test_handlers_gpio.py
  test_handlers_i2c.py
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- GPIO tools work on test hardware (LED blink test recommended)
- I2C tools detect devices on bus (scan_bus returns addresses)
- Pin/address whitelists enforced (reject non-whitelisted operations)
- PWM generates correct frequency
- All JSON schemas match Doc 05 specifications exactly
- Sandbox mode supported (full=mocked, disabled=real hardware)
- Operator role required for GPIO/I2C write operations
- Test coverage ≥85% (unit tests with mocks)

WHITELIST CONFIGURATION (from design docs):
GPIO: allowed_pins: [17, 18, 22, 23, 24, 25]  // BCM numbering
I2C: allowed_addresses: [0x76, 0x77]  // Sensor addresses
I2C: blocked_addresses: [0x00-0x07, 0x78-0x7F]  // Reserved

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Implement GPIO tools using gpiozero in agent
3. Implement I2C tools using smbus2 in agent
4. Add whitelist/blacklist enforcement in MCP server
5. Add @require_role("operator") for write operations
6. Implement sandbox mode handling
7. Write unit tests with mocked gpiozero/smbus2
8. Write hardware validation tests (optional, documented)
9. Run `uv run pytest --cov` - must pass ≥85% coverage
10. Run `uv run ruff check` - zero errors

HARDWARE TESTING (recommended but optional):
- GPIO: Connect LED to GPIO 17 + 220Ω resistor to ground
- Test gpio.write_pin(17, true) - LED should light up
- I2C: Connect BME280 sensor (address 0x76 or 0x77)
- Test i2c.scan_bus() - should detect sensor address

CRITICAL SAFETY REQUIREMENTS:
- MUST enforce GPIO pin whitelist (prevent access to dangerous pins)
- MUST enforce I2C address whitelist
- NEVER allow access to I2C reserved addresses (0x00-0x07, 0x78-0x7F)
- GPIO pins must be explicitly configured before use
- PWM frequency must be validated (1Hz - 10kHz range)

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Show GPIO/I2C tools working (with mocks or hardware)
- Demonstrate whitelist enforcement working
- Mark ready for human review

IF STUCK:
- Review Doc 08 §4-5 for complete specifications
- Start with simple GPIO read/write before PWM
- Use gpiozero MockFactory for testing without hardware
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. These hardware control tools demonstrate the full security model (RBAC + whitelists + audit logging).
```

---

## Issue #7: Service & Process Management Tools

### 📌 Title
```
[Phase 1] Service & Process Management Tools
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 5-6 hours
**Complexity**: Medium
**Dependencies**: Issue #4
**Requires Hardware**: No

**Scope**: Implement systemd service management and process monitoring tools.

**Deliverables**:
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

**Acceptance Criteria**:
- ✅ `service.list_services` returns only whitelisted services
- ✅ `service.control_service` starts/stops/restarts services successfully
- ✅ Service whitelist prevents control of non-whitelisted services
- ✅ `process.list_processes` returns accurate process list
- ✅ Filtering works (by name, user, CPU%, etc.)
- ✅ Pagination works correctly (offset/limit parameters)
- ✅ Operator role required for service control
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

**Design Documents**:
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §5-6: service.*, process.*
- [Doc 07](07-service-and-process-management-module-design.md): Complete design

**Implementation Notes**:
```python
src/mcp_raspi/tools/
  service.py         # All service.* tools
  process.py         # All process.* tools
src/mcp_raspi_ops/handlers/
  service.py         # Agent systemd handlers (D-Bus)
  process.py         # Agent process handlers (psutil)
```

**Safe Testing**:
Create a test systemd service for testing:
```ini
[Unit]
Description=MCP Test Service
[Service]
ExecStart=/bin/sleep 3600
[Install]
WantedBy=multi-user.target
```

**Time Breakdown**:
- Service management tools: 2 hours
- Process management tools: 1.5 hours
- Whitelist enforcement: 0.5 hours
- Pagination logic: 0.5 hours
- Agent systemd/psutil integration: 1 hour
- Testing: 1.5 hours

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] Service whitelist properly enforced
- [ ] D-Bus integration working correctly

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing Service & Process Management Tools for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #7 - implementing systemd service control and process monitoring
- Depends on: Issue #4 (Security) must be complete
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: dbus-next for systemd, psutil for processes
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/05-mcp-tools-interface-and-json-schema-specification.md §5-6 (service.*, process.* namespaces)
- docs/07-service-and-process-management-module-design.md (Complete design)

DELIVERABLES:
1. service.list_services: query systemd, filter by whitelist
2. service.get_status: get status of single service
3. service.control_service: start/stop/restart with whitelist enforcement
4. service.set_enabled: enable/disable autostart
5. Service whitelist enforcement: configurable list of manageable services
6. process.list_processes: list processes with filtering (name, user, CPU%)
7. process.get_info: detailed info for single PID
8. Pagination support: offset/limit for large result sets
9. Agent implementation: systemd via D-Bus, processes via psutil
10. Unit tests, integration tests with real systemd (safe test service)

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/tools/
  service.py         # All service.* tools
  process.py         # All process.* tools
src/mcp_raspi_ops/handlers/
  service.py         # Agent systemd handlers (D-Bus)
  process.py         # Agent process handlers (psutil)
tests/
  test_tools_service.py
  test_tools_process.py
  test_handlers_service.py
  test_handlers_process.py
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- service.list_services returns only whitelisted services
- service.control_service starts/stops/restarts services successfully
- Service whitelist prevents control of non-whitelisted services
- process.list_processes returns accurate process list
- Filtering works (by name, user, CPU%, etc.)
- Pagination works correctly (offset/limit parameters)
- Operator role required for service control
- All JSON schemas match Doc 05 specifications exactly
- Test coverage ≥85%

WHITELIST CONFIGURATION (from design docs):
allowed_services: ["nginx", "docker", "custom-app.service"]
# Only these services can be controlled via MCP tools

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Implement service tools using dbus-next for systemd interaction
3. Implement process tools using psutil for process monitoring
4. Add service whitelist enforcement in MCP server
5. Add @require_role("operator") for service control operations
6. Implement pagination logic (offset/limit)
7. Create safe test systemd service for integration tests
8. Write unit tests with mocked D-Bus/psutil
9. Write integration tests with real systemd service
10. Run `uv run pytest --cov` - must pass ≥85% coverage
11. Run `uv run ruff check` - zero errors

SYSTEMD D-BUS INTEGRATION:
- Use dbus-next library for systemd communication
- Connect to system bus: org.freedesktop.systemd1
- Service control: StartUnit, StopUnit, RestartUnit methods
- Service status: GetUnit, GetUnitByPID methods
- Handle D-Bus errors gracefully

CRITICAL SAFETY REQUIREMENTS:
- MUST enforce service whitelist (prevent control of critical system services)
- NEVER allow control of: systemd, dbus, networking, sshd (unless explicitly whitelisted)
- Service operations require operator role
- All service control actions MUST be logged to audit log
- Handle D-Bus permission errors gracefully

PAGINATION IMPLEMENTATION:
- offset: Number of results to skip
- limit: Maximum results to return
- Return total count in response metadata
- Example: offset=0, limit=50 returns first 50 processes

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Show service/process tools working (with mocks or real systemd)
- Demonstrate whitelist enforcement working
- Mark ready for human review

IF STUCK:
- Review Doc 07 for complete specifications
- Start with read-only tools (list_services, list_processes) first
- Use dbus-next MockBus for testing without system bus
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. These tools enable safe service management - critical for production deployments.
```

---

## Issue #8: Metrics Sampling & Query System

### 📌 Title
```
[Phase 1] Metrics Sampling & Query System
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 5-6 hours
**Complexity**: Medium
**Dependencies**: Issue #4
**Requires Hardware**: No

**Scope**: Implement background metrics sampling with SQLite storage and time-series queries.

**Deliverables**:
- [ ] SQLite schema design: metrics table with timestamp, metric type, value
- [ ] `metrics.start_sampling`: start background sampling job (asyncio)
- [ ] `metrics.stop_sampling`: stop background job gracefully
- [ ] `metrics.get_status`: return sampling state (active, interval, metrics)
- [ ] `metrics.query`: time range queries with basic aggregation (min/max/avg)
- [ ] Background job: sample CPU, memory, disk, temp every N seconds
- [ ] Retention policy: delete metrics older than configured days
- [ ] Configuration: sampling interval, retention days, metrics to collect
- [ ] Unit tests, integration tests with real SQLite DB

**Acceptance Criteria**:
- ✅ `metrics.start_sampling` starts background job
- ✅ Metrics written to SQLite database at configured interval
- ✅ `metrics.query` returns correct data for time ranges
- ✅ Aggregation functions work (min/max/avg)
- ✅ Retention policy deletes old data correctly
- ✅ Sampling can be stopped and restarted
- ✅ Database handles concurrent access (sampling + queries)
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

**Design Documents**:
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §4: metrics.* namespace
- [Doc 06](06-system-information-and-metrics-module-design.md) §4: Metrics module
- [Doc 09](09-logging-observability-and-diagnostics-design.md) §3: Metrics storage

**Implementation Notes**:
```python
src/mcp_raspi/
  metrics/
    __init__.py
    sampler.py         # Background sampling job
    storage.py         # SQLite storage layer
    query.py           # Query logic with aggregation
  tools/
    metrics.py         # All metrics.* tools
```

**SQLite Schema**:
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

**Time Breakdown**:
- SQLite schema & storage: 1.5 hours
- Background sampling job: 2 hours
- Query & aggregation logic: 1.5 hours
- Retention policy: 0.5 hours
- Testing: 1.5 hours

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] Database schema properly indexed
- [ ] Concurrent access handled safely

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing Metrics Sampling & Query System for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #8 - implementing time-series metrics with SQLite storage
- Depends on: Issue #4 (Security) must be complete
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: SQLite for storage, asyncio for background sampling, psutil for metrics
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/05-mcp-tools-interface-and-json-schema-specification.md §4 (metrics.* namespace)
- docs/06-system-information-and-metrics-module-design.md §4 (Metrics module)
- docs/09-logging-observability-and-diagnostics-design.md §3 (Metrics storage)

DELIVERABLES:
1. SQLite schema design: metrics table with timestamp, metric type, value
2. metrics.start_sampling: start background sampling job (asyncio)
3. metrics.stop_sampling: stop background job gracefully
4. metrics.get_status: return sampling state (active, interval, metrics)
5. metrics.query: time range queries with basic aggregation (min/max/avg)
6. Background job: sample CPU, memory, disk, temp every N seconds
7. Retention policy: delete metrics older than configured days
8. Configuration: sampling interval, retention days, metrics to collect
9. Unit tests, integration tests with real SQLite DB

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/
  metrics/
    __init__.py
    sampler.py         # Background sampling job (asyncio)
    storage.py         # SQLite storage layer
    query.py           # Query logic with aggregation
  tools/
    metrics.py         # All metrics.* tools
tests/
  test_metrics_sampler.py
  test_metrics_storage.py
  test_metrics_query.py
  test_tools_metrics.py
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- metrics.start_sampling starts background job
- Metrics written to SQLite database at configured interval
- metrics.query returns correct data for time ranges
- Aggregation functions work (min/max/avg)
- Retention policy deletes old data correctly
- Sampling can be stopped and restarted
- Database handles concurrent access (sampling + queries)
- All JSON schemas match Doc 05 specifications exactly
- Test coverage ≥85%

SQLITE SCHEMA (MUST IMPLEMENT EXACTLY):
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

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Implement SQLite storage layer with schema above
3. Implement background sampling job using asyncio.create_task()
4. Sample CPU, memory, disk, temperature every N seconds (configurable)
5. Implement metrics.query with time range filtering
6. Add aggregation functions: min(), max(), avg()
7. Implement retention policy (delete old data on schedule)
8. Add metrics.start_sampling, stop_sampling, get_status tools
9. Write comprehensive tests (unit + integration with real SQLite)
10. Run `uv run pytest --cov` - must pass ≥85% coverage
11. Run `uv run ruff check` - zero errors

BACKGROUND SAMPLING JOB (asyncio):
- Use asyncio.create_task() to run in background
- Sample metrics every N seconds (default: 60 seconds)
- Collect: CPU%, memory%, disk%, temperature
- Write to SQLite database using connection pool
- Handle graceful shutdown (stop_sampling)

QUERY IMPLEMENTATION:
- Time range: start_time, end_time (Unix timestamps or ISO 8601)
- Metric types: filter by metric_type
- Aggregation: min, max, avg (computed in SQL)
- Example query: "CPU avg over last hour"

RETENTION POLICY:
- Delete metrics older than configured days (default: 30 days)
- Run cleanup task periodically (e.g., daily at 2 AM)
- Use SQL: DELETE FROM metrics WHERE timestamp < ?

CONCURRENT ACCESS HANDLING:
- Use SQLite connection pool (aiosqlite recommended)
- Write-ahead logging (WAL mode) for concurrent reads
- Use transactions for write operations
- Handle database lock errors gracefully

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Show metrics sampling working (can run for 1 minute, show data in DB)
- Demonstrate query and aggregation working
- Mark ready for human review

IF STUCK:
- Review Doc 06 §4 for complete specifications
- Start with storage layer and simple queries first
- Use pytest-asyncio for testing async code
- Test with short sampling intervals (5 seconds) during development
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. This metrics system provides time-series observability - critical for monitoring device health.
```

---

## Issue #9: Logging Tools & Camera Support

### 📌 Title
```
[Phase 1] Logging Tools & Camera Support
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 5-6 hours
**Complexity**: Medium
**Dependencies**: Issue #4
**Requires Hardware**: Camera (optional)

**Scope**: Implement log query tools and basic camera capture functionality.

**Deliverables**:
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

**Acceptance Criteria**:
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

**Design Documents**:
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §9-10: logs.*, camera.*
- [Doc 08](08-device-control-and-reboot-shutdown-safeguards-design.md) §6: Camera
- [Doc 09](09-logging-observability-and-diagnostics-design.md) §5: Log query

**Implementation Notes**:
```python
src/mcp_raspi/tools/
  logs.py            # All logs.* tools
  camera.py          # All camera.* tools
src/mcp_raspi_ops/handlers/
  logs.py            # Agent log reading
  camera.py          # Agent camera capture (picamera2)
```

**Camera Testing**:
- If no camera: `camera.get_info` returns `{"detected": false}`
- If camera present: Capture test photo, verify JPEG file created

**Time Breakdown**:
- Log query tools: 2 hours
- Sensitive data masking: 0.5 hours
- Camera info tool: 0.5 hours
- Camera capture tool: 1.5 hours
- Rate limiting: 0.5 hours
- Testing: 1.5 hours

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] Sensitive data masking working correctly
- [ ] Camera handling robust (works with/without hardware)

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing Logging Tools & Camera Support for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #9 - implementing log queries and camera capture
- Depends on: Issue #4 (Security) must be complete
- Requires hardware: Camera optional (gracefully degrade if not present)
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: picamera2 for camera, file reading for logs
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/05-mcp-tools-interface-and-json-schema-specification.md §9-10 (logs.*, camera.* namespaces)
- docs/08-device-control-and-reboot-shutdown-safeguards-design.md §6 (Camera)
- docs/09-logging-observability-and-diagnostics-design.md §5 (Log query)

DELIVERABLES:
1. logs.get_recent_app_logs: query application logs with filters
2. logs.get_recent_audit_logs: query audit logs with filters
3. Time range filtering: start/end timestamps
4. Level filtering: filter by log level (DEBUG, INFO, WARNING, ERROR)
5. Pagination: offset/limit for large log sets
6. Log rotation: file-based or journald integration
7. Sensitive data masking: redact secrets in logs
8. camera.get_info: detect camera, return capabilities
9. camera.take_photo: capture JPEG with basic resolution/quality params
10. Rate limiting: max photos per minute (configurable)
11. Agent implementation: log reading, camera via picamera2
12. Unit tests, hardware tests (camera optional, documented)

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/tools/
  logs.py            # All logs.* tools
  camera.py          # All camera.* tools
src/mcp_raspi_ops/handlers/
  logs.py            # Agent log reading
  camera.py          # Agent camera capture (picamera2)
tests/
  test_tools_logs.py
  test_tools_camera.py
  test_handlers_logs.py
  test_handlers_camera.py
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- Log query tools return correct logs with filters applied
- Time range and level filtering work correctly
- Pagination works (offset/limit)
- Sensitive data masked (e.g., API keys, tokens)
- camera.get_info detects camera or returns "not detected"
- camera.take_photo captures photo (if camera present)
- Photos saved to configured media directory
- Rate limiting enforced (reject if limit exceeded)
- All JSON schemas match Doc 05 specifications exactly
- Test coverage ≥85%

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Implement log query tools (read from log files or journald)
3. Add time range filtering (parse timestamps)
4. Add level filtering (DEBUG, INFO, WARNING, ERROR)
5. Implement pagination (offset/limit)
6. Add sensitive data masking (regex patterns for API keys, tokens)
7. Implement camera.get_info (detect camera using picamera2)
8. Implement camera.take_photo (capture JPEG with resolution/quality)
9. Add rate limiting (max photos per minute)
10. Write comprehensive tests (unit + integration)
11. Run `uv run pytest --cov` - must pass ≥85% coverage
12. Run `uv run ruff check` - zero errors

LOG QUERY IMPLEMENTATION:
- Read from application log files (e.g., /var/log/mcp-raspi/app.log)
- Parse log entries (assume JSON or structured format)
- Filter by time range: start_time, end_time (ISO 8601)
- Filter by level: DEBUG, INFO, WARNING, ERROR
- Pagination: offset, limit
- Return: list of log entries with metadata

SENSITIVE DATA MASKING:
- Redact patterns: API keys, tokens, passwords, secrets
- Regex patterns: "api_key": "...", "token": "...", "password": "..."
- Replace with: "api_key": "***REDACTED***"
- MUST mask before returning logs to client

CAMERA IMPLEMENTATION:
- Use picamera2 library (Raspberry Pi camera v2/v3)
- camera.get_info: Try to detect camera, return capabilities
  - If no camera: {"detected": false}
  - If camera: {"detected": true, "model": "...", "resolutions": [...]}
- camera.take_photo: Capture JPEG
  - Parameters: width, height, quality (1-100)
  - Save to configured media directory (e.g., /var/lib/mcp-raspi/media/)
  - Return: file path, timestamp, file size

RATE LIMITING:
- Max photos per minute: configurable (default: 10)
- Track timestamps of recent captures
- Reject if limit exceeded: return error with retry-after timestamp

CAMERA TESTING (without hardware):
- Mock picamera2 in tests
- Test camera.get_info returns {"detected": false} when no camera
- Test camera.take_photo raises error when no camera
- Document: "To test with real camera, run on Raspberry Pi with camera attached"

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Show log query tools working (with sample logs)
- Show camera tools working (with mocks or real camera)
- Demonstrate sensitive data masking
- Mark ready for human review

IF STUCK:
- Review Doc 09 §5 for log query specifications
- Review Doc 08 §6 for camera specifications
- Start with log query tools before camera (simpler)
- Use mocks for camera testing without hardware
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. These tools provide observability (logs) and device interaction (camera) - important for debugging and monitoring.
```

---

## Issue #10: Self-Update Mechanism - Part 1 (Foundation)

### 📌 Title
```
[Phase 1] Self-Update Mechanism - Part 1 (Foundation)
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 6 hours
**Complexity**: High
**Dependencies**: Issue #4
**Requires Hardware**: No

**Scope**: Implement foundation for self-update: version management, directory structure, and basic update backend.

**Deliverables**:
- [ ] `version.json` structure: current, previous, history
- [ ] Version directory layout: `/opt/mcp-raspi/releases/v1.0.0/`, `current` symlink
- [ ] `manage.get_server_status`: return version, uptime, last_update timestamp
- [ ] `UpdateBackend` abstraction: interface for different update sources
- [ ] `PythonPackageBackend`: download new version via `uv`/`pip`
- [ ] Version validation: semantic versioning checks
- [ ] Atomic directory operations: safe symlink switching
- [ ] Configuration: update source, version directory, rollback settings
- [ ] Unit tests for version management, backend abstraction

**Acceptance Criteria**:
- ✅ Version directory structure created correctly
- ✅ `version.json` tracks current/previous versions
- ✅ `manage.get_server_status` returns accurate version info
- ✅ `PythonPackageBackend` can fetch package info (mock in tests)
- ✅ Symlink operations are atomic (no race conditions)
- ✅ Version validation rejects invalid version strings
- ✅ Configuration fully integrated
- ✅ All JSON schemas match Doc 05 specifications
- ✅ Test coverage ≥85%

**Design Documents**:
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §8: manage.* namespace
- [Doc 10](10-self-update-mechanism-and-rollback-strategy-design.md) §3-4: Version & backends

**Implementation Notes**:
```python
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

**Version Directory Structure**:
```
/opt/mcp-raspi/
  releases/
    v1.0.0/            # First release
    v1.0.1/            # New release
  current -> v1.0.0    # Symlink to active version
  version.json         # Version tracking
```

**Time Breakdown**:
- Version management: 1.5 hours
- Directory structure & operations: 1 hour
- UpdateBackend abstraction: 1 hour
- PythonPackageBackend: 1.5 hours
- manage.get_server_status tool: 0.5 hours
- Testing: 1.5 hours

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] Atomic operations properly implemented
- [ ] Version validation robust

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing Self-Update Mechanism - Part 1 (Foundation) for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #10 - implementing self-update foundation (Part 1 of 2)
- Depends on: Issue #4 (Security) must be complete
- Part 2 (Issue #11) will implement the state machine
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: pathlib for directory operations, semantic versioning
- Time limit: 6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/05-mcp-tools-interface-and-json-schema-specification.md §8 (manage.* namespace)
- docs/10-self-update-mechanism-and-rollback-strategy-design.md §3-4 (Version & backends)

DELIVERABLES:
1. version.json structure: current, previous, history
2. Version directory layout: /opt/mcp-raspi/releases/v1.0.0/, current symlink
3. manage.get_server_status: return version, uptime, last_update timestamp
4. UpdateBackend abstraction: interface for different update sources
5. PythonPackageBackend: download new version via uv/pip
6. Version validation: semantic versioning checks
7. Atomic directory operations: safe symlink switching
8. Configuration: update source, version directory, rollback settings
9. Unit tests for version management, backend abstraction

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/
  updates/
    __init__.py
    version.py           # Version management, version.json
    backends.py          # UpdateBackend abstraction
    python_backend.py    # PythonPackageBackend
    operations.py        # Atomic directory operations
  tools/
    manage.py            # manage.* tools
tests/
  test_updates_version.py
  test_updates_backends.py
  test_updates_operations.py
  test_tools_manage.py
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- Version directory structure created correctly
- version.json tracks current/previous versions
- manage.get_server_status returns accurate version info
- PythonPackageBackend can fetch package info (mock in tests)
- Symlink operations are atomic (no race conditions)
- Version validation rejects invalid version strings
- Configuration fully integrated
- All JSON schemas match Doc 05 specifications exactly
- Test coverage ≥85%

VERSION DIRECTORY STRUCTURE (MUST IMPLEMENT):
```
/opt/mcp-raspi/
  releases/
    v1.0.0/            # First release directory
    v1.0.1/            # New release directory
  current -> v1.0.0    # Symlink to active version
  version.json         # Version tracking file
```

VERSION.JSON STRUCTURE:
```json
{
  "current": "1.0.0",
  "previous": "0.9.0",
  "history": [
    {
      "version": "1.0.0",
      "installed_at": "2025-01-15T10:00:00Z",
      "source": "pypi"
    },
    {
      "version": "0.9.0",
      "installed_at": "2025-01-10T09:00:00Z",
      "source": "pypi"
    }
  ]
}
```

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Implement version.py with VersionManager class
3. Implement version.json read/write with Pydantic models
4. Implement directory structure creation (pathlib)
5. Implement atomic symlink switching (tempfile + os.rename)
6. Create UpdateBackend abstract base class
7. Implement PythonPackageBackend (use subprocess to call uv/pip)
8. Add semantic version validation (use packaging library)
9. Implement manage.get_server_status tool
10. Write comprehensive tests (unit tests, mocked backends)
11. Run `uv run pytest --cov` - must pass ≥85% coverage
12. Run `uv run ruff check` - zero errors

ATOMIC SYMLINK SWITCHING (CRITICAL):
- NEVER use os.symlink() directly (not atomic)
- Use tempfile + os.rename() for atomicity:
  1. Create temp symlink: symlink(target, temp_path)
  2. Atomic rename: os.rename(temp_path, final_path)
- This ensures no race conditions during updates

UPDATEBACKEND ABSTRACTION:
```python
class UpdateBackend(ABC):
    @abstractmethod
    async def check_for_updates(self) -> Optional[str]:
        """Check if new version available. Return version string or None."""
        pass

    @abstractmethod
    async def download_version(self, version: str, dest_dir: Path) -> None:
        """Download specified version to destination directory."""
        pass
```

PYTHONPACKAGEBACKEND IMPLEMENTATION:
- Use subprocess to call: uv pip download mcp-raspi==VERSION
- Parse output to get package info
- Extract package to version directory
- Validate package contents (check for __init__.py, etc.)

VERSION VALIDATION:
- Use packaging.version.Version for parsing
- Accept: "1.0.0", "1.2.3", "2.0.0-beta.1"
- Reject: "v1.0.0", "1.0", "latest", invalid strings
- Semantic versioning: MAJOR.MINOR.PATCH

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Show version.json structure working
- Show directory structure created correctly
- Demonstrate atomic symlink switching
- Mark ready for human review

IF STUCK:
- Review Doc 10 §3-4 for complete specifications
- Start with version.json and directory structure first
- Use pathlib for all path operations
- Test atomic operations carefully (race condition scenarios)
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. This foundation is critical for Issue #11 (state machine). Do NOT implement the full update process yet - that's Issue #11.
```

---

## Issue #11: Self-Update Mechanism - Part 2 (State Machine)

### 📌 Title
```
[Phase 1] Self-Update Mechanism - Part 2 (State Machine)
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 6 hours
**Complexity**: Very High
**Dependencies**: Issue #10
**Requires Hardware**: No

**Scope**: Implement the complete self-update state machine with rollback capability.

**Deliverables**:
- [ ] Update state machine: idle → checking → preparing → switching → verifying → success/failed
- [ ] `manage.update_server`: implement full state machine
- [ ] Update process: download → validate → switch symlink → restart service → verify
- [ ] Systemd service restart integration: graceful restart after update
- [ ] Automatic rollback: trigger on repeated failures (health checks)
- [ ] Manual rollback: CLI tool to rollback to previous version
- [ ] Health check system: verify service working after update
- [ ] State persistence: track update state across restarts
- [ ] Comprehensive state machine tests (all transitions, error cases)

**Acceptance Criteria**:
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

**Design Documents**:
- [Doc 05](05-mcp-tools-interface-and-json-schema-specification.md) §8: manage.update_server
- [Doc 10](10-self-update-mechanism-and-rollback-strategy-design.md) §5-8: State machine & rollback

**Implementation Notes**:
```python
src/mcp_raspi/updates/
  state_machine.py     # UpdateStateMachine class
  rollback.py          # Rollback logic
  health_check.py      # Post-update health checks
  systemd_restart.py   # Service restart integration
```

**State Machine Diagram**:
```
idle → checking → preparing → switching → verifying
                     ↓            ↓         ↓
                  failed ←─────────┴────────┘
                     ↓
                 rollback
```

**Critical Testing**:
- **Test on real device**: Update from v1.0.0 to v1.0.1 (test versions)
- **Test rollback**: Simulate failure, verify automatic rollback
- **Test service restart**: Ensure no downtime during update

**Time Breakdown**:
- State machine core: 2 hours
- Update process integration: 1.5 hours
- Rollback logic: 1 hour
- Health checks: 0.5 hours
- Systemd restart: 0.5 hours
- Testing (including E2E): 2 hours

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] No security vulnerabilities introduced
- [ ] State machine handles all error cases
- [ ] Rollback tested thoroughly

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing Self-Update Mechanism - Part 2 (State Machine) for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #11 - implementing self-update state machine (Part 2 of 2)
- Depends on: Issue #10 (Self-Update Foundation) MUST be complete
- This is the MOST COMPLEX issue in Phase 1 - state machines are hard!
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Tools: asyncio for state machine, systemd integration
- Time limit: 6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/05-mcp-tools-interface-and-json-schema-specification.md §8 (manage.update_server)
- docs/10-self-update-mechanism-and-rollback-strategy-design.md §5-8 (State machine & rollback)

DELIVERABLES:
1. Update state machine: idle → checking → preparing → switching → verifying → success/failed
2. manage.update_server: implement full state machine
3. Update process: download → validate → switch symlink → restart service → verify
4. Systemd service restart integration: graceful restart after update
5. Automatic rollback: trigger on repeated failures (health checks)
6. Manual rollback: CLI tool to rollback to previous version
7. Health check system: verify service working after update
8. State persistence: track update state across restarts
9. Comprehensive state machine tests (all transitions, error cases)

EXPECTED FILE STRUCTURE:
```python
src/mcp_raspi/updates/
  state_machine.py     # UpdateStateMachine class
  rollback.py          # Rollback logic
  health_check.py      # Post-update health checks
  systemd_restart.py   # Service restart integration
tests/
  test_updates_state_machine.py
  test_updates_rollback.py
  test_updates_health_check.py
  test_updates_e2e.py  # End-to-end update test
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- manage.update_server completes full update cycle
- Service restarts automatically after update
- Health checks detect broken updates
- Automatic rollback triggers on repeated failures
- Manual rollback CLI tool works
- State machine handles all error cases gracefully
- version.json updated correctly throughout process
- Symlink switching is atomic (no downtime)
- Admin role required for update operations
- Test coverage ≥85% (including error paths)

STATE MACHINE STATES (MUST IMPLEMENT):
1. idle: No update in progress
2. checking: Checking for new version
3. preparing: Downloading and validating new version
4. switching: Switching symlink to new version
5. verifying: Running health checks on new version
6. success: Update completed successfully
7. failed: Update failed, rollback needed
8. rolling_back: Performing rollback to previous version

STATE TRANSITIONS:
- idle → checking (user calls manage.update_server)
- checking → preparing (new version found)
- preparing → switching (download complete, validated)
- switching → verifying (symlink switched, service restarted)
- verifying → success (health checks passed)
- verifying → failed (health checks failed)
- failed → rolling_back (automatic rollback triggered)
- rolling_back → idle (rollback complete)

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Implement UpdateStateMachine class with state enum
3. Implement state transitions with validation
4. Implement manage.update_server tool (orchestrates state machine)
5. Integrate with UpdateBackend from Issue #10
6. Implement systemd service restart (subprocess: systemctl restart)
7. Implement health check system (verify service responds)
8. Implement automatic rollback on repeated failures
9. Implement manual rollback CLI tool
10. Add state persistence (save state to disk)
11. Write comprehensive tests (unit + integration + E2E)
12. Run `uv run pytest --cov` - must pass ≥85% coverage
13. Run `uv run ruff check` - zero errors

UPDATE PROCESS SEQUENCE:
1. Check for updates (call backend.check_for_updates())
2. Download new version (call backend.download_version())
3. Validate download (checksum, signature if available)
4. Switch symlink atomically (use operations.py from Issue #10)
5. Restart systemd service (systemctl restart mcp-raspi-server)
6. Run health checks (HTTP ping, basic tool call)
7. If health checks fail 3 times: automatic rollback
8. Update version.json with new current/previous versions

HEALTH CHECK IMPLEMENTATION:
- After update, wait 10 seconds for service to start
- Make basic health check requests:
  - HTTP GET to /health endpoint (if available)
  - Or call a simple MCP tool (e.g., system.get_basic_info)
- Retry 3 times with 5-second delays
- If all fail: trigger rollback

AUTOMATIC ROLLBACK:
- Triggered when health checks fail repeatedly
- Switch symlink back to previous version (from version.json)
- Restart service again
- Update version.json to restore previous state
- Log rollback to audit log

MANUAL ROLLBACK CLI TOOL:
```bash
mcp-raspi-rollback --to-version 1.0.0
# or
mcp-raspi-rollback --to-previous
```

STATE PERSISTENCE:
- Save current state to /opt/mcp-raspi/update_state.json
- Persist across service restarts
- On restart, check if update was in progress
- Resume or rollback as needed

CRITICAL TESTING REQUIREMENTS:
- Test full update cycle (mock or with test versions)
- Test all state transitions
- Test automatic rollback on health check failure
- Test manual rollback
- Test state persistence across restarts
- Test error handling (network failure, invalid version, etc.)

SYSTEMD INTEGRATION:
- Use subprocess to call: systemctl restart mcp-raspi-server
- Run as root (agent has privileges)
- Wait for service to start (check status)
- Handle restart failures gracefully

WHEN COMPLETE:
- Post implementation summary to this issue
- Post test coverage report
- Show state machine working (can simulate update with test versions)
- Demonstrate rollback working (manual and automatic)
- Document any limitations or edge cases
- Mark ready for human review

IF STUCK:
- Review Doc 10 §5-8 for complete specifications
- Start with basic state machine before adding rollback
- Test each state transition individually
- Use pytest fixtures for complex test scenarios
- This is the hardest issue - it's OK to ask for clarification!
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. This state machine is the most critical component of self-update. It MUST be robust and handle all error cases. Take time to test thoroughly!
```

---

## Issue #12: Deployment & Final Integration

### 📌 Title
```
[Phase 1] Deployment & Final Integration
```

### 📋 Issue Description (Copy to GitHub Issue Body)

**Estimated Time**: 5-6 hours
**Complexity**: Medium
**Dependencies**: All previous issues (#1-11)
**Requires Hardware**: No

**Scope**: Create deployment artifacts, systemd integration, and operations documentation.

**Deliverables**:
- [ ] Systemd unit files: `mcp-raspi-server.service`, `raspi-ops-agent.service`
- [ ] Installation script: `install.sh` for automated setup
- [ ] Configuration templates: `config.example.yml` with all options documented
- [ ] Cloudflare Tunnel setup guide
- [ ] Operations runbook: troubleshooting, common issues, recovery procedures
- [ ] Acceptance checklist: validate all Phase 1 requirements (see `docs/acceptance-checklist.md`)
- [ ] CI/CD integration: ensure all tests pass in pipeline
- [ ] Final E2E tests on clean Raspberry Pi OS install

**Acceptance Criteria**:
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

**Design Documents**:
- [Doc 12](12-deployment-systemd-integration-and-operations-runbook.md): Complete deployment guide
- [acceptance-checklist.md](acceptance-checklist.md): Phase 1 release criteria

**Implementation Notes**:
```
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

**Systemd Service Example**:
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

**Time Breakdown**:
- Systemd unit files: 1 hour
- Installation script: 1.5 hours
- Configuration templates: 0.5 hours
- Operations runbook: 1.5 hours
- Acceptance testing: 2 hours
- Documentation updates: 1 hour

**Human Review Checklist**:
- [ ] Code follows design document specifications
- [ ] All acceptance criteria met
- [ ] Tests comprehensive and passing
- [ ] Coverage ≥85% on new code
- [ ] Systemd integration working correctly
- [ ] Documentation complete and accurate
- [ ] All Phase 1 requirements validated

### 🤖 GitHub Copilot Agent Custom Prompt (Use When Assigning)

```
You are implementing Deployment & Final Integration for the Raspberry Pi MCP Server project.

CONTEXT:
- Project: Python 3.11+ MCP server for Raspberry Pi device management
- This is Issue #12 - FINAL issue of Phase 1
- Depends on: ALL previous issues (#1-11) MUST be complete
- This issue ties everything together for production deployment
- Design docs are in docs/ directory - read thoroughly
- Standards: TDD, ≥85% test coverage, type hints, docstrings
- Time limit: 5-6 hours for this issue

DESIGN DOCUMENTS TO READ:
- docs/12-deployment-systemd-integration-and-operations-runbook.md (Complete deployment guide)
- docs/acceptance-checklist.md (Phase 1 release criteria)
- All previous design docs (for reference)

DELIVERABLES:
1. Systemd unit files: mcp-raspi-server.service, raspi-ops-agent.service
2. Installation script: install.sh for automated setup
3. Configuration templates: config.example.yml with all options documented
4. Cloudflare Tunnel setup guide
5. Operations runbook: troubleshooting, common issues, recovery procedures
6. Acceptance checklist: validate all Phase 1 requirements
7. CI/CD integration: ensure all tests pass in pipeline
8. Final E2E tests on clean Raspberry Pi OS install

EXPECTED FILE STRUCTURE:
```
deployment/
  systemd/
    mcp-raspi-server.service
    raspi-ops-agent.service
  install.sh
  uninstall.sh
  config.example.yml
docs/
  cloudflare-tunnel-setup.md
  operations-runbook.md
  troubleshooting.md
  getting-started.md
```

ACCEPTANCE CRITERIA (ALL MUST PASS):
- Systemd services start/stop/restart correctly
- Services restart on boot automatically
- Installation script works on clean Raspberry Pi OS
- Cloudflare Tunnel setup documented and tested
- Operations runbook covers all troubleshooting scenarios
- Acceptance checklist passes on Pi 3, Pi 4, Pi 5 (if available)
- All CI/CD tests passing
- Test coverage ≥85% overall project
- No high/critical security vulnerabilities
- README updated with getting started guide

SYSTEMD UNIT FILES (MUST IMPLEMENT):

mcp-raspi-server.service:
```ini
[Unit]
Description=Raspberry Pi MCP Server
After=network.target raspi-ops-agent.service
Requires=raspi-ops-agent.service

[Service]
Type=simple
User=mcp-raspi
Group=mcp-raspi
ExecStart=/opt/mcp-raspi/current/bin/mcp-raspi-server --config /etc/mcp-raspi/config.yml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

raspi-ops-agent.service:
```ini
[Unit]
Description=Raspberry Pi Ops Agent (Privileged)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/opt/mcp-raspi/current/bin/raspi-ops-agent --config /etc/mcp-raspi/config.yml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

DEVELOPMENT PROCESS:
1. Read all linked design documents first
2. Create systemd unit files (above templates)
3. Create install.sh script (see requirements below)
4. Create config.example.yml with all configuration options
5. Write Cloudflare Tunnel setup guide
6. Write operations runbook (troubleshooting, recovery)
7. Run through acceptance checklist (docs/acceptance-checklist.md)
8. Run final E2E tests on clean system (or document process)
9. Update README.md with getting started guide
10. Run `uv run pytest --cov` - must pass ≥85% coverage overall
11. Run `uv run ruff check` - zero errors

INSTALL.SH REQUIREMENTS:
```bash
#!/bin/bash
# Must handle:
# 1. Create mcp-raspi user/group
# 2. Create directory structure (/opt/mcp-raspi, /etc/mcp-raspi, /var/log/mcp-raspi)
# 3. Install Python dependencies (uv sync)
# 4. Copy systemd unit files to /etc/systemd/system/
# 5. Enable and start services (systemctl enable/start)
# 6. Create initial config from template
# 7. Set correct permissions (mcp-raspi user, root for agent)
# 8. Verify installation (health check)
```

CONFIG.EXAMPLE.YML:
- Document ALL configuration options
- Include comments explaining each option
- Provide safe defaults
- Include examples for common scenarios
- Reference design docs for details

CLOUDFLARE TUNNEL SETUP GUIDE:
- Prerequisites: Cloudflare account, domain name
- Step 1: Install cloudflared
- Step 2: Authenticate cloudflared
- Step 3: Create tunnel configuration
- Step 4: Configure Cloudflare Access (OAuth)
- Step 5: Test tunnel connectivity
- Security considerations

OPERATIONS RUNBOOK:
- Common tasks: start/stop/restart services, view logs, update config
- Troubleshooting: service won't start, connection issues, update failed
- Recovery procedures: rollback update, restore from backup
- Monitoring: health checks, log locations, metrics queries
- Security: audit log review, access control verification

ACCEPTANCE TESTING:
- Go through docs/acceptance-checklist.md systematically
- Test on clean Raspberry Pi OS install (or VM)
- Verify all MCP tools work
- Verify systemd integration
- Verify security features (OAuth, RBAC, audit log)
- Document any issues or limitations

CI/CD INTEGRATION:
- Ensure GitHub Actions workflow exists
- Run all tests in CI: pytest --cov
- Run linting: ruff check
- Check coverage threshold: ≥85%
- Build package: uv build
- Optional: Deploy to test device

FINAL E2E TEST CHECKLIST:
- [ ] Install on clean Raspberry Pi OS
- [ ] Services start automatically on boot
- [ ] All MCP tools work (system, GPIO, services, etc.)
- [ ] OAuth authentication works
- [ ] RBAC enforced correctly
- [ ] Audit log captures events
- [ ] Self-update works (test with mock versions)
- [ ] Rollback works
- [ ] Uninstall.sh cleanly removes everything

WHEN COMPLETE:
- Post implementation summary to this issue
- Post final test coverage report (overall project)
- Share acceptance checklist results
- Document any known issues or limitations
- Update project README with installation instructions
- Mark Phase 1 COMPLETE! 🎉

IF STUCK:
- Review Doc 12 for complete specifications
- Review docs/acceptance-checklist.md for requirements
- Test on actual Raspberry Pi if possible (or document VM testing)
- This is the final issue - make sure everything works!
- If approaching 6-hour limit, document progress and stop

SUCCESS CRITERIA:
All acceptance criteria met. Phase 1 is PRODUCTION-READY. This is the culmination of all 12 issues - make it count!
```

---

**Document Version**: 1.2
**Last Updated**: 2025-12-04
**Format**: Complete 3-part specifications (Title + Description + Custom Prompt)
**Status**: Issues #5-12 complete - ALL ISSUES READY FOR GITHUB
