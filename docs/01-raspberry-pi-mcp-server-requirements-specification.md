# 01. Raspberry Pi MCP Server – Requirements Specification

## 1. Document Purpose

- Define the goals, scope, and constraints of the Raspberry Pi MCP Server and provide a shared baseline for architecture and implementation.  
- Describe functional and non‑functional requirements, clearly distinguishing **Phase 1 (Minimum Viable Product)** from **Phase 2+ (future extensions)**.  
- Serve as the requirements source for all other design documents (02–14).

## 2. Scope

### 2.1 In Scope

- Provide an MCP server for Raspberry Pi devices running **Raspberry Pi OS**, acting as:  
  - A device self‑control interface (system and hardware control on the same Pi).  
  - A self‑metrics and health monitoring interface (system information and metrics of the same Pi).  
- Deploy the MCP server on the managed Raspberry Pi device itself, accessible via:  
  - Local network (LAN/Wi‑Fi).  
  - The public internet through Cloudflare Tunnel, with access control via OAuth/OIDC (Cloudflare Access).  
- Primary clients:  
  - AI models (e.g., ChatGPT) using MCP tools.  
  - Other MCP‑compatible services or automation scripts.

### 2.2 Out of Scope (Phase 1)

- Direct control of other devices on the LAN (anything other than the local Pi).  
- Complex business‑level orchestration (e.g., a full home automation platform).  
- Graphical UI or mobile apps – Phase 1 only exposes an MCP interface.  
- General support for all Linux distributions – Phase 1 targets Raspberry Pi OS only.

## 3. Stakeholders

- **Device owner / operator** – wants to manage and monitor the Pi remotely via natural language or automation.  
- **AI clients (ChatGPT, etc.)** – execute controlled system operations via MCP tools.  
- **System developers** – implement and extend the MCP server and its modules.  
- **Security / compliance owners** – care about public exposure, access control, audit logging, and compliance.

## 4. Use Cases

### 4.1 Device Self‑Control

- Remotely control GPIO (e.g., switch relays, LEDs, fans).  
- Control I2C/SPI devices (e.g., read sensors, perform simple writes).  
- Control the camera to take photos or short videos.  
- Initiate safe reboot operations, and shutdown when necessary (with stronger safeguards).  
- Start/stop/query specific system services (systemd) and processes via the service/process management module.

### 4.2 Self‑Monitoring & Data Collection

- Retrieve current system information:  
  - Raspberry Pi model, CPU, memory, storage, OS version, etc.  
- Retrieve runtime metrics:  
  - CPU utilization, memory usage, disk usage, network throughput, CPU temperature, throttling status, etc.  
- Periodically sample and persist metrics for trend analysis and health evaluation.  
- Query recent metric samples to assist AI in diagnostics and tuning suggestions.

### 4.3 Remote Management & Operations

- Remotely trigger **self‑update** of the MCP server (fetch a new version and restart safely).  
- Remotely view MCP server version, configuration summary, and health status.  
- Remotely trigger safe system reboot of the Pi.  
- View system and service logs to help with troubleshooting (basic capabilities in Phase 1, with more advanced filtering/analysis in later phases).

### 4.4 Example User Stories

- As a home server owner, I want to type “show me the status of my Pi” into ChatGPT so that the AI returns CPU/memory/disk usage and whether the device is overheating.  
- As a developer, I want to say “collect metrics every 10 seconds and keep them for one day” and have the AI create a sampling job and export the data when needed.  
- As an operator, when a service misbehaves, I want the AI to “restart the nginx service and check if it recovered”, and have the entire process auditable.  
- As a security owner, I want any reboot, shutdown, or OS update operation to be triggerable only by OAuth‑authenticated users with an admin role.

## 5. Functional Requirements

This section uses identifiers `FR‑x` to denote functional requirements.

### 5.1 System Information & Metrics

