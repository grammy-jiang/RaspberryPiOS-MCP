# Executive Summary – Raspberry Pi MCP Server

## Project Overview

The **Raspberry Pi MCP Server** is a secure, remotely manageable system that enables safe monitoring and control of Raspberry Pi devices through the Model Context Protocol (MCP). It allows AI assistants (like Claude, ChatGPT) and other clients to interact with Raspberry Pi hardware and system resources through a well-defined, secure API.

**Target Use Cases**:
- Remote IoT device management and monitoring
- Home automation and smart device control
- Educational robotics and maker projects
- Remote lab equipment management
- Edge computing device orchestration

## Key Design Principles

1. **Security First**: OAuth/Cloudflare Access integration, role-based access control, audit logging
2. **Safety by Design**: Whitelists, rate limits, sandbox modes, explicit user consent for dangerous operations
3. **Minimal Privilege**: Separate privileged agent, constrained IPC, non-privileged MCP server
4. **Self-Maintaining**: Automated self-update with rollback, comprehensive diagnostics
5. **Resource Conscious**: Optimized for 1GB RAM, microSD storage, unreliable networks

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                    Internet (Cloudflare)                    │
│              ┌──────────────────────────────┐               │
│              │  Cloudflare Tunnel + Access  │               │
│              │       (OAuth/OIDC)           │               │
│              └──────────────┬───────────────┘               │
└─────────────────────────────┼─────────────────────────────┘
                              │
