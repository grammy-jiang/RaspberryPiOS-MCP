# 03. Raspberry Pi Platform & Resource Constraints Design Note

## 1. Document Purpose

- Describe the target Raspberry Pi hardware platforms and operating system.  
- Analyze memory, CPU, storage, and network constraints and how they affect the MCP server design.  
- Provide input to performance, reliability, and security decisions in the rest of the design.

## 2. Target Hardware Platforms

### 2.1 Supported Raspberry Pi Models

The initial target set of devices is:

- Raspberry Pi 2  
- Raspberry Pi 3 / 3B+  
- Raspberry Pi 4  
- Raspberry Pi 5  
- Raspberry Pi Zero 2W

These models differ in CPU architecture, memory capacity, I/O controllers, and power, so we rely on abstraction layers to smooth out differences.

### 2.2 Typical Hardware Configurations

- **Memory** – Minimum supported RAM: 1 GB.  
- **Storage**:  
  - System disk is typically a TF/SD card.  
  - Optional external USB/SSD as a data disk.  
- **Network**:  
  - Wired LAN (Ethernet).  
  - Wi‑Fi (2.4/5 GHz) with potential intermittent connectivity or weak signal.  
- **Peripherals**:  
  - GPIO pins.  
  - I2C / SPI / UART buses.  
  - CSI camera connector.  
  - Various sensors and external modules.

### 2.3 Model‑Specific Notes (Overview)

- **Pi 2 / 3 / 3B+**:  
  - Lower CPU performance; suitable for lighter workloads.  
  - Often only 1 GB RAM; requires more conservative background tasks and log/metrics retention.  
- **Pi 4**:  
  - Significant performance improvements; suitable for more background services and more frequent metric sampling.  
  - Supports larger RAM configurations (2 GB+); design should still consider lower‑end models.  
- **Pi 5**:  
  - Improved I/O subsystem and GPU/multimedia hardware; some older tool paths may differ.  
  - Prefer capability detection over hard‑coded model checks to determine available features.  
- **Zero 2W**:  
  - Most constrained device; best suited as a lightweight edge node.  
  - Recommended to disable high‑overhead features by default (e.g., very frequent sampling or heavy log queries).

## 3. Operating System & Runtime

### 3.1 Target OS

- Target OS: **Raspberry Pi OS** (both 32‑bit and 64‑bit SHOULD be supported).  
- Assume system updates and dependency installation via the standard package manager (APT).  
- Assume `systemd` is available as the init system and service manager.

### 3.2 Runtime Environment

- Implementation language: **Python 3.11+**, as the primary language for both MCP Server and privileged agent:  
  - Leverages the Python ecosystem for Raspberry Pi hardware and system libraries (`gpiozero`, `psutil`, `smbus2`, etc.).  
- In Phase 2+, other languages (e.g., Go/Node tools) MAY be integrated via FFI or subprocess‑based plugins; details are covered by the plugin/adapter layer designs.  
- No dependency on a graphical environment (X11/Wayland); all functionality is exposed via CLI/services and MCP tools.

## 4. Resource Constraints

### 4.1 Memory Constraints

- Minimum supported RAM: 1 GB.  
- MCP Server and its dependencies (runtime, libraries, daemon processes) SHOULD aim to keep memory usage modest:  
  - Target steady‑state total usage under ~300–400 MB where feasible (exact numbers will depend on implementation details).  
  - Avoid loading large volumes of metrics/logs entirely into memory.  
- Recommendations:  
  - Use streaming log writes rather than in‑memory buffers.  
  - Use pagination/windowing for metrics collection and queries.  
  - Use caches carefully and avoid unbounded in‑memory caches.

### 4.2 CPU Constraints

- Raspberry Pi CPUs are multi‑core ARM but weaker than typical desktop/server CPUs.  
- MCP request handling SHOULD remain lightweight and avoid heavy computation in a single request (e.g., complex compression, expensive scans).  
- Metric collection and background tasks SHOULD be spread over time to avoid competing with foreground load.

### 4.3 Storage Constraints

- TF/SD cards have limited I/O performance and are subject to wear:  
  - Logs and metrics MUST be written with controlled frequency and volume to avoid accelerating card wear.  
  - Log rotation (size/time‑based) is strongly recommended.  