- **FR‑1** – The system MUST provide MCP tools to obtain basic system information (model, OS, kernel, uptime, etc.).  
- **FR‑2** – The system MUST provide MCP tools to obtain a real‑time health snapshot (CPU/memory/disk/temperature, etc.).  
- **FR‑3** – The system SHOULD support metrics collection at a configurable sampling interval and persist samples locally.  
- **FR‑4** – The system SHOULD support querying historical metrics by time range or by number of samples.

### 5.2 Service & Process Management (Phase 1/2)

- **FR‑5** – The system MUST provide the ability to list current processes and basic information (Phase 1).  
- **FR‑6** – The system SHOULD provide the ability to filter processes by criteria (e.g., name, PID) (Phase 1 or 2).  
- **FR‑7** – The system MAY provide systemd service control (start/stop/restart/status) and this MUST be configurable and opt‑in (Phase 1+).  
- **FR‑8** – The system MAY provide the ability to send signals to individual processes (terminate/restart) and MUST enforce safeguards (such as whitelists) to avoid accidental kills (Phase 2).

### 5.3 Device Control

- **FR‑9** – The system MUST provide safe access to GPIO pins:  
  - List available/allowed pins and their current modes.  
  - Configure pin modes (input/output/pull‑up/pull‑down).  
  - Read/write digital levels.  
- **FR‑10** – The system SHOULD support PWM output (frequency and duty cycle) for fan/motor control.  
- **FR‑11** – The system SHOULD support basic I2C bus operations: scan devices, perform bounded‑length reads/writes.  
- **FR‑12** – The system MAY support higher‑level interfaces for common peripherals (e.g., temperature/humidity sensors, IMUs, environmental sensors) (Phase 2).  
- **FR‑13** – When a local camera is available, the system SHOULD provide basic camera control, at least taking photos (saving to a configured directory and returning the path); short video recording can be added in Phase 2+.

### 5.4 Reboot/Shutdown & Safeguards

- **FR‑14** – The system MUST provide a safe reboot tool that:  
  - Records the reboot reason and caller (if available).  
  - Supports an optional delay (e.g., 5–30 seconds).  
- **FR‑15** – The system MAY provide a shutdown tool, but it MUST have stronger enablement and confirmation logic than reboot.  
- **FR‑16** – The system MUST be designed to prevent repeated reboot/shutdown (rate limiting, warnings/alerts, etc.).

### 5.5 Security & Access Control

- **FR‑17** – The MCP server MUST support access control via OAuth/OIDC (e.g., Cloudflare Access).  
- **FR‑18** – The system MUST support configuration of authorization levels per tool (read‑only / safe control / admin‑level dangerous operations).  
- **FR‑19** – The system MUST record audit logs for all MCP calls, including tool name, timestamp, and result.  
- **FR‑20** – The system SHOULD allow disabling certain dangerous tools via configuration (e.g., OS updates, shutdown).

### 5.6 Self‑Update & OS Update

- **FR‑21** – The system MUST support remote update of the MCP server itself (self‑update) – fetching a new version and restarting the service.  
- **FR‑22** – The system SHOULD provide a simple rollback path (e.g., retain the previous version and auto‑rollback on failure).  
- **FR‑23** – The system MAY provide OS‑level package updates (e.g., `apt update && apt upgrade`), but such tools MUST be marked as dangerous and must be fully disableable.

### 5.7 Logging & Diagnostics

- **FR‑24** – The system MUST record structured application logs, at least including time, level, module, message, and key fields.  
- **FR‑25** – The system MUST record audit logs at the MCP call layer.  
- **FR‑26** – The system MUST provide tools to query portions of system/service logs for basic troubleshooting in Phase 1; later phases may add more advanced filtering, search, and export.

### 5.8 Server Introspection & Management

- **FR‑27** – The system MUST provide tools to view MCP server state, including but not limited to: version, build information, configuration summary (without sensitive values), startup time, and self‑update status.  
- **FR‑28** – The system SHOULD provide a capability matrix or “self‑description” tool to report which modules and hardware capabilities are available (e.g., whether a camera or temperature sensor is present, whether self‑update is enabled) so clients can adapt.