┌─────────────────────────────┼─────────────────────────────┐
│          Raspberry Pi OS    │                              │
│                             ▼                              │
│  ┌────────────────────────────────────────────┐           │
│  │  mcp-raspi-server (Non-privileged)         │           │
│  │  - JSON-RPC over stdio                     │           │
│  │  - Tool routing & auth                     │           │
│  │  - Configuration & logging                 │           │
│  └─────────────────┬──────────────────────────┘           │
│                    │ IPC (Unix socket)                     │
│                    ▼                                       │
│  ┌────────────────────────────────────────────┐           │
│  │  raspi-ops-agent (Privileged, root)        │           │
│  │  - GPIO/I2C/Camera control                 │           │
│  │  - Service/process management              │           │
│  │  - Reboot/shutdown/updates                 │           │
│  └────────────────────────────────────────────┘           │
│                                                             │
└─────────────────────────────────────────────────────────┘
```

## Core Capabilities (Phase 1)

### System Monitoring & Diagnostics
- **System info**: hostname, model, OS, kernel, hardware details
- **Health metrics**: CPU, memory, disk, temperature, network stats
- **Time-series metrics**: SQLite-backed sampling with queries
- **Logs**: Query application and audit logs with filtering

### Device Control
- **GPIO**: Read/write pins, PWM, with pin whitelists
- **I2C**: Scan bus, read/write devices with address filtering
- **Camera**: Capture photos with rate limiting

### System Management
- **Services**: List, status, start/stop/restart systemd services (whitelist-controlled)
- **Processes**: List, filter, get detailed process information
- **Power**: Reboot/shutdown with safety checks and confirmations

### Self-Update & Rollback
- **Remote updates**: Fetch and install new server versions via MCP
- **Automatic rollback**: Restore previous version on repeated failures
- **Version management**: Track current and previous good versions

### Security & Access Control
- **Authentication**: Cloudflare Access JWT validation, local dev mode
- **Authorization**: Role-based (viewer, operator, admin) with per-tool policies
- **Audit logging**: All privileged operations logged with caller identity

## Technology Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.11+ |
| **MCP Protocol** | JSON-RPC 2.0 over stdio |
| **IPC** | Unix domain sockets (JSON) |
| **Configuration** | YAML + Pydantic with env var overrides |
| **Hardware** | gpiozero, smbus2, picamera2 |
| **System** | psutil, dbus-next, systemd |
| **Storage** | SQLite (metrics), file-based (logs) |
| **Auth** | PyJWT, Cloudflare Access |
| **Deployment** | systemd services, uv package manager |
| **Testing** | pytest, pytest-asyncio, pytest-cov |
| **Linting** | ruff, mypy |

## Security Model

### Threat Model
- **Trusted**: Device owner, authorized AI assistants with valid OAuth tokens
- **Untrusted**: Internet, unauthorized users, malicious clients
- **Boundary**: Cloudflare Tunnel + Access, role-based authorization

### Defense Layers
1. **Network**: Cloudflare Tunnel (no direct device exposure)
2. **Authentication**: OAuth/OIDC via Cloudflare Access
3. **Authorization**: Role-based access control (RBAC)
4. **Tool-level**: Whitelists (GPIO pins, I2C addresses, services)
5. **Rate limiting**: Prevent abuse of dangerous operations
6. **Audit**: All privileged operations logged immutably
7. **Privilege separation**: Non-privileged server + constrained privileged agent

### Roles & Permissions
- **viewer**: Read-only operations (system info, metrics, logs)
- **operator**: Safe control operations (start/stop whitelisted services, read GPIO)
- **admin**: All operations including reboot, shutdown, self-update, GPIO writes

## Configuration System

**Layered configuration** (later layers override earlier):
1. Built-in defaults (safe, localhost-only)
2. YAML file (`/etc/mcp-raspi/config.yml`)
3. Environment variables (`MCP_RASPI_*`)
4. CLI arguments (`--config`, `--log-level`, `--debug`)

**Key configuration sections**:
- `server`: Listen address, log level
- `security`: Auth mode, roles, OAuth settings
- `tools`: Enable/disable tool namespaces
- `gpio`/`i2c`/`camera`: Whitelists and constraints
- `updates`: Self-update backend and policies
- `testing`: Sandbox mode for safe testing

## Development Timeline (AI-Assisted)

**Phase 1 Duration**: 4-6 weeks of focused AI development with human oversight

| Week | Focus | Deliverables |
|------|-------|--------------|
| **1** | Core Infrastructure | MCP server, privileged agent, IPC, config loading |
| **2** | Security & System Tools | Auth, RBAC, system info, reboot/shutdown |
| **3** | Device Control | GPIO, I2C, service/process management |
| **4** | Metrics & Logging | SQLite metrics, log queries, camera |
| **5-6** | Self-Update & Polish | Version management, rollback, testing, deployment |

**Phase 2+ Features** (deferred):
- OS package updates (APT integration)
- Advanced metrics (Prometheus export)
- Video recording, live streaming
- SPI/UART support
- Fleet management
- Configuration hot-reload
- Enhanced PWM controls

## Documentation Structure

### Design Documents (Implementation-Ready)
1. **Requirements** – Goals, scope, functional/non-functional requirements
2. **Architecture** – System structure, components, data flows
3. **Platform** – Raspberry Pi specifics, resource constraints
4. **Security** – Auth, access control, threat model
5. **MCP Tools** – Complete tool interface specifications
6. **System & Metrics** – System info and metrics module
7. **Service & Process** – Service/process management
8. **Device Control** – GPIO/I2C/camera + safety
9. **Logging** – Structured logging, audit, diagnostics
10. **Self-Update** – Update mechanism, rollback strategy
11. **Testing** – TDD strategy, coverage, sandbox
12. **Deployment** – Systemd, operations runbook
13. **Python Standards** – Code style, tooling, dev workflow
14. **Configuration** – Complete config reference

### Supporting Documents
- **Phase 1 Scope Matrix** – AI-optimized feature breakdown and timeline
- **Document Navigator** – Reading order and dependencies
- **Quick Start Guide** – Get started in 10 minutes
- **Test Matrix** – Device/environment test coverage
- **Acceptance Checklist** – Pre-release validation

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| **Security breach** | OAuth, RBAC, audit logging, privilege separation |
| **Dangerous operations** | Whitelists, rate limits, confirmation prompts, sandbox mode |
| **Failed updates** | Automatic rollback, version.json tracking, previous good version |
| **Resource exhaustion** | Rate limits, disk space checks, metrics retention policies |
| **Network failure** | Graceful degradation, local SSH access, offline operation |
| **Hardware damage** | GPIO whitelists, I2C address filtering, PWM limits |

## Success Criteria (Phase 1)

**Must Have**:
- ✅ All core features implemented and tested (85%+ coverage)
- ✅ Cloudflare OAuth integration working
- ✅ Self-update with rollback proven on real hardware
- ✅ Acceptance checklist passes on Pi 3, Pi 4, Pi 5
- ✅ No known high/critical security vulnerabilities
- ✅ Deployment runbook validated

**Deployment Readiness**:
- Systemd units tested and documented
- Example configurations provided
- Operations runbook covers common issues
- At least one successful production deployment

## Getting Started (For Implementers)

### For AI Assistants
1. Read [`docs/phase-1-scope-matrix.md`](phase-1-scope-matrix.md) – Your implementation guide
2. Follow the day-by-day sequence in Section 9
3. Reference design docs (01-14) for detailed specifications
4. Implement with TDD: write tests alongside code
5. Follow Python standards (Doc 13): ruff, pytest, type hints

### For Human Developers
1. Review this executive summary for context
2. Read [`docs/document-navigator.md`](document-navigator.md) for reading order
3. Deep-dive into relevant design docs (01-14)
4. Set up development environment (Doc 13)
5. Follow acceptance checklist for validation

### For Operations
1. Read deployment guide (Doc 12)
2. Follow installation procedures
3. Configure Cloudflare Tunnel (if internet-exposed)
4. Validate with acceptance checklist (Doc: acceptance-checklist.md)
5. Monitor logs and metrics

## Key Differentiators

1. **AI-First Design**: Built to be safely controlled by AI assistants
2. **Security-Focused**: Defense-in-depth with OAuth, RBAC, audit, privilege separation
3. **Self-Updating**: Remote updates with automatic rollback
4. **Resource-Efficient**: Optimized for constrained Raspberry Pi hardware
5. **Well-Documented**: 14 comprehensive design documents + supporting materials
6. **Test-Driven**: 85%+ coverage target, sandbox testing, acceptance checklist
7. **Operations-Ready**: Systemd integration, runbook, diagnostics

## Project Status

**Current**: Design and documentation phase complete (100%)
- All 14 design documents finalized
- Phase 1 scope matrix with AI-optimized timeline
- Test matrix and acceptance criteria defined

**Next**: Implementation Phase 1 (4-6 weeks estimated)
- AI-assisted development following scope matrix
- TDD with comprehensive test coverage
- Hardware validation on real Raspberry Pi devices

**Future**: Phase 2+ enhancements
- OS updates, Prometheus metrics, fleet management
- Advanced device controls, video streaming
- Performance optimizations

---

## Quick Links

- **Start Here**: [`phase-1-scope-matrix.md`](phase-1-scope-matrix.md) – AI implementation guide
- **Navigate Docs**: [`document-navigator.md`](document-navigator.md) – Reading order
- **Quick Start**: [`quick-start-guide.md`](quick-start-guide.md) – Setup in 10 minutes
- **Full Design**: Documents 01-14 in `docs/` directory
- **MCP Spec**: https://spec.modelcontextprotocol.io/

---

**Document Version**: 1.0
**Last Updated**: 2025-12-03
**Audience**: Decision makers, new team members, stakeholders
**Reading Time**: 5-7 minutes
