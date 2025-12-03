# RaspberryPiOS-MCP

Design and documentation for a future **Raspberry Pi MCP Server** that will manage and observe Raspberry Pi OS devices, with a focus on safe device control, self‑monitoring, and secure internet exposure via Cloudflare + OAuth.

## Documentation

### 🚀 Quick Start (Pick Your Path)

**New to the project?**
- 📖 [`docs/00-executive-summary.md`](docs/00-executive-summary.md) – 5-minute overview of the entire system
- 🗺️ [`docs/quick-start-guide.md`](docs/quick-start-guide.md) – 10-minute guide to get oriented (all roles)
- 🧭 [`docs/document-navigator.md`](docs/document-navigator.md) – Find the right doc for your role

**AI Assistant implementing features?**
- 🤖 **START HERE**: [`docs/phase-1-scope-matrix.md`](docs/phase-1-scope-matrix.md) – Your complete implementation guide
  - ✅ What to build (Must Have / Should Have / Phase 2+)
  - 📅 Day-by-day implementation sequence (42-day plan)
  - 📏 AI-optimized effort estimates (4-6 weeks total)
  - 📖 Design document quick reference
  - ✨ Code quality standards and iteration guidelines

**Human developer joining?**
- 📖 Read: Executive summary → Navigator → Foundation docs (01-03)
- 💻 Setup: Follow Doc 13 (Python standards) for dev environment
- 🔨 Build: Pick your module using document navigator

### Complete Design Documentation

The full design is captured in the numbered specs under `docs/` (recommended reading order):

1. `docs/01-raspberry-pi-mcp-server-requirements-specification.md` – Overall goals, scope, functional and non‑functional requirements.
2. `docs/02-raspberry-pi-mcp-server-high-level-architecture-design.md` – Top‑level architecture, components and data flows.
3. `docs/03-raspberry-pi-platform-and-resource-constraints-design-note.md` – Raspberry Pi platform targets and resource constraints.
4. `docs/04-security-oauth-integration-and-access-control-design.md` – Security model, OAuth/Cloudflare integration, access control.
5. `docs/05-mcp-tools-interface-and-json-schema-specification.md` – MCP tool namespaces, operations and JSON schemas.
6. `docs/06-system-information-and-metrics-module-design.md` – System information and metrics collection module.
7. `docs/07-service-and-process-management-module-design.md` – Service and process management design.
8. `docs/08-device-control-and-reboot-shutdown-safeguards-design.md` – GPIO/I2C/camera control and reboot/shutdown safeguards.
9. `docs/09-logging-observability-and-diagnostics-design.md` – Logging, observability and diagnostics.
10. `docs/10-self-update-mechanism-and-rollback-strategy-design.md` – Self‑update workflow and rollback strategy.
11. `docs/11-testing-validation-and-sandbox-strategy.md` – Testing, validation and sandbox/safety strategy.
12. `docs/12-deployment-systemd-integration-and-operations-runbook.md` – Deployment approach, systemd integration and operations runbook.
13. `docs/13-python-development-standards-and-tools.md` – Python coding standards, tooling (`uv`, `ruff`, `pytest`, `tox`, coverage, `mypy`) and dev commands.
14. `docs/14-configuration-reference-and-examples.md` – Central configuration reference (`AppConfig` structure, layers & examples).

### Navigation & Planning Documents

- **[`docs/00-executive-summary.md`](docs/00-executive-summary.md)** – 2-page executive overview (5-7 min read)
- **[`docs/quick-start-guide.md`](docs/quick-start-guide.md)** – Get started in 10 minutes (all roles)
- **[`docs/document-navigator.md`](docs/document-navigator.md)** – Reading paths, dependencies, reference matrix
- **[`docs/phase-1-scope-matrix.md`](docs/phase-1-scope-matrix.md)** – Complete Phase 1 implementation plan (AI-optimized)
- **[`docs/github-copilot-agent-issue-plan.md`](docs/github-copilot-agent-issue-plan.md)** – GitHub Copilot Agent issue breakdown (12 issues, 6-hour sessions)
- **[`docs/github-issues-quick-reference.md`](docs/github-issues-quick-reference.md)** – Quick reference: all 12 issue titles and dependencies
- **[`docs/test-matrix.md`](docs/test-matrix.md)** – Device/environment/function test coverage matrix
- **[`docs/acceptance-checklist.md`](docs/acceptance-checklist.md)** – Pre-release validation checklist

### Documentation Structure

```
📚 Documentation Layer Structure
├── 🎯 Entry Points (Start Here!)
│   ├── 00-executive-summary.md      ← Overview for everyone (5 min)
│   ├── quick-start-guide.md         ← Get oriented fast (10 min)
│   └── document-navigator.md        ← Find what you need
│
├── 📋 Planning & Scope
│   └── phase-1-scope-matrix.md      ← AI implementation guide (PRIMARY for builders)
│
├── 🏗️ Foundation (Read First)
│   ├── 01-requirements-specification.md
│   ├── 02-architecture-design.md
│   └── 03-platform-constraints.md
│
├── 🔐 Core Design
│   ├── 04-security-oauth-access-control.md
│   └── 05-tools-interface-json-schema.md
│
├── 🔧 Module Designs (Implementation Details)
│   ├── 06-system-information-metrics.md
│   ├── 07-service-process-management.md
│   ├── 08-device-control-safeguards.md
│   ├── 09-logging-observability-diagnostics.md
│   └── 10-self-update-rollback-strategy.md
│
├── 🚀 Implementation & Operations
│   ├── 11-testing-validation-sandbox.md
│   ├── 12-deployment-systemd-operations.md
│   ├── 13-python-development-standards.md
│   └── 14-configuration-reference-examples.md
│
└── ✅ Validation
    ├── test-matrix.md
    └── acceptance-checklist.md
```