## 6. Non‑Functional Requirements

This section uses identifiers `NFR‑x` to denote non‑functional requirements.

### 6.1 Availability

- **NFR‑1** – The target is long‑running operation; occasional restarts (daily/weekly/monthly) are acceptable, and telecom‑grade high availability is not required.  
- **NFR‑2** – The system SHOULD be self‑healing under failures (e.g., processes restarted by systemd when they crash).  
- **NFR‑3** – Self‑update failures MUST NOT make the device completely unmanageable (e.g., keep the previous version or a fallback path).

### 6.2 Performance & Latency

- **NFR‑4** – Typical MCP request latency SHOULD be on the order of hundreds of milliseconds, but MAY degrade to several seconds under load or network instability.  
- **NFR‑5** – On devices with 1 GB of RAM and SD/TF card storage, steady‑state memory usage SHOULD be kept to a few hundred MB (including dependencies) where feasible.  
- **NFR‑6** – Metric collection and log writing SHOULD NOT significantly impact the main workloads.

### 6.3 Portability & Compatibility

- **NFR‑7** – Support Raspberry Pi models: Pi 2, 3, 3+, 4, 5, Zero 2W.  
- **NFR‑8** – Support Raspberry Pi OS (32/64‑bit); avoid relying on features specific to a single OS version.  
- **NFR‑9** – Hardware differences (e.g., different GPIO controllers or temperature sensors) SHOULD be abstracted away by appropriate abstraction layers.

### 6.4 Security & Privacy

- **NFR‑10** – Default configuration SHOULD be “secure by default”; dangerous tools MUST require explicit enablement.  
- **NFR‑11** – All public entry points MUST be protected by authentication at the network or application layer (OAuth/access tokens).  
- **NFR‑12** – Logs MUST NOT record sensitive credentials (e.g., OAuth tokens, passwords).

### 6.5 Operability & Observability

- **NFR‑13** – The system MUST emit enough structured logs and metrics to make it possible to trace and diagnose issues (see doc 09).  
- **NFR‑14** – Critical operations (reboot, self‑update, service control, device control) MUST have traceable audit records including initiator, time, and result.  
- **NFR‑15** – The system SHOULD expose simple health‑check endpoints or tools for external monitoring/coordination to probe liveness.

### 6.6 Extensibility

- **NFR‑16** – Adding new MCP tools or modules MUST NOT break behavior of existing stable tools; incompatible changes MUST be reflected via versioning or new tool names.  
- **NFR‑17** – The authorization model and configuration system SHOULD support future addition of roles, policies, and tool categories without major refactoring.  
- **NFR‑18** – The design SHOULD allow future device‑control extensions (e.g., Zigbee gateways, Docker management) within the same security model.

### 6.7 Technology Choices

- **NFR‑19** – The implementation language is **Python 3.11+**, using Python ecosystem tools (e.g., `fastapi`, `uvicorn`, `pydantic`) as the primary stack (see docs 02 and 13).  
- **NFR‑20** – OS‑level updates MUST use the default Raspberry Pi OS package manager (`apt`/`apt-get`); the design MUST NOT rely on containers or custom package managers as required dependencies.  
- **NFR‑21** – For Phase 1, the authorization model assumes a single device owner / single trusted user and does NOT support multi‑tenant or multi‑user fine‑grained authorization (this can evolve later).

### 6.8 Resilience & Testability

