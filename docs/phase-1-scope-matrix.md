# Phase 1 Scope Matrix – Raspberry Pi MCP Server

## 1. Document Purpose

This document provides a clear breakdown of what functionality is **in scope for Phase 1** versus **deferred to Phase 2+**. This document is designed for AI-assisted development workflows.

### For AI Assistants Reading This Document

This scope matrix helps you:

- **Understand project boundaries**: Know exactly what to implement in Phase 1 vs what to defer
- **Prioritize features correctly**: Focus on ✅ Must-Have features before ⚠️ Should-Have features
- **Reference implementation details**: Each feature links to detailed design documents (01-14)
- **Estimate complexity**: Use complexity ratings to break down work into manageable chunks
- **Maintain consistency**: Follow the defined patterns and avoid scope creep

**When implementing**: Always check this matrix first. If a user requests a Phase 2+ feature during Phase 1, politely reference this document and suggest deferring unless there's explicit approval to change scope.

**When uncertain**: Reference the linked design documents (Doc 01-14) for detailed specifications, JSON schemas, security requirements, and implementation patterns.

### Project Goals

**Phase 1 Goal**: Deliver a secure, functional MCP server for Raspberry Pi that supports:
- Remote system monitoring and diagnostics.
- Basic device control (GPIO, I2C, camera).
- Service management with safety guardrails.
- Self-update capability with rollback.
- Comprehensive logging and audit trails.

**Phase 2+ Goals**: Extend with advanced features, performance optimizations, and enterprise capabilities.

---

## 2. Scope Legend

| Symbol | Meaning | Effort Estimate |
|--------|---------|-----------------|
| ✅ | **Phase 1 - Must Have** | Core functionality, blocking for Phase 1 release |
| ⚠️ | **Phase 1 - Should Have** | Important but can be simplified or deferred if needed |
| 🔄 | **Phase 1 - Partial** | Basic version in Phase 1, enhanced in Phase 2+ |
| ⏭️ | **Phase 2+** | Explicitly deferred to future phases |
| 🚫 | **Out of Scope** | Not planned for this project |

**Effort Ratings** (per feature/module, AI-assisted development):
- **XS** (Extra Small): 1-3 hours - Simple CRUD, basic wrappers, straightforward logic
- **S** (Small): 4-8 hours - Single module with tests, basic integrations, well-defined interfaces
- **M** (Medium): 1-2 days - Multi-module feature, moderate complexity, requires integration testing
- **L** (Large): 3-5 days - Complex subsystem, state machines, multiple integration points
- **XL** (Extra Large): 1-2 weeks - Major feature with high complexity, extensive testing, security-critical

**AI Development Assumptions**:
- AI assistant (like Claude) is primary developer with human oversight
- Human reviews code, provides clarifications, approves designs
- AI generates code, tests, documentation in integrated workflows
- Estimates include: implementation + unit tests + integration tests + documentation
- Debugging and iteration time included in estimates
- Hardware testing time (GPIO/I2C/Camera) adds 50-100% to estimates

---

## 3. Feature Matrix by Functional Area

### 3.1 Core Infrastructure

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **MCP Server (JSON-RPC over stdio)** | ✅ | - | L | High | Core protocol implementation |
| **Privileged agent (IPC via Unix socket)** | ✅ | - | M | Medium | Basic IPC with JSON request/response |
| **Configuration loading (YAML + env vars)** | ✅ | - | S | Medium | Pydantic-based with layering |
| **CLI argument overrides** | ⚠️ | Enhanced | XS | Low | Basic `--config`, `--log-level`, `--debug` |
| **Configuration hot-reload** | ⏭️ | ✅ | M | Medium | Requires SIGHUP handling, validation |
| **Configuration validation CLI tool** | ⏭️ | ✅ | S | Low | `mcp-raspi-config validate` |
| **Multi-instance support** | 🚫 | 🚫 | - | - | One MCP server per device |

### 3.2 Security & Authentication (Document 04)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **Role-based access control (RBAC)** | ✅ | - | M | Medium | viewer, operator, admin roles |
| **Cloudflare Access/OAuth integration** | ✅ | - | L | High | JWT validation, JWKS fetching |
| **Local auth mode (LAN-only)** | ✅ | - | S | Low | Static tokens or permissive for dev |
| **mTLS support** | ⏭️ | ✅ | M | Medium | Certificate-based auth |
| **Tool-level policy enforcement** | 🔄 | Enhanced | M | Medium | Basic role checks in Phase 1 |
| **Fine-grained per-tool policies** | ⏭️ | ✅ | M | Medium | Per-tool rate limits, custom rules |
| **API key management** | ⏭️ | ✅ | S | Low | Rotate, revoke, list keys |
| **Audit log tamper-proofing** | ⏭️ | ✅ | M | High | Cryptographic signatures, append-only |
| **Session management** | ⏭️ | ✅ | M | Medium | Track active sessions, force logout |