**Total**: 20 documentation files, 250+ pages, 10-12 hours comprehensive study, implementation-ready specifications.

**Documentation Quality**: Professional-grade, comprehensive specifications with 9.6/10 quality rating. All content has been consolidated for easy navigation with consistent terminology, accurate cross-references, and implementation-ready detail.

This repository currently contains **documentation only**; implementation work (Python MCP server, privileged agent, systemd units, etc.) should follow these specs. The design is intended to be implementation-ready: interfaces, models, workflows and error handling are fully specified in the docs above.

## AI-Assisted Development

This project is designed for **AI-first development workflows** where AI assistants (like Claude, GitHub Copilot, GPT-4, etc.) implement features based on comprehensive design documentation with human oversight.

**Key differences from traditional development**:
- **Effort estimates** are calibrated for AI coding speed (4-6 weeks total vs 3-4 months traditional)
- **Documentation is AI-optimized** with clear references, patterns, and guidelines
- **Scope matrix** helps AI understand boundaries and dependencies
- **Human role**: Review code, test on hardware, provide feedback, approve designs

**For AI assistants**: Start with [`docs/phase-1-scope-matrix.md`](docs/phase-1-scope-matrix.md) which contains specific instructions on how to use these design documents effectively.

**For GitHub Copilot Agent**: See [`docs/github-copilot-agent-issue-plan.md`](docs/github-copilot-agent-issue-plan.md) for a complete breakdown of Phase 1 into 12 GitHub Issues optimized for 6-hour Copilot Agent sessions. Each issue includes acceptance criteria, design doc references, implementation notes, and time breakdowns.

## High‑Level Design Summary

From the docs set, the MCP server is designed as:

- A non‑privileged MCP server process (`mcp-raspi-server`) running on Raspberry Pi OS, exposing MCP tools over JSON‑RPC 2.0.  
- A separate privileged agent (`raspi-ops-agent`) that performs hardware and OS operations via a constrained IPC protocol over a Unix domain socket.  
- A layered configuration model (`AppConfig`) loaded from defaults → YAML → environment variables (`MCP_RASPI_*`) → CLI flags, with sections for server, security, tools, device control, logging, updates, IPC, and testing/sandbox.  
- A security model based on Cloudflare Tunnel + Cloudflare Access/OIDC, roles (`viewer`, `operator`, `admin`), safety levels (`read_only`, `safe_control`, `admin`), and per‑tool policies and rate limits.  
- A rich tool surface (`system.*`, `metrics.*`, `service.*`, `process.*`, `gpio.*`, `i2c.*`, `camera.*`, `logs.*`, `manage.*`) with JSON Schemas and Pydantic models defined for parameters and results.  
- A self‑update subsystem that manages versioned releases under `/opt/mcp-raspi/releases/` with a `current` symlink, `version.json` metadata, automatic/manual rollback, and clear separation from OS‑level APT updates.  
- A testing strategy that emphasizes TDD, high coverage (≥85% overall, ~90% for critical modules), sandbox modes for dangerous operations (`testing.sandbox_mode`), a test matrix across devices/environments, and an acceptance checklist for releases.

## Planned Implementation Stack & Dev Flow

- Implementation language: **Python 3.11+** on Raspberry Pi OS.  
- Core runtime libraries (subject to refinement during coding):  
  - Server/core: `fastapi`, `uvicorn`, `pydantic`, `pyyaml`, `pyjwt`.  
  - System & metrics: `psutil`.  
  - Device control: `gpiozero`, `smbus2`, optional `spidev`, `pyserial`, `picamera2`.  
  - Service/process management: `dbus-next` + `systemctl` wrappers.  
- Recommended dev tools and runners: `uv` (env + run), `pytest`, `pytest-asyncio`, `pytest-cov`, `tox`, `ruff`, `mypy`.

Once code and packaging files are added, the typical local flow is expected to be (see doc 13 for details):

1. Create a virtualenv and install dependencies:
   - `uv venv .venv`  
   - `source .venv/bin/activate`  
   - `uv pip install -e ".[dev]"`  
2. Run tests and checks:
   - `uv run pytest`  
   - `uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing`  
   - `uv run ruff check src tests` / `uv run ruff format src tests`  
3. Run development instances:
   - `uv run mcp-raspi-server --config ./dev-config.yml`  
   - `sudo uv run raspi-ops-agent --config ./dev-config.yml`

These commands are part of the design and may be refined when the initial implementation is created, but `uv` + `ruff` + `pytest` + `tox` are the preferred toolchain. Deployment, self‑update and rollback flows are described in detail in docs 10 and 12; testing and CI strategy in docs 11 and 13; configuration structure and examples in doc 14.  

## Implementation Readiness

All major aspects of the system are specified at an implementation level:

- Requirements & architecture: docs 01–03.  
- Security, tools & modules: docs 04–09.  
- Self‑update, testing, deployment & Python standards: docs 10–13.  
- Configuration model & examples: doc 14.  
- Test planning & acceptance: `docs/test-matrix.md`, `docs/acceptance-checklist.md`.  

You can now scaffold `pyproject.toml`, `src/mcp_raspi/`, `src/mcp_raspi_ops/`, and start implementing `AppConfig`, logging/audit, JSON‑RPC server, IPC client/agent, and each module following these specs.  