- If an external SSD is detected, high‑frequency writes (metrics DB, audit logs) SHOULD be directed there where possible.  
- Update mechanisms MUST be robust under low free‑space conditions, avoiding partial downloads/writes that could corrupt installations.

### 4.4 Network Constraints

- Devices typically connect via LAN/Wi‑Fi and may experience:  
  - Short disconnections.  
  - High latency.  
  - DNS issues.  
- The MCP server MUST keep local functionality available under unstable network conditions (e.g., local scripts and tools continue to work).  
- Self‑update and OS update flows MUST implement retries and timeouts and MUST fail safely when network operations fail.

## 5. Design Implications

### 5.1 Architecture Implications

- Prefer **lightweight, modular** design; avoid heavy dependencies (e.g., large external databases or message queues) on constrained devices.  
- Prefer built‑in system facilities (systemd, journald, filesystem) over additional services where practical.  
- Use abstraction layers to encapsulate hardware and OS specifics and simplify cross‑model support.

### 5.2 Logging & Metrics Implications

- Logs and metrics SHOULD default to local storage in files or lightweight databases (e.g., SQLite), not external systems.  
- Provide configuration for retention duration and total capacity for logs and metrics.  
- For high‑frequency events (e.g., GPIO state changes), avoid per‑event disk writes; use buffering or sampling instead.

### 5.3 Security Implications

- Even with constrained hardware, security requirements are high due to potential public exposure:  
  - Prefer using existing TLS termination (Cloudflare) and system crypto libraries for heavy cryptographic operations.  
  - Avoid implementing complex custom cryptographic protocols.  
- The privileged agent SHOULD remain minimal to reduce attack surface and potential vulnerabilities.

### 5.4 Deployment Profiles

- It is useful to define deployment “profiles” according to device type and usage:  
  - `lightweight` – for 1 GB devices (Pi 2/Zero 2W): disable high‑frequency sampling and heavy log queries by default.  
  - `standard` – for Pi 3/4: enable most features with default intervals and log levels.  
  - `performance` – for higher‑RAM Pi 4/5: allow more sampling tasks and diagnostic features.  
- Profiles are implemented via configuration defaults controlling enabled modules, sampling intervals, log levels, etc.

## 6. Compatibility Strategy

### 6.1 Hardware Abstraction

- Use libraries or dedicated abstraction layers for GPIO, I2C, SPI, etc.:  
  - For Python, consider `gpiozero` or wrappers around `libgpiod`/other backends.  
  - Choose the appropriate backend based on configuration and runtime detection.  
- Prefer capability detection (e.g., “is this temperature sensor interface available?”) over hard‑coded model checks.

### 6.2 OS & Version Handling

- Avoid depending on a particular kernel version; use presence of files/commands for feature detection (e.g., whether `vcgencmd` is available).  
- Self‑update and OS update logic MUST be compatible with the standard APT behavior and flexible enough to accommodate future OS changes (e.g., via configuration and parameters).

## 7. Risks & Mitigations

- **Risk: SD card wear causing storage failures**  
  - Mitigation: control frequency and volume of log/metrics writes; use external SSD for high‑write workloads; implement backup/export mechanisms.  
- **Risk: resource exhaustion leading to unstable MCP service**  
  - Mitigation: performance/benchmark testing; limit background task resource usage; use OS‑level resource controls (e.g., cgroups) where appropriate.  
- **Risk: hardware differences causing inconsistent behavior**  
  - Mitigation: unify hardware access via abstraction layers; document per‑model capabilities where needed; perform runtime self‑checks and surface a capability matrix.

## 8. Implementation Checklist

During implementation, ensure the following with regard to platform and constraints:

- On startup, perform a platform self‑check, including at least:  
  - Raspberry Pi model and memory size detection.  
  - Key interface availability (`/proc`, `/sys`, `systemd`, `vcgencmd`, etc.).  
  - Existence and writability of log and metrics directories.  
- Select an appropriate deployment profile based on self‑check and log it:  
  - For example, `profile=lightweight` should automatically adjust sampling intervals and log levels.  
- Set sensible default concurrency limits and buffer sizes on low‑memory devices.  
- In the test matrix (see `docs/test-matrix.md`), cover at least one low‑end (e.g., 1 GB Pi 3 or Zero 2W) and one high‑end (e.g., Pi 4/5) device and verify performance/resource usage meets expectations.  