### 3.3 MCP Tools - System Information (Document 06)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **system.get_basic_info** | ✅ | - | S | Low | Hostname, model, OS, kernel, uptime |
| **system.get_health_snapshot** | ✅ | - | M | Medium | CPU, memory, disk, temp, network |
| **system.get_network_info** | 🔄 | Enhanced | S | Low | Basic IPs/interfaces in Phase 1 |
| **system.get_detailed_network_info** | ⏭️ | ✅ | M | Medium | Routing tables, connection states |
| **system.reboot** | ✅ | - | S | Medium | With safety checks and audit |
| **system.shutdown** | ✅ | - | S | Medium | With safety checks and audit |
| **Temperature monitoring (multiple sources)** | 🔄 | Enhanced | S | Low | `/sys/class/thermal` only in Phase 1 |
| **Disk I/O metrics** | ⏭️ | ✅ | M | Medium | Read/write rates, IOPS |

### 3.4 MCP Tools - Metrics (Document 06)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **metrics.start_sampling** | ✅ | - | M | Medium | Background job with SQLite storage |
| **metrics.stop_sampling** | ✅ | - | XS | Low | Stop background job |
| **metrics.get_status** | ✅ | - | XS | Low | Is sampling active? |
| **metrics.query** | ✅ | - | M | Medium | Time range queries, basic aggregation |
| **Advanced aggregations (percentiles)** | ⏭️ | ✅ | S | Medium | 95th, 99th percentile calculations |
| **Metrics export (Prometheus)** | ⏭️ | ✅ | M | Medium | `/metrics` endpoint with Prometheus format |
| **Metrics retention policies** | 🔄 | Enhanced | S | Low | Simple days-based in Phase 1 |
| **Multi-metric correlation queries** | ⏭️ | ✅ | L | High | Complex analytical queries |

### 3.5 MCP Tools - Service Management (Document 07)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **service.list_services** | ✅ | - | M | Medium | Query systemd, apply whitelist |
| **service.get_status** | ✅ | - | S | Low | Single service status |
| **service.control_service** | ✅ | - | M | Medium | start, stop, restart with whitelist |
| **service.set_enabled** | ✅ | - | S | Medium | enable/disable autostart |
| **Service dependency validation** | ⏭️ | ✅ | M | High | Check deps before stop/disable |
| **Service logs integration** | ⏭️ | ✅ | S | Medium | Return recent journald logs for service |
| **Custom service templates** | ⏭️ | ✅ | M | Medium | Create/manage custom units |

### 3.6 MCP Tools - Process Management (Document 07)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **process.list_processes** | ✅ | - | M | Medium | Via psutil, with filtering |
| **process.get_info** | ✅ | - | S | Low | Detailed info for one PID |
| **Pagination support** | ⚠️ | Enhanced | S | Low | Basic offset/limit in Phase 1 |
| **process.send_signal** | ⏭️ | ✅ | M | High | SIGTERM, SIGKILL with safeguards |
| **Process tree visualization** | ⏭️ | ✅ | S | Medium | Parent-child relationships |
| **Resource usage trending** | ⏭️ | ✅ | M | Medium | Track per-process metrics over time |

### 3.7 MCP Tools - GPIO (Document 08)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **gpio.read_pin** | ✅ | - | S | Low | Basic digital read |
| **gpio.write_pin** | ✅ | - | S | Low | Basic digital write with whitelist |
| **gpio.configure_pin** | ✅ | - | M | Medium | Set mode, pull-up/down |
| **gpio.set_pwm** | 🔄 | Enhanced | M | Medium | Basic PWM, limited freq range |
| **PWM frequency validation per model** | ⏭️ | ✅ | S | Medium | Model-specific limits |
| **gpio.get_all_states** | ⚠️ | - | S | Low | Bulk read for monitoring |
| **Event-driven GPIO (edge detection)** | ⏭️ | ✅ | L | High | Async callbacks for pin changes |
| **GPIO state persistence** | ⏭️ | ✅ | M | Medium | Restore states after reboot |