- **NFR‑22** – Under network instability or outages, core local management and monitoring MUST remain available; self‑update and OS update MUST “fail safely” (e.g., no partial/inconsistent states) and MUST NOT leave the system unmanageable (see docs 03 and 10).  
- **NFR‑23** – The implementation SHOULD be amenable to automated testing and CI, and follow test‑driven development (TDD) principles:  
  - Core modules SHOULD have good unit and integration test coverage (see doc 11); overall line coverage target is at least 85%, with higher coverage for critical modules.  
  - New features and bug fixes SHOULD add or update test cases first, then implement or adjust code, and any regression MUST be covered by tests.  
  - The project SHOULD follow the Python development standards and tooling defined in doc 13 (`uv`, `pytest`, `pytest-cov`, `tox`, `ruff`, `mypy`, etc.).

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- Runtime environment: Raspberry Pi OS; storage typically on TF/SD card, optionally with external SSD.  
- Network environment may have **intermittent connectivity**, especially over Wi‑Fi.  
- Some devices have only 1 GB RAM, so resources are limited.  
- Public exposure will be via Cloudflare Tunnel (assumed available and configurable).

### 7.2 Assumptions

- MCP clients (e.g., ChatGPT) can handle OAuth flows and supply appropriate token headers.  
- Device owners are able to perform the initial local install and configuration of the MCP server and Cloudflare Tunnel.  
- Any future additional client types (e.g., local Web UI) will reuse the same MCP interface.

## 8. Phasing & Roadmap

### 8.1 Phase 1 (Minimum Viable Version)

- Implement system information and health snapshot tools (FR‑1, FR‑2).  
- Implement basic metrics collection and limited history querying (FR‑3, FR‑4).  
- Implement basic GPIO and I2C operations (FR‑9–FR‑11).  
- Implement basic camera photo capture (FR‑13).  
- Implement safe reboot tools (FR‑14).  
- Implement MCP server self‑update (FR‑21) with recoverability on failure.  
- Implement basic security and OAuth integration plus audit logging (FR‑17–FR‑20, FR‑24–FR‑25).  
- Implement basic log query tools (FR‑26) and server introspection tools (FR‑27).

### 8.2 Phase 2+

- Extend service/process management capabilities (FR‑6–FR‑8).  
- Extend device control to more peripherals and higher‑level abstractions (FR‑12).  
- Enhance log query and diagnostics (build on FR‑26 with more advanced filtering, search, export, and correlation).  
- Introduce OS‑level update tools (FR‑23) and refine rollback strategies (FR‑22).  
- Further optimize performance, observability, and operational experience.  
- Design and implement extension mechanisms (e.g., plugins via FFI or subprocess integration for Go/Node tools), with a clear plugin system or command adaptation layer so that non‑Python tools can safely extend capabilities without bypassing the security model.

In Phase 2+ we will also:

- Further refine the boundary and invocation patterns between self‑update and OS‑level updates via `apt`/`apt-get` (e.g., preview updates, staged rollouts), and document concrete strategies in doc 10.  
- Further refine local log and metrics retention strategies (capacity limits, rotation intervals, tiered retention), and any external archival options; these strategies will be documented concretely in doc 09.

## 9. Open Questions

At this time there are no critical open questions that must be resolved before implementation. If new uncertainties arise in requirements or architecture, they will be recorded here and reflected in the relevant design documents.

## 10. Implementation Readiness Notes

For ease of implementation:

- Each functional requirement (FR‑x) maps to at least one MCP tool or internal module:
  - `system.*`, `metrics.*` → FR‑1–FR‑4.
  - `service.*`, `process.*` (including `process.send_signal` in Phase 2+) → FR‑5–FR‑8.
  - `gpio.*`, `i2c.*`, `camera.*` → FR‑9–FR‑13.
  - `system.reboot`, `system.shutdown` → FR‑14–FR‑16.
  - Security, logging, self‑update (including `manage.preview_os_updates` and `manage.apply_os_updates` in Phase 2+), and introspection modules → FR‑17–FR‑28.  
- Each non‑functional requirement (NFR‑x) is reflected in at least one design document:  
  - Availability and self‑recovery → docs 02, 10, 12.  
  - Performance and resource usage → docs 02, 03, 06.  
  - Security and privacy → docs 04, 09.  
- During implementation, maintain a simple “requirement → implementation → test cases” traceability table so that for every FR/NFR there is at least one covering test.  
- When adding new requirements, assign new FR/NFR IDs and update this document and the corresponding design docs accordingly.  