### 3.8 MCP Tools - I2C (Document 08)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **i2c.scan_bus** | ✅ | - | S | Low | Detect devices on bus |
| **i2c.read** | ✅ | - | M | Medium | Read bytes with whitelist |
| **i2c.write** | ✅ | - | M | Medium | Write bytes with whitelist |
| **Address whitelist/blacklist** | ✅ | - | S | Low | Config-driven access control |
| **SMBus protocol helpers** | ⏭️ | ✅ | M | Medium | Read/write word, block operations |
| **I2C device drivers** | ⏭️ | ✅ | L | High | High-level interfaces for common sensors |
| **I2C error recovery** | ⏭️ | ✅ | M | Medium | Bus reset, retry logic |

### 3.9 MCP Tools - Camera (Document 08)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **camera.get_info** | ✅ | - | S | Low | Detect camera, basic capabilities |
| **camera.take_photo** | ✅ | - | M | Medium | Capture JPEG with basic params |
| **Photo resolution/quality params** | 🔄 | Enhanced | S | Low | Basic presets in Phase 1 |
| **Rate limiting (photos/minute)** | ✅ | - | XS | Low | Simple counter-based |
| **camera.record_video** | ⏭️ | ✅ | L | High | H.264 encoding, duration limits |
| **Live streaming** | ⏭️ | ✅ | XL | High | RTSP or WebRTC streaming |
| **Advanced camera controls** | ⏭️ | ✅ | M | Medium | ISO, shutter, white balance, effects |

### 3.10 MCP Tools - SPI & UART (Document 08)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **SPI support** | ⏭️ | ✅ | L | High | Similar to I2C but different protocol |
| **UART/Serial support** | ⏭️ | ✅ | M | Medium | Read/write serial ports |

### 3.11 MCP Tools - Logging & Diagnostics (Document 09)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **logs.get_recent_app_logs** | ✅ | - | M | Medium | Query application logs |
| **logs.get_recent_audit_logs** | ✅ | - | M | Medium | Query audit logs |
| **Time range filtering** | ✅ | - | S | Low | Start/end timestamps |
| **Level filtering** | ✅ | - | XS | Low | Filter by log level |
| **Pagination** | ⚠️ | Enhanced | S | Low | Basic limit/offset |
| **Full-text search in logs** | ⏭️ | ✅ | M | Medium | Keyword search across logs |
| **Log export (download)** | ⏭️ | ✅ | S | Low | Export logs as file |
| **Log shipping integration** | ⏭️ | ✅ | M | Medium | Fluentd, Logstash, etc. |
| **Real-time log streaming** | ⏭️ | ✅ | L | High | WebSocket-based tail -f |

### 3.12 MCP Tools - Management & Updates (Document 10)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **manage.get_server_status** | ✅ | - | M | Medium | Version, uptime, last_update |
| **manage.update_server** | ✅ | - | XL | High | Self-update with state machine |
| **Python package backend** | ✅ | - | L | High | uv/pip-based updates |
| **Version.json management** | ✅ | - | M | Medium | Track current/previous versions |
| **Automatic rollback** | ✅ | - | L | High | Trigger on repeated failures |
| **Manual rollback** | 🔄 | Enhanced | M | Medium | CLI-based in Phase 1 |
| **manage.rollback_server (MCP tool)** | ⏭️ | ✅ | M | Medium | Remote rollback via MCP |
| **Git backend for updates** | ⏭️ | ✅ | L | High | Pull from git repo |
| **Archive backend (tarball)** | ⏭️ | ✅ | M | Medium | Download and extract |
| **APT backend** | ⏭️ | ✅ | L | High | Debian package integration |
| **Update signature verification** | ⏭️ | ✅ | M | High | GPG or similar |
| **Differential updates** | ⏭️ | ✅ | L | High | Delta patches to save bandwidth |
| **Scheduled updates** | ⏭️ | ✅ | M | Medium | Maintenance windows |
| **manage.preview_os_updates** | ⏭️ | ✅ | M | Medium | APT dry-run |
| **manage.apply_os_updates** | ⏭️ | ✅ | L | High | Full OS package updates |

### 3.13 Logging & Observability (Document 09)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **Structured JSON logging** | ✅ | - | M | Medium | All logs in JSON format |
| **Application logs** | ✅ | - | S | Low | General operational logs |
| **Audit logs** | ✅ | - | M | Medium | Security-critical operations |
| **Log rotation (basic)** | ✅ | - | S | Low | File-based or journald |
| **Sensitive data masking** | ✅ | - | S | Medium | Redact secrets in logs |
| **Distributed tracing** | ⏭️ | ✅ | L | High | OpenTelemetry integration |
| **Metrics dashboards** | ⏭️ | ✅ | M | Medium | Grafana templates |
| **Alerting rules** | ⏭️ | ✅ | M | Medium | Alert on thresholds |
| **Log aggregation** | ⏭️ | ✅ | M | Medium | Central log collection |
| **Performance profiling tools** | ⏭️ | ✅ | M | High | CPU/memory profiling |

### 3.14 Testing & Sandbox (Document 11)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **Unit tests (pytest)** | ✅ | - | XL | Medium | Comprehensive coverage |
| **Integration tests** | ✅ | - | L | Medium | Server + agent integration |
| **Sandbox mode (full/partial/disabled)** | ✅ | - | M | Medium | Safe testing of dangerous ops |
| **Test fixtures and mocks** | ✅ | - | M | Medium | GPIO, I2C, systemd mocks |
| **Coverage reporting (≥85%)** | ✅ | - | S | Low | pytest-cov integration |
| **E2E tests on real hardware** | 🔄 | Enhanced | L | Medium | Basic in Phase 1 |
| **Load/stress testing** | ⏭️ | ✅ | M | Medium | Performance benchmarks |
| **Fuzz testing** | ⏭️ | ✅ | M | High | Input fuzzing for robustness |
| **Security scanning** | ⏭️ | ✅ | S | Low | Dependency vulnerability checks |
| **CI/CD pipeline** | ✅ | - | M | Medium | GitHub Actions or similar |

### 3.15 Deployment & Operations (Document 12)

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **Systemd unit files** | ✅ | - | M | Medium | Server + agent services |
| **Installation scripts** | ⚠️ | Enhanced | M | Medium | Basic manual steps in Phase 1 |
| **Cloudflare Tunnel integration** | ✅ | - | M | Medium | Basic setup documented |
| **Configuration templates** | ✅ | - | S | Low | Example config.yml |
| **Operations runbook** | ✅ | - | M | Low | Troubleshooting guide |
| **Backup procedures** | 🔄 | Enhanced | S | Low | Documented in Phase 1, automated in Phase 2+ |
| **Automated provisioning** | ⏭️ | ✅ | L | Medium | Ansible playbooks |
| **Fleet management** | ⏭️ | ✅ | XL | High | Multi-device orchestration |
| **Monitoring dashboards** | ⏭️ | ✅ | M | Medium | Pre-built Grafana dashboards |
| **Disaster recovery automation** | ⏭️ | ✅ | L | High | Automated restore scripts |

### 3.16 Documentation

| Feature | Phase 1 | Phase 2+ | Effort | Complexity | Notes |
|---------|---------|----------|--------|------------|-------|
| **Requirements (Doc 01)** | ✅ | - | - | - | Already complete |
| **Architecture (Doc 02)** | ✅ | - | - | - | Already complete |
| **All design docs (03-14)** | ✅ | - | - | - | Already complete |
| **API reference (auto-generated)** | ⏭️ | ✅ | M | Low | From JSON schemas |
| **User guide** | ⏭️ | ✅ | M | Low | End-user documentation |
| **Developer guide** | ⚠️ | Enhanced | M | Low | Basic in README for Phase 1 |
| **Video tutorials** | ⏭️ | ✅ | L | Low | Setup and usage videos |

---

## 4. Phase 1 Effort Estimation Summary (AI-Assisted Development)

### By Module

| Module | Total Effort (AI) | Risk Level | Dependencies | Key AI Challenges |
|--------|-------------------|------------|--------------|-------------------|
| **Core Infrastructure** | 1.5-2 weeks | High | Foundation for everything | JSON-RPC protocol, IPC design, error handling patterns |
| **Security & Auth** | 1-1.5 weeks | High | Blocks production use | JWT validation, JWKS integration, policy enforcement |
| **System Info & Metrics** | 3-4 days | Medium | Moderate complexity | psutil integration, SQLite queries, background jobs |
| **Service Management** | 2-3 days | Medium | systemd integration | D-Bus/systemd interaction, whitelist logic |
| **Process Management** | 1-2 days | Low | psutil wrapper | Filtering, pagination, data modeling |
| **GPIO/I2C/Camera** | 4-6 days | Medium | Hardware dependencies | Hardware testing iteration, safety validation |
| **Logging & Diagnostics** | 2-3 days | Medium | Pervasive, critical | JSON formatting, masking, query interfaces |
| **Self-Update** | 1-2 weeks | High | Complex state machine | State machine design, rollback safety, systemd restart |
| **Testing** | Ongoing | High | TDD, continuous | Test coverage, mocking hardware, E2E scenarios |
| **Deployment & Docs** | 2-3 days | Medium | Operations enablement | Systemd units, example configs, runbook |

### Overall Phase 1 Estimate (AI-Assisted)

**Total Development Time**: 4-6 weeks of focused AI development with human oversight

**Breakdown**:
- **Week 1-2**: Core infrastructure (MCP server, privileged agent, IPC, config loading)
- **Week 2-3**: Security foundation (OAuth, RBAC, audit logging)
- **Week 3-4**: Basic tools (system info, GPIO, I2C, service/process management)
- **Week 4-5**: Metrics, logging, camera support
- **Week 5-6**: Self-update mechanism and comprehensive testing
- **Week 6+**: Hardware validation, deployment, bug fixes, polish

**Critical Path** (must be sequential):
1. Core infrastructure (MCP server + agent + IPC) → ~1.5 weeks
2. Security & authentication → ~1 week
3. Basic tools (system, GPIO, I2C) → ~1 week
4. Self-update mechanism → ~1.5 weeks
5. E2E testing & validation → ~1 week

**Parallel Development Opportunities**:
- Logging framework can be built alongside core infrastructure
- Tool modules (GPIO, I2C, camera) can be developed in parallel once IPC is ready
- Unit tests written concurrently with implementation
- Documentation updated incrementally

**Human Oversight Requirements**:
- **Daily**: Code reviews, design decisions, clarifications
- **Weekly**: Hardware testing sessions, integration validation
- **Milestone**: Security review, rollback testing, acceptance criteria validation

---

## 5. Phase 1 Success Criteria

### Must Have (Blocking)
- ✅ All ✅-marked features implemented and tested
- ✅ 85%+ test coverage on critical modules
- ✅ All FR-1 through FR-20 satisfied (from Doc 01)
- ✅ Cloudflare OAuth integration working
- ✅ Self-update with rollback proven on real hardware
- ✅ Deployment runbook validated
- ✅ Acceptance checklist passes

### Should Have (Desirable)
- ⚠️ All ⚠️-marked features implemented
- Basic performance benchmarks established
- CI/CD pipeline running all tests
- Example configurations for common scenarios

### Phase 1 Release Gates
1. **Security**: No known high/critical vulnerabilities
2. **Stability**: Self-update tested on 3+ devices without issues
3. **Docs**: All Phase 1 features documented in runbook
4. **Testing**: Acceptance checklist passes on Pi 3, Pi 4, Pi 5
5. **Operations**: At least one successful production deployment

---

## 6. Phase 2+ Prioritization

### High Priority (Phase 2A - ~2-3 months)
- OS update tools (preview + apply)
- Manual rollback MCP tool
- Process signal sending (controlled)
- Advanced metrics (Prometheus export)
- Automated provisioning scripts
- Enhanced PWM with frequency validation

### Medium Priority (Phase 2B - ~2-3 months)
- Configuration hot-reload
- Service dependency validation
- Full-text log search
- Camera video recording
- SPI support
- Performance optimization

### Lower Priority (Phase 3+ - ~3-6 months)
- Fleet management
- Distributed tracing
- mTLS authentication
- I2C device drivers
- Live camera streaming
- Delta updates

---

## 7. Dependency Notes

### External Dependencies
- **Cloudflare Access**: Requires Cloudflare account and setup
- **Hardware**: Raspberry Pi 3+ for testing
- **OS**: Raspberry Pi OS 11+ (Bullseye or newer)
- **Python**: 3.11+ required
- **Tools**: uv, ruff, pytest must be available

### Inter-Module Dependencies
- **Security** → All tools depend on role/policy enforcement
- **Logging** → All modules must use structured logging
- **IPC** → All privileged operations route through agent
- **Config** → All modules consume AppConfig
- **Testing** → Sandbox mode affects all dangerous operations

### Risk Mitigation
- **Self-update complexity**: Allocate extra time, prototype early
- **Cloudflare integration**: Test with multiple IdPs early
- **Hardware availability**: Secure test devices before GPIO/I2C work
- **Systemd integration**: Test on clean Pi OS installs frequently

---

## 8. Scope Management

### How to Use This Matrix

**For Implementation**:
- Focus only on ✅ items
- Implement ⚠️ items if time permits
- Design 🔄 items with Phase 2+ enhancement in mind
- Explicitly skip ⏭️ items (add TODO comments in code)

**For Code Reviews**:
- Reject PRs that add Phase 2+ features without discussion
- Ensure Phase 1 features are complete before moving on
- Check that deferred features have stub/placeholder implementations where needed

**For Planning**:
- Use effort estimates for sprint planning
- Track progress against Phase 1 Must-Haves
- Adjust scope if timeline slips (drop ⚠️ items first)

### Change Control

To **add** a Phase 2+ feature to Phase 1:
1. Document rationale in this file
2. Update effort estimates
3. Adjust timeline
4. Get team consensus

To **defer** a Phase 1 feature to Phase 2+:
1. Ensure no blocking dependencies
2. Update this matrix
3. Update affected design docs
4. Verify success criteria still achievable

---

## 9. Implementation Sequence Recommendation (AI-Assisted)

### Implementation Approach

**Development Model**: AI-first development with iterative human review
- AI implements features following design documents
- Human reviews, tests on hardware, provides feedback
- Iterate until feature meets acceptance criteria
- Move to next feature in sequence

### Week 1: Foundation & Core Infrastructure (Days 1-7)

**Day 1-2: Project Setup & Foundation**
- Initialize repo structure (`src/mcp_raspi/`, `src/mcp_raspi_ops/`, `tests/`)
- Setup `pyproject.toml` with `uv`, dependencies (Pydantic, pytest, ruff)
- Configure CI/CD (GitHub Actions for lint, test, coverage)
- Create core Pydantic models: `AppConfig`, `ToolContext`, `ToolError`
- Implement configuration loading (YAML + env vars + CLI args)
- **Deliverable**: Runnable project skeleton with config loading + tests

**Day 3-5: MCP Server Core**
- Implement JSON-RPC over stdio handler
- Create basic request routing framework
- Implement `ToolError` → JSON-RPC error mapping
- Add structured logging framework (JSON logs)
- Create first dummy tool (`system.get_basic_info` stub)
- **Deliverable**: MCP server can receive requests, route to handlers, return responses

**Day 6-7: Privileged Agent & IPC**
- Implement privileged agent skeleton (`mcp_raspi_ops`)
- Create Unix socket IPC server in agent
- Create IPC client (`OpsAgentClient`) in MCP server
- Implement request/response protocol (JSON over socket)
- Add basic error propagation
- **Deliverable**: MCP server ↔ agent IPC working with test command

### Week 2: Security & Basic Tools (Days 8-14)

**Day 8-10: Security Foundation**
- Implement `ToolContext` extraction from MCP protocol
- Add Cloudflare Access JWT validation (with mock for testing)
- Implement RBAC (viewer, operator, admin roles)
- Create policy enforcement layer
- Add audit logging (`AuditLogger` with structured fields)
- Implement local auth mode for development
- **Deliverable**: All tools check roles, audit logs record privileged ops

**Day 11-12: System Information Tools**
- `system.get_basic_info`: hostname, model, OS, kernel (via Python stdlib)
- `system.get_health_snapshot`: CPU, memory, disk, temp (via `psutil`)
- Add temperature reading from `/sys/class/thermal/thermal_zone*/temp`
- Implement network info (basic: IPs, interfaces)
- **Deliverable**: System info tools working with comprehensive tests

**Day 13-14: Power Management Tools**
- `system.reboot` with safety checks and confirmation
- `system.shutdown` with safety checks
- Integrate with privileged agent for actual reboot/shutdown
- Add sandbox mode handling (full/partial/disabled)
- Implement rate limiting for power operations
- **Deliverable**: Reboot/shutdown working in sandbox and real modes

### Week 3: Device Control & Services (Days 15-21)

**Day 15-17: GPIO Tools**
- `gpio.read_pin`: digital read with BCM pin numbering
- `gpio.write_pin`: digital write with whitelist enforcement
- `gpio.configure_pin`: mode, pull-up/down
- `gpio.set_pwm`: basic PWM (fixed frequency initially)
- `gpio.get_all_states`: bulk state reading
- Implement via privileged agent using `gpiozero`
- **Deliverable**: GPIO control working on test hardware

**Day 18-19: I2C Tools**
- `i2c.scan_bus`: detect devices on bus
- `i2c.read`: read bytes with address whitelist
- `i2c.write`: write bytes with address whitelist
- Implement via privileged agent using `smbus2`
- Add whitelist/blacklist configuration
- **Deliverable**: I2C operations working on test hardware

**Day 20-21: Service & Process Management**
- `service.list_services`: query systemd via D-Bus
- `service.get_status`: single service status
- `service.control_service`: start/stop/restart with whitelist
- `service.set_enabled`: enable/disable autostart
- `process.list_processes`: via `psutil` with filtering
- `process.get_info`: detailed process info
- **Deliverable**: Service/process tools working with whitelist enforcement

### Week 4: Metrics, Logging & Camera (Days 22-28)

**Day 22-24: Metrics Module**
- Design SQLite schema for metrics storage
- `metrics.start_sampling`: background job with `asyncio`
- `metrics.stop_sampling`: gracefully stop sampling
- `metrics.get_status`: return sampling state
- `metrics.query`: time range queries with basic aggregation
- Implement retention policy (delete old data)
- **Deliverable**: Metrics sampling and querying working

**Day 25-26: Logging Tools**
- `logs.get_recent_app_logs`: query application logs
- `logs.get_recent_audit_logs`: query audit logs
- Implement time range filtering, level filtering, pagination
- Add log rotation (file-based or journald)
- Implement sensitive data masking
- **Deliverable**: Log query tools working

**Day 27-28: Camera Support**
- `camera.get_info`: detect camera, capabilities
- `camera.take_photo`: capture JPEG with basic params
- Implement via privileged agent using `picamera2`
- Add rate limiting (photos/minute)
- Store photos in configured media directory
- **Deliverable**: Camera capture working on test hardware

### Week 5-6: Self-Update & Final Integration (Days 29-42)

**Day 29-32: Self-Update Foundation**
- Design `version.json` structure
- `manage.get_server_status`: version, uptime, last_update
- Implement version directory layout (`/opt/mcp-raspi/releases/`)
- Create `UpdateBackend` abstraction
- Implement `PythonPackageBackend` (uv/pip based)
- **Deliverable**: Version management working

**Day 33-37: Self-Update State Machine**
- `manage.update_server`: implement state machine
  - States: idle, checking, preparing, switching, verifying, succeeded/failed
- Implement atomic symlink switching (`current` → new version)
- Add systemd service restart integration
- Implement automatic rollback on repeated failures
- Add extensive state machine testing
- **Deliverable**: Self-update with rollback working on test device

**Day 38-40: Deployment & Integration**
- Create systemd unit files (`mcp-raspi-server.service`, `raspi-ops-agent.service`)
- Write installation documentation
- Create example configurations (`config.example.yml`)
- Document Cloudflare Tunnel setup
- Write operations runbook (troubleshooting, common issues)
- **Deliverable**: Deployment documentation complete

**Day 41-42: Final Testing & Polish**
- Run full acceptance checklist (see `docs/acceptance-checklist.md`)
- Test on multiple Pi models (Pi 3, Pi 4, Pi 5)
- Fix discovered bugs
- Ensure 85%+ test coverage
- Validate security controls
- **Deliverable**: Phase 1 release candidate ready

### Post-Implementation (As Needed)

**Hardware Validation Sessions** (iterative, throughout):
- Test GPIO operations on real hardware
- Test I2C with actual sensors
- Test camera capture with various settings
- Test self-update on clean OS install
- Test reboot/shutdown and recovery

**Documentation Updates** (continuous):
- Update README with getting started guide
- Add inline code documentation
- Generate API reference from JSON schemas
- Update runbook with discovered issues

---

## 10. AI Implementation Guidelines

### How AI Should Use This Document

**Before starting any feature**:
1. ✅ Check this matrix to confirm feature is Phase 1
2. 📖 Read the relevant design document(s) for detailed specifications
3. 🎯 Understand the effort estimate and complexity level
4. 🔗 Identify dependencies (what must be built first)

**During implementation**:
- Follow the implementation sequence (Section 9)
- Write tests alongside code (TDD approach)
- Use Pydantic models from design docs for data structures
- Follow JSON schemas from Doc 05 for tool interfaces
- Add docstrings and inline comments for complex logic

**When user requests out-of-scope features**:
```
"That feature [X] is marked as Phase 2+ in the scope matrix.
It's not planned for Phase 1 to keep the initial release focused.
Would you like me to:
1. Add it to Phase 1 (requires updating scope + timeline)
2. Defer it to Phase 2+ as planned
3. Implement a simplified version for Phase 1?"
```

### Design Document Quick Reference

| When implementing... | Read these documents... | Key sections |
|---------------------|------------------------|--------------|
| **Project setup, config** | Doc 02, 13, 14 | Architecture, Python standards, config reference |
| **MCP server core** | Doc 02, 05 | §5 (MCP protocol), §2-3 (JSON schemas, error codes) |
| **Security/auth** | Doc 04, 05 | Complete security design, ToolContext |
| **System info tools** | Doc 05, 06 | §3 (system namespace), system info module |
| **Metrics** | Doc 05, 06, 09 | §4 (metrics namespace), metrics module, logging |
| **Service management** | Doc 05, 07 | §5 (service namespace), service module |
| **Process management** | Doc 05, 07 | §6 (process namespace), process module |
| **GPIO/I2C/Camera** | Doc 05, 08 | §7 (device namespaces), device control module |
| **Logging/diagnostics** | Doc 05, 09 | §9 (logs namespace), logging module |
| **Self-update** | Doc 05, 10 | §8 (manage namespace), complete self-update design |
| **Testing** | Doc 11 | Complete testing strategy, sandbox modes |
| **Deployment** | Doc 12 | Systemd integration, operations runbook |

### Code Quality Standards for AI

**Every feature must include**:
- ✅ Implementation following design docs
- ✅ Unit tests with 85%+ coverage
- ✅ Integration tests for cross-module features
- ✅ Docstrings for public functions/classes
- ✅ Type hints on all public interfaces
- ✅ Error handling with `ToolError`
- ✅ Audit logging for privileged operations
- ✅ Configuration via `AppConfig`

**Code review checklist** (for human reviewer):
- [ ] Matches design document specifications
- [ ] All tests pass (`uv run pytest`)
- [ ] Linting passes (`uv run ruff check`)
- [ ] Coverage meets target (`uv run pytest --cov`)
- [ ] Security considerations addressed
- [ ] No Phase 2+ features added without approval
- [ ] Hardware-specific code has sandbox mode handling

### Iteration & Feedback Loop

**Typical AI development cycle**:
1. **AI**: Implement feature + tests following docs
2. **Human**: Review code, test on hardware (if applicable)
3. **Human**: Provide feedback/corrections
4. **AI**: Iterate based on feedback
5. **Repeat** until acceptance criteria met
6. **Human**: Approve and merge

**Expected iterations per feature**:
- XS/S features: 1-2 iterations
- M features: 2-3 iterations
- L features: 3-4 iterations
- XL features: 4-6 iterations

Hardware testing adds 1-2 extra iterations for GPIO/I2C/Camera features.

---

## 11. References

### Design Documents
- **Doc 01**: Requirements Specification (all FRs mapped to phases)
- **Doc 02**: High-Level Architecture Design (system structure, IPC, config)
- **Doc 03**: Platform & Resource Constraints (Raspberry Pi specifics)
- **Doc 04**: Security, OAuth Integration & Access Control (complete security model)
- **Doc 05**: MCP Tools Interface & JSON Schema Specification (all tool interfaces)
- **Doc 06**: System Information & Metrics Module Design
- **Doc 07**: Service & Process Management Module Design
- **Doc 08**: Device Control & Reboot/Shutdown Safeguards Design
- **Doc 09**: Logging, Observability & Diagnostics Design
- **Doc 10**: Self-Update Mechanism & Rollback Strategy Design
- **Doc 11**: Testing, Validation & Sandbox Strategy
- **Doc 12**: Deployment, Systemd Integration & Operations Runbook
- **Doc 13**: Python Development Standards & Tools
- **Doc 14**: Configuration Reference & Examples

### Supporting Documents
- **Acceptance Checklist**: Phase 1 release criteria (`docs/acceptance-checklist.md`)
- **Test Matrix**: Device/environment test coverage (`docs/test-matrix.md`)

### External References
- **MCP Specification**: https://spec.modelcontextprotocol.io/
- **Raspberry Pi Documentation**: https://www.raspberrypi.com/documentation/
- **Python 3.11 Docs**: https://docs.python.org/3.11/

---

**Document Version**: 1.0
**Last Updated**: 2025-12-03
**Optimized For**: AI-assisted development workflows
**Owner**: Implementation Team Lead
**Review Cycle**: Update at end of each sprint or when scope changes
