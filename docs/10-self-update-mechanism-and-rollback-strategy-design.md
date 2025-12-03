# 10. Self‑Update Mechanism & Rollback Strategy Design

## 1. Document Purpose

- Describe the overall design and flow of the MCP server self‑update mechanism.
- Explain how to safely fetch new versions, switch versions, and roll back on failure.
- Define the relationship and boundaries between MCP server self‑updates and OS‑level updates (APT).

This document builds on:

- `01-raspberry-pi-mcp-server-requirements-specification.md` – FR‑21, FR‑23, NFRs for safety and manageability.
- `02-raspberry-pi-mcp-server-high-level-architecture-design.md` – process model, privileged agent, IPC.
- `04-security-oauth-integration-and-access-control-design.md` – roles, policies, audit logging.
- `05-mcp-tools-interface-and-json-schema-specification.md` – `manage.*` tools and JSON Schemas.
- `09-logging-observability-and-diagnostics-design.md` – logging and audit requirements.
- `12-deployment-systemd-integration-and-operations-runbook.md` – systemd integration and operational procedures.
- `14-configuration-reference-and-examples.md` – `updates.*` configuration.

## 2. Goals & Non‑Goals

### 2.1 Goals

- **Controlled remote self‑update capability (FR‑21, Phase 1)**
  - Allow the MCP server to update itself via:
    - MCP tools (`manage.update_server`).
    - Local CLI (for example `mcp-raspi-update`).
  - Support:
    - `target_version` selection.
    - `channel` (e.g. `stable`/`beta`) with configuration‑driven constraints.
  - Provide clear status feedback using the shared `common_status` structure:
    - `manage.get_server_status` exposes the most recent update status.

- **Safe and recoverable behavior (NFR‑3, NFR‑14, NFR‑22)**
  - The device must remain manageable regardless of update success:
    - If update fails, the previous version must continue to be usable via MCP or SSH.
    - If the new version fails to start, automatic or manual rollback must restore the previous known‑good version.
  - All updates and rollbacks must be fully audited:
    - Caller, time, target version, result, and error codes.

- **Clear version management & rollback strategy**
  - Use a versioned layout to manage MCP server versions:
    - Version directories.
    - A `current` symlink.
    - A `version.json` metadata file (see §5).
  - Each version has its own release directory.
  - Current running version is indicated by the `current` symlink and `version.json`.
  - The last known good version is recorded for rollback.
  - Automatic rollback:
    - Triggered when a new version fails startup consecutively beyond a threshold.
  - Manual rollback:
    - Operators can choose a rollback target via CLI or MCP tools.

- **Fit Raspberry Pi resources and network conditions**
  - Designed for:
    - 1 GB RAM.
    - microSD + optional SSD storage.
    - Unreliable network connectivity.
  - Update process must:
    - Fail gracefully when disk space is insufficient or network is unavailable.
    - Never corrupt the currently running version.
  - Enforce limits and checks for:
    - Download size.
    - Release directory usage.
  - Use staging directories and a clear state machine to avoid “half‑installed” states.

- **Support multiple deployment modes (extensible in Phase 2+)**
  - Phase 1:
    - Primary focus on Python package distribution via PyPI/ private indices.
  - Phase 2+:
    - Optional backends (Git, archives, APT) integrated behind a unified backend interface and state machine.

- **Clear separation from OS updates (FR‑23)**
  - Strictly distinguish:
    - Self‑update: update only the MCP server (`mcp-raspi` and its runtime).
    - OS update: update underlying OS packages via `apt`/`apt-get`.
  - Keep designs and tools separate:
    - This document addresses OS update boundaries and workflows in §6.

### 2.2 Non‑Goals

- **Not a general distribution/orchestration platform**
  - The self‑update mechanism serves this MCP server and its environment only:
    - Does not provide a general package management service.
    - Does not manage arbitrary third‑party software or user applications.

- **Not a unified manager for all system components**
  - OS updates (kernel, system services, libraries) remain managed by:
    - `apt`/`apt-get`.
    - OS lifecycle tools.
  - This module:
    - Only provides a controlled entry point for OS updates (Phase 2+).
    - Does not replace APT or become a generic “system update center”.
  - It does not attempt to couple MCP self‑updates with OS updates into a single action.

- **No guarantee of zero‑downtime or live hot‑swap**

  - Design does not aim for fully seamless, zero‑downtime hot upgrades:
    - Updates typically require restarting the `mcp-raspi-server` systemd service (and possibly `raspi-ops-agent`).
    - Short periods of MCP unavailability are acceptable.
  - Does not support:
    - Cross‑request connection migration.
    - Session‑level hot switching (these belong to reverse proxies or client retry strategies).

- **No arbitrary historical version management or complex rollout strategies**
  - Rollback guarantees:
    - Only the previous known good version (`previous_good_version`) is guaranteed as a rollback target.
  - Does not include:
    - Full history backtracking.
    - Canary releases, phased rollouts, or blue‑green deployment (these could be Phase 2+ topics).

- **Not a complete backup/disaster recovery solution**
  - Self‑update and rollback:
    - Covers only MCP server update failures.
  - Does not replace:
    - System‑wide backups.
    - Filesystem snapshots.
    - Full images and DR plans (handled by operations and described in document 12).

## 3. Update Backends & Packaging

### 3.1 Phase 1: Python Package Distribution

Phase 1 assumes the MCP server is distributed and installed as a Python package:

- Managed using:
  - `uv` as the environment and package manager.
  - A `pyproject.toml`‑based project (no `requirements.txt`).
- Installation patterns:
  - A dedicated release directory per version:
    - For example `/opt/mcp-raspi/releases/<version>/`.
  - Each release may contain:
    - A virtual environment (for example `/opt/mcp-raspi/releases/<version>/venv`).
    - Or a Python package installed into a shared `uv` environment with version isolation.

Additional assumptions:

- The MCP server entrypoints (`mcp-raspi-server`, `raspi-ops-agent`) are installed in a predictable location under:
  - The release directory’s virtual environment, or
  - A shared environment configured in `AppConfig.updates`.
- `version.json`:
  - Resides in a stable location such as `/var/lib/mcp-raspi/version.json`.
  - Acts as the source of truth for:
    - `current_version`.
    - `previous_good_version`.
    - Last update status (`last_update`).

### 3.2 Phase 2+: Additional Backends (Overview)

Phase 2+ may introduce additional backends, while preserving the same high‑level flow and rollback semantics:

- `GitBackend`:
  - Uses `git fetch` + `git checkout` plus build steps to place code into release directories.
- `ArchiveBackend`:
  - Downloads and verifies tarballs.
  - Extracts them into staging and then release directories.
- `AptBackend`:
  - Uses APT to install or upgrade the MCP server package.
  - Requires careful handling for:
    - Mapping APT‑installed versions into the `version.json` model.
    - Rolling back logically (re‑pinning, reinstalling previous package) where feasible.

These backends share:

- The same `UpdateBackend` abstraction (§3.4).
- Integration via the `UpdateService` state machine.
- The same version directory and `version.json` concepts (where applicable).

### 3.3 APT Integration (Phase 2+)

For environments that prefer OS‑level package management:

- The MCP server may also be packaged as a Debian package (`mcp-raspi`) and installed via APT.
- In this mode:
  - A lightweight `AptBackend` can:
    - Call `apt update` and `apt install --only-upgrade mcp-raspi`.
    - Use `dpkg -s mcp-raspi` or `apt-cache policy mcp-raspi` to determine the installed version.
    - Sync `version.json.current_version` and `previous_good_version` accordingly.
  - APT handles transactional aspects and dependency resolution.

Limitations:

- Rolling back APT upgrades:
  - Often requires:
    - Pinning.
    - Dedicated repositories.
    - Or external snapshot mechanisms.
  - The self‑update module offers limited rollback logic in APT mode; full rollback relies on external tools.

### 3.4 Update Backend Abstraction

To support multiple deployment modes, define an abstract backend interface in `mcp_raspi.modules.update.backends`:

```python
from typing import Optional
from pydantic import BaseModel


class PreparedUpdate(BaseModel):
    target_version: str
    channel: Optional[str] = None


class UpdateBackend:
    async def prepare(
        self,
        channel: Optional[str],
        target_version: Optional[str],
    ) -> PreparedUpdate: ...

    async def apply(self, update: PreparedUpdate) -> None: ...
```

#### 3.4.1 Responsibilities & Semantics

`UpdateBackend` focuses on “how to obtain and place the new version”, not on:

- Who initiates the update (MCP tool vs CLI).
- State machine orchestration, audit logging, or error mapping.
- systemd restarts or service orchestration.

`prepare(channel, target_version)`:

- Interprets intent:
  - If `target_version` is provided:
    - Lock onto that specific version.
  - If `target_version` is `None`:
    - Use `channel` (for example `stable`/`beta`) to resolve the latest available version.
- Checks preconditions:
  - Disk space.
  - Network connectivity.
  - Presence of required tools (for example `uv`, `pip`, `git`, `apt`).
  - On failure:
    - Raise `ToolError` with appropriate `error_code`, e.g.:
      - `unavailable` for network failures.
      - `resource_exhausted` for disk space issues.
- Prepares artifacts in a staging area:
  - For example, downloads and installs a Python wheel into a temporary directory.
  - Returns `PreparedUpdate`:
    - `target_version` is the resolved concrete version.
    - Additional fields (implementation‑specific) may include:
      - `staging_path`.
      - Checksums or metadata.
- Must be idempotent:
  - Repeated calls for the same `channel` + `target_version` should reuse existing staging artifacts where possible and avoid destructive changes.

`apply(update)`:

- Assumes `update` came from `prepare` of the same backend.
- Performs local “switch” actions, such as:
  - Ensuring `/opt/mcp-raspi/releases/<version>/` (or equivalent) is fully ready.
  - Atomically updating the `current` symlink (§5.4).
  - Updating or adjusting systemd units if necessary.
- On failure:
  - Raise `ToolError`.
  - Avoid leaving the system in a half‑switched state:
    - Only update symlinks after verifying new version availability.
    - Restore previous state if failure occurs mid‑switch.

Implementation may extend `PreparedUpdate` with `backend`, `staging_path`, `metadata`, etc., but:

- The model must remain JSON‑serializable.
- Tests (see §8.1) must cover all added fields.

#### 3.4.2 Concrete Backends

- **Phase 1: `PythonPackageBackend`**
  - Uses `uv`/`pip` to install `mcp-raspi` into a release directory or virtual environment:
    - For example:
      - `/opt/mcp-raspi/releases/<version>/venv/`
      - or `/opt/mcp-raspi/venv-<version>/`.
  - Reads from `AppConfig.updates`:
    - `package_name` (default `mcp-raspi`).
    - `releases_dir`.
    - `staging_dir`.
    - `default_channel`.
  - `prepare`:
    - Resolves version and channel:
      - Using configured index metadata or external API calls if needed.
    - Uses `subprocess` to run a command such as:
      - `uv pip install mcp-raspi==<version> -t <staging_dir>`
      - or an equivalent `uv` operation to install into a staged environment.
    - Verifies that entrypoints (`mcp-raspi-server`, `raspi-ops-agent`) are available in the new path.
  - `apply`:
    - Moves/renames the staging directory into `<releases>/<version>`.
    - Atomically updates `current` symlink to point to the new directory.
    - Updates `version.json` with the pending switch information (see §5.1).

- **Phase 2+: `GitBackend` / `ArchiveBackend` / `AptBackend`**
  - `GitBackend`:
    - Uses `git fetch` + `git checkout` and a build step to install a specific commit/tag into a release directory.
  - `ArchiveBackend`:
    - Downloads tarballs.
    - Verifies hashes/signatures.
    - Extracts into staging, then switches to release.
  - `AptBackend`:
    - Executes commands such as:
      - `apt update && apt install --only-upgrade mcp-raspi`.
    - Requires additional logic to:
      - Identify the currently installed version.
      - Provide limited rollback support or rely on external mechanisms.

All backends:

- Must implement the `UpdateBackend` interface.
- Are selected via configuration and the `UpdateService` (see §3.4.3).

#### 3.4.3 Backend Selection & Configuration

In `AppConfig`, define an `UpdatesConfig` section (see also document 14):

```python
from pydantic import BaseModel
from typing import Literal


class UpdatesConfig(BaseModel):
    backend: Literal["python_package", "git", "archive", "apt"] = "python_package"
    package_name: str = "mcp-raspi"
    releases_dir: str = "/opt/mcp-raspi/releases"
    staging_dir: str = "/opt/mcp-raspi/staging"
    default_channel: str = "stable"
    enable_remote_server_update: bool = False
    enable_os_update: bool = False
```

Backend selection:

- During `UpdateService` initialization:
  - Use `AppConfig.updates.backend` to instantiate the appropriate backend:
    - `python_package` → `PythonPackageBackend`.
    - `git` → `GitBackend` (Phase 2+).
    - `archive` → `ArchiveBackend` (Phase 2+).
    - `apt` → `AptBackend` (Phase 2+).

Configuration layering:

- `releases_dir` and `staging_dir`:
  - Can be overridden via environment variables or CLI arguments, following the config layering rules in documents 02 and 13.
- Sensitive settings:
  - Private PyPI URLs, APT repository credentials, etc., must come from secrets or environment files, not hard‑coded in configuration.

This abstraction allows:

- Introducing new deployment/update methods without changing:
  - `UpdateService` public API.
  - MCP tool schemas.
  - State machine and rollback logic.

## 4. Update Workflow

This section ties together:

- Tool interfaces (document 05).
- Backend abstraction (§3.4).
- Rollback strategy (§5).
- Privileged agent integration (document 02).

### 4.1 High‑Level Flow (Request Perspective)

Example Phase 1 flow (Python package backend):

1. **Client calls MCP tool**
   - Client (e.g. ChatGPT) calls `manage.update_server` with `channel` and/or `target_version` (see document 05 §8.2).

2. **MCP server entry layer**
   - JSON‑RPC layer parses the request into `ToolContext` and parameters, then:
     - Validates caller identity and role:
       - Only `admin` role can perform updates (document 04).
     - Checks policy flags:
       - `AppConfig.updates.enable_remote_server_update`.
       - If disabled:
         - Raise `ToolError(error_code="failed_precondition")`.

3. **Call the update service (inside non‑privileged process)**
   - Tool handler calls `UpdateService.update_server(channel, target_version)`.
   - `UpdateService`:
     - Uses `AppConfig.updates.backend` to select a backend.
     - Builds internal context:
       - Current version, target version, channel, caller information.

4. **Execute privileged steps via the agent**
   - For actions requiring root privileges (filesystem writes, systemd control):
     - `UpdateService` uses `OpsAgentClient` (documents 02 and 08) to send an IPC request, e.g.:
       - `operation="update.server"`.
       - `params` includes `channel`, `target_version`, and current version data.
   - In `raspi-ops-agent`:
     - `UpdateHandler`:
       - Calls the selected `UpdateBackend.prepare` and `UpdateBackend.apply`.
       - Drives the state machine (see §4.2, §5).
       - Persists status to `version.json`.

5. **Restart & self‑check**
   - After switching versions:
     - The agent triggers `systemctl restart mcp-raspi-server` (and restarts itself if needed).
   - systemd (configured per document 12):
     - Brings up the new version.
   - On startup:
     - The new server instance:
       - Reads `version.json`.
       - Performs self‑checks.
       - Updates `ServerStatus.last_update`.

6. **Client receives status**
   - `manage.update_server` returns:
     - A `UpdateStatus` object (document 05 §8.2) describing:
       - `old_version`.
       - `new_version`.
       - `status` (`pending`, `running`, `succeeded`, `failed`).
   - Clients can call:
     - `manage.get_server_status` to poll or inspect the last update status.

### 4.2 State Machine Overview

The update process is modeled as a state machine:

- States (example set):
  - `idle`.
  - `checking_prerequisites`.
  - `preparing`.
  - `switching`.
  - `verifying`.
  - `succeeded`.
  - `failed`.
- Transitions:
  - `idle` → `checking_prerequisites`.
  - `checking_prerequisites` → `preparing` or `failed`.
  - `preparing` → `switching` or `failed`.
  - `switching` → `verifying` or `failed`.
  - `verifying` → `succeeded` or `failed`.

Each transition:

- Must be recorded in `version.json` (`last_update` fields).
- Should emit:
  - Application log entries.
  - Audit entries for critical steps.

On failures:

- The state machine must:
  - Put the system into a defined `failed` state.
  - Ensure that `current` symlink and running version match.
  - Leave `previous_good_version` untouched unless a successful update occurs.

## 5. Version Layout & Rollback Strategy

### 5.1 Version Metadata (`version.json`)

`version.json` is the canonical source-of-truth for MCP version state, stored under a path such as `/var/lib/mcp-raspi/version.json`.

Example structure:

```json
{
  "current_version": "1.2.3",
  "previous_good_version": "1.2.2",
  "last_update": {
    "status": "succeeded",
    "old_version": "1.2.2",
    "new_version": "1.2.3",
    "started_at": "2025-01-01T12:00:00Z",
    "finished_at": "2025-01-01T12:01:00Z",
    "message": null
  }
}
```

Rules:

- `current_version`:
  - Version that the system expects to be running after successful startup.
- `previous_good_version`:
  - Last version known to have passed self‑check.
- `last_update`:
  - Uses `common_status` (document 05) for `status`/`message` and replicates `old_version`/`new_version`.
- All updates to `version.json`:
  - Must be atomic (write to temp file then rename).
  - Must be validated using a Pydantic model.

### 5.2 Automatic Rollback

Automatic rollback triggers when:

- New version fails self‑check multiple times (for example N consecutive failures).

Mechanism:

- On each startup, server runs self‑check:
  - Validates critical dependencies, configuration, and basic operations.
  - Records success or failure.
- A failure count (either in `version.json` or a separate state file) is incremented.
- When the count exceeds a threshold:
  - The agent or a small watchdog process:
    - Switches `current` symlink back to `previous_good_version`.
    - Updates `version.json`:
      - `current_version` set to `previous_good_version`.
      - `last_update.status` set to `failed`.
      - `last_update.message` describing rollback.
- After rollback:
  - The system returns to the previous known good version.
  - Further automatic updates may be suppressed until intervention.

### 5.3 Manual Rollback

Manual rollback is initiated via:

- MCP tool (Phase 2+):
  - A dedicated tool such as `manage.rollback_server`.
- CLI:
  - A local CLI utility (for example `mcp-raspi-rollback`).

Behavior:

- Allows an operator to:
  - Roll back to `previous_good_version`.
  - In Phase 2+, optionally choose another version within a limited history (if retained).
- Implementation:
  - Uses same symlink switching logic as successful forward update.
  - Updates `version.json` and status fields.

### 5.4 Directory & Symlink Layout

Recommended layout:

- Releases directory:
  - `/opt/mcp-raspi/releases/`
    - `1.2.2/`
    - `1.2.3/`
    - `...`
- Symlinks:
  - `/opt/mcp-raspi/current` → `/opt/mcp-raspi/releases/1.2.3/`
  - Optional:
    - `/opt/mcp-raspi/previous` → `/opt/mcp-raspi/releases/1.2.2/`
- Version metadata:
  - `/var/lib/mcp-raspi/version.json`

Flow alignment:

1. During `prepare`:
   - New version is installed into:
     - `/opt/mcp-raspi/staging/<temp-id>/` or `/opt/mcp-raspi/releases/<version>.staging/`.
2. On successful checks:
   - Staging directory is promoted to:
     - `/opt/mcp-raspi/releases/<version>/`.
3. During `SWITCHING`:
   - Atomically update `current` symlink to point to the new release directory.
   - Preserve old version directories until at least one successful self‑check.
4. On self‑check:
   - New version decides:
     - If successful:
       - Update `current_version` and `previous_good_version`.
       - Mark `last_update.status="succeeded"`.
     - If failed:
       - After threshold failures, invoke automatic rollback (see §5.2).

These layouts and flows:

- Must be thoroughly tested (see §8) to ensure:
  - `current` symlink, `version.json`, and the actual running version are always consistent.

## 6. OS Updates and Their Relationship to Self‑Update

### 6.1 Separation of Concerns

Self‑update vs OS update (from document 01 FR‑21/FR‑23):

- **Self‑update (server update)**:
  - Updates only the MCP server (`mcp-raspi` and its environment).
  - Does not proactively modify other system packages.
  - Implemented via:
    - `manage.update_server`.
    - Self‑update state machine.
- **OS update**:
  - Uses `apt`/`apt-get` to update OS packages:
    - Kernel.
    - Libraries.
    - System services.
  - Can indirectly affect MCP server behavior.

Boundaries:

- Even if MCP server is installed via APT:
  - “Update MCP package only” vs “update the entire system” must be separately controlled.
  - The former:
    - Is handled by self‑update logic and `AptBackend` (Phase 2+).
  - The latter:
    - Is handled by OS update tools, with broader risk.

OS update tools:

- Considered high‑risk:
  - Must be disabled by default.
  - Only enabled when:
    - Device owner explicitly turns them on.
    - `admin` role is configured with appropriate permissions (document 04).
- Phase 1 behavior:
  - OS update tools:
    - Should return `ToolError(error_code="failed_precondition")` with message “OS updates not enabled”.
    - Must not run any system commands.

### 6.2 OS Update Workflow (Overview, Phase 2+)

OS update process is conceptually split into two tools (document 05 §8.3):

- `manage.preview_os_updates`:
  - Read‑only preview of:
    - Which packages would be updated.
    - Target versions.
    - Estimated impact.
- `manage.apply_os_updates`:
  - Actually performs OS updates.
  - Optionally triggers a reboot.

#### 6.2.1 `manage.preview_os_updates`

Objectives:

- Provide insight into pending OS updates without changing system state.

Typical steps (in privileged agent `update.os` handler):

1. Optionally run `apt update`:
   - To refresh package indices (may also be done in `apply` step).
2. Run a simulation / read‑only command:
   - `apt list --upgradable`.
   - Or `apt-get -s upgrade`.
3. Parse output into a structured result:
   - For each upgradable package, include:
     - `name`.
     - `current_version`.
     - `candidate_version`.
     - `section`/`priority` (if available).
     - `is_security_update` (if derivable).
     - `size_change_bytes` (if available).
4. Aggregate summary:
   - Total packages.
   - Estimated download size and disk usage change.
   - A coarse “risk level” flag:
     - For example, “includes kernel updates, reboot recommended”.

Result:

- Returned via `manage.preview_os_updates` result schema:
  - Includes `common_status` for the task (usually a one‑shot `succeeded`).
  - Includes a detailed list and summary as defined in document 05.

#### 6.2.2 `manage.apply_os_updates`

Objectives:

- Execute OS updates once explicitly authorized.

Typical steps (in `update.os` handler):

1. Before execution, re‑validate:
   - Tool is enabled in configuration.
   - Caller role is `admin`.
   - System resources, such as disk space, meet minimum requirements:
     - Otherwise, return `resource_exhausted`.
2. Run update commands:
   - `apt update` (if not recently run or indices are stale).
   - `apt-get upgrade -y`:
     - Phase 2+ may allow configuration to choose between:
       - `upgrade`.
       - `full-upgrade`/`dist-upgrade`.
3. Track progress:
   - Treat OS update as a long‑running job.
   - Map progress into `common_status`:
     - `status`, `progress_percent`, `message`.
   - Phase 1 may:
     - Block until completion and return final status.
4. Determine reboot requirement:
   - Use tools such as `needrestart` or APT hints.
   - Add fields in result:
     - `reboot_required: bool`.
     - A brief explanation.
5. Reboot (if configured):
   - Automatic reboot is controlled by configuration:
     - Default is to only recommend a reboot, not execute it automatically.

The result of `manage.apply_os_updates`:

- Should include:
  - `common_status` for the job.
  - A `summary`:
    - Number of packages updated.
    - Success/failure counts.
    - `reboot_required`.

#### 6.2.3 Relationship to Self‑Update State Machine

OS updates do not use:

- Version directories and `version.json` (self‑update only).

They can reuse:

- `common_status` for job status representation.
- Logging/audit conventions (document 09).
- `ToolError` error mapping (document 05 §9).

Recommended practice:

- Before OS updates:
  - Use `manage.update_server` to bring MCP server to the latest stable version.
  - Then trigger OS updates:
    - Reduces the chance of MCP server being incompatible during/after OS changes.

Phase 1 and Phase 2+:

- As per document 01:
  - OS update tools (`FR‑23`) are Phase 2+ features.
  - In Phase 1:
    - Tools return `failed_precondition` with a clear “OS updates not enabled” message.
  - Phase 2+:
    - Implement full preview and staged OS updates based on this section.

## 7. Security Considerations

This section specifies security requirements for the update and rollback mechanism, consistent with documents 01, 02, 04, and 09.

### 7.1 Trust Model & Attack Surface

Trust boundaries:

- External clients (for example ChatGPT):
  - Authenticated via Cloudflare/OAuth (document 04).
  - Must not gain arbitrary control over OS or package managers.
- Privileged agent (`raspi-ops-agent`):
  - The only component allowed to execute:
    - Update commands.
    - Version directory writes.
    - `version.json` modifications.
  - Runs with elevated privileges in a constrained environment.
- MCP server:
  - Runs as a non‑privileged user.
  - Issues restricted IPC requests for updates.

Attack surface:

- Unauthorized users triggering self‑update or OS update.
- Injection of malicious packages or tampering with downloads.
- Abuse of update interfaces:
  - Frequent restarts.
  - Disk exhaustion.
  - Service unavailability.
- Arbitrary shell command execution embedded in update scripts.

### 7.2 Update Source Integrity

Update sources must be trusted and use HTTPS:

- Python package updates:
  - Must use trusted PyPI or configured private index.
  - TLS verification must not be disabled or weakened.
- OS updates:
  - Must use trusted APT repositories with GPG verification.

Python package backend:

- Uses PyPI or configured private indices (URL and credentials from `AppConfig`/secrets).
- Optionally:
  - Verify hashes or signatures of downloaded wheel/tarball.
  - Phase 2+ may introduce:
    - Independent signing workflows.

APT/OS update backend:

- Relies on Debian/Raspberry Pi OS GPG verification:
  - MCP update flow must not disable APT verification.
- OS update tools must not:
  - Directly modify `/etc/apt/sources.list`.
  - Import new repository keys.
  - These operations remain manual/admin tasks outside MCP.

On any integrity/check failure:

- Abort the update and raise `ToolError(error_code="failed_precondition")`.
- Log a high‑priority error.

### 7.3 Least Privilege & Command Whitelisting

Least privilege:

- Update commands and scripts:
  - Run inside the privileged agent with restricted access.
  - Only permitted to:
    - Access version directories (`/opt/mcp-raspi/releases`, `/var/lib/mcp-raspi`).
    - Run a limited set of explicit commands:
      - Python package update:
        - `uv pip install ...` or equivalent.
      - OS update:
        - `apt update`, `apt-get upgrade`, etc.
      - systemd control:
        - `systemctl restart`, `systemctl daemon-reload`, etc.
- No arbitrary shell commands:
  - MCP must not accept free‑form shell command strings as part of update operations.

Filesystem permissions:

- Update/rollback code may write only:
  - Version directories.
  - `current` symlink.
  - `version.json`.
  - OS update operations write via APT only.
- Access to these paths:
  - Must use minimum required privileges (for example a dedicated group/user).

### 7.4 Authorization, Policy & Rate Limiting

Authorization:

- `manage.update_server` and OS update tools:
  - Allowed only for `admin` role by default.
  - Policy is defined in:
    - Document 04 (role policies).
    - `tools.manage.*` policy configuration in document 14.

Policy toggles:

- `AppConfig.updates.enable_remote_server_update`:
  - Gate for remote self‑update via MCP.
- `AppConfig.updates.enable_os_update`:
  - Gate for OS update tools.
- When disabled:
  - Tools must return `ToolError(error_code="failed_precondition")`.

Rate limiting:

- Protect against:
  - Frequent update attempts.
  - Overlapping update requests.
- For example:
  - Permit at most one self‑update attempt per hour.
  - Reject concurrent update requests while one is in progress.
- Rate‑limited operations:
  - Return `ToolError(error_code="resource_exhausted")`.
  - Record an audit and application log entry.

### 7.5 Logging & Audit Requirements

Every update and rollback must be logged and audited:

- Application logs:
  - Record events such as:
    - Update start/end.
    - Errors.
    - Automatic rollback triggers.
- Audit logs:
  - Record:
    - Caller identity.
    - Tool name (`manage.update_server`, `manage.preview_os_updates`, etc.).
    - Target version.
    - Result and `error_code`.
    - Key context fields (for example `channel`, `backend`, `reboot_required`).

The `manage.get_server_status.last_update` field:

- Must be consistent with:
  - `version.json`.
  - Update logs and audit entries.

## 8. Testing & Validation

Tests for this module must follow TDD and coverage requirements from document 11:

- Every update/rollback behavior must be expressed in tests.

### 8.1 Unit Tests

- Version metadata & state machine:
  - Use temporary directories to simulate:
    - `/var/lib/mcp-raspi/`.
    - `/opt/mcp-raspi/`.
  - Test:
    - `version.json` read/write logic.
    - Updates to `current_version` and `previous_good_version`.
  - Cover all state transitions:
    - `idle` → `checking_prerequisites` → ... → `succeeded`/`failed`.
    - Verify that:
      - Different error scenarios lead to correct terminal states.
      - `UpdateStatus` values are correct.
- Update backend (PythonPackageBackend):
  - Mock `subprocess` / `uv` calls:
    - Normal paths.
    - Network errors.
    - Missing package versions.
    - Integrity check failures.
  - Verify:
    - `prepare` returns `PreparedUpdate` with expected `target_version` and `channel`.
- Rollback logic:
  - Simulate:
    - New version startup failures reaching the threshold.
  - Verify:
    - `current` symlink switches back to old version.
    - `version.json` is updated correctly.
- Error handling:
  - Inject representative errors:
    - Disk full.
    - Source unreachable.
    - Permission denied.
  - Verify:
    - `ToolError.error_code` matches definitions in document 05.

### 8.2 Integration Tests

Integration tests on actual Raspberry Pi or equivalent:

- Build two distinguishable `mcp-raspi` versions:
  - Use `manage.update_server` to upgrade from old to new.
  - Verify:
    - CLI and server version (`manage.get_server_status.version`) show the new version.
    - Old version directory remains available for rollback.
  - Introduce an intentionally broken new version:
    - Missing dependencies.
    - Fails self‑check.
  - Verify:
    - Automatic rollback triggers.
    - Old version is restored.
- Failures:
  - Simulate network interruption during download:
    - State machine ends in `failed`.
    - Reasonable message is returned.
  - Simulate failure updating symlink:
    - Verify rollback and status reporting.
- If OS updates (Phase 2+) are implemented:
  - Use a test APT repository or dummy packages to:
    - Verify `manage.preview_os_updates` and `manage.apply_os_updates`.

### 8.3 Security & Abuse‑Resilience Tests

- Permission checks:
  - Using different roles (`viewer`, `operator`, `admin`):
    - Attempt `manage.update_server` and OS update tools.
  - Verify:
    - Only allowed roles can perform updates.
    - Others receive `permission_denied`.
- Abuse scenarios:
  - Frequent self‑update calls:
    - Verify:
      - Rate limits and state machine protections:
        - For example, reject new requests while an update is in progress.
  - Disabled remote self‑update:
    - With `enable_remote_server_update=False`:
      - Verify that tools return `failed_precondition`.

### 8.4 Logging & Observability Tests

- Verify:
  - Each update and rollback generates:
    - Application log entries.
    - Audit log entries with:
      - Caller.
      - Target version.
      - Result.
      - `error_code`.
  - `logs.get_recent_app_logs` and `logs.get_recent_audit_logs` can retrieve relevant entries.
- Verify:
  - `manage.get_server_status.last_update`:
    - Matches `version.json`.
    - Is consistent with logs (timestamps and statuses).

## 9. Implementation Checklist

- Design and implement:
  - `mcp_raspi.modules.update.UpdateService`.
  - At least one `UpdateBackend` (`PythonPackageBackend`).
  - Keep schemas aligned with `manage.*` tools in document 05.
- Implement IPC handlers in the privileged agent:
  - `update.server` and `update.os` (Phase 2+).
  - Align operations with document 02 §6.4.
- Implement a clear state machine and error handling path:
  - Avoid being stuck in intermediate states.
  - Persist states to disk via `version.json`.
- Ensure that:
  - Every update or rollback step:
    - Logs an audit event before and after the step, keeping logs and metadata in sync.
  - SSH and MCP access remain available where possible during updates.
  - Documentation clearly states:
    - There may be short unavailability periods.
- Apply:
  - Reasonable timeouts and retry policies for network and disk operations.
  - `ToolError` with standard error codes for client feedback.
- In `AppConfig`, define:
  - Self‑update and OS update policy fields:
    - Enable/disable flags.
    - Channel restrictions.
    - Backend types.
  - Support environment variable and CLI overrides via the configuration layering rules.
- Following document 11:
  - Write comprehensive unit and integration tests for the self‑update module.
  - Ensure coverage meets project targets and enforce this in CI.


---

<!-- Merged from 10-addendum-self-update-rollback-enhancements.md -->


## 1. Update Package Signature Verification (Phase 1 Enhanced)

### 1.1 Overview

Cryptographic signature verification ensures update packages are authentic and haven't been tampered with, protecting against supply chain attacks and MITM attacks.

**Phase 1**: Basic signature verification with Ed25519
**Phase 2+**: Key rotation, hardware security modules, transparency logs

### 1.2 Signature Algorithm

**Algorithm**: Ed25519 (fast, small signatures, secure)
**Signature Size**: 64 bytes
**Public Key Size**: 32 bytes

**Why Ed25519**:
- Fast verification on Raspberry Pi (< 1ms)
- No complex dependency (available in Python `cryptography` library)
- Resistant to timing attacks
- Small signature size (good for embedded)

### 1.3 Update Package Structure

```
mcp-raspi-server-1.2.0.tar.gz        # Main package
mcp-raspi-server-1.2.0.tar.gz.sig    # Detached signature
mcp-raspi-server-1.2.0.manifest.json # Package manifest
```

#### Manifest File

```json
{
  "version": "1.2.0",
  "package_file": "mcp-raspi-server-1.2.0.tar.gz",
  "package_sha256": "a3c5e8f1...",
  "package_size_bytes": 15728640,
  "signature_file": "mcp-raspi-server-1.2.0.tar.gz.sig",
  "signing_key_id": "primary-2025",
  "signed_at": "2025-12-03T12:00:00Z",
  "min_version": "1.0.0",
  "release_notes_url": "https://releases.example.com/v1.2.0/notes.md",
  "files": [
    {
      "path": "src/mcp_raspi/server.py",
      "sha256": "b4d6e9f2...",
      "size": 12345
    }
  ],
  "requires_restart": true,
  "migration_required": false,
  "breaking_changes": false
}
```

### 1.4 Public Key Distribution

**Embedded Public Keys**: Ship with initial installation, stored in `/opt/mcp-raspi/keys/`.

```python
# /opt/mcp-raspi/keys/trusted-keys.json
{
  "version": 1,
  "keys": [
    {
      "key_id": "primary-2025",
      "algorithm": "ed25519",
      "public_key": "b5bb9d8014a0f9b1d61e21e796d78dccdf1352f23cd32812f4850b878ae4944c",
      "valid_from": "2025-01-01T00:00:00Z",
      "valid_until": "2026-12-31T23:59:59Z",
      "purpose": "release_signing",
      "revoked": false
    },
    {
      "key_id": "backup-2025",
      "algorithm": "ed25519",
      "public_key": "c6cc0e9015b1f0c2e72f32f807e87eddef2463g34de43923g5961c989bf5055d",
      "valid_from": "2025-01-01T00:00:00Z",
      "valid_until": "2026-12-31T23:59:59Z",
      "purpose": "release_signing_backup",
      "revoked": false
    }
  ]
}
```

### 1.5 Signature Verification Implementation

```python
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from pathlib import Path
from typing import Optional
import hashlib
import json

class SignatureVerifier:
    """Verifies update package signatures."""

    def __init__(self, keys_path: Path):
        self.keys_path = keys_path
        self.trusted_keys = self._load_trusted_keys()

    def _load_trusted_keys(self) -> dict:
        """Load trusted public keys from disk."""
        keys_file = self.keys_path / "trusted-keys.json"
        if not keys_file.exists():
            raise ValueError(f"Trusted keys file not found: {keys_file}")

        with open(keys_file, "r") as f:
            return json.load(f)

    def verify_package(
        self,
        package_path: Path,
        signature_path: Path,
        manifest_path: Path
    ) -> bool:
        """
        Verify update package authenticity.

        Returns:
            True if signature is valid, raises exception otherwise.
        """
        # 1. Load and verify manifest
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # 2. Verify package hash matches manifest
        package_sha256 = self._calculate_sha256(package_path)
        if package_sha256 != manifest["package_sha256"]:
            raise ValueError(
                f"Package hash mismatch: "
                f"expected {manifest['package_sha256']}, "
                f"got {package_sha256}"
            )

        # 3. Verify package size
        package_size = package_path.stat().st_size
        if package_size != manifest["package_size_bytes"]:
            raise ValueError(
                f"Package size mismatch: "
                f"expected {manifest['package_size_bytes']}, "
                f"got {package_size}"
            )

        # 4. Get signing key
        key_id = manifest["signing_key_id"]
        public_key = self._get_public_key(key_id)
        if public_key is None:
            raise ValueError(f"Unknown signing key: {key_id}")

        # 5. Verify signature
        with open(signature_path, "rb") as f:
            signature = f.read()

        # Signature is over the manifest file (which contains package hash)
        with open(manifest_path, "rb") as f:
            manifest_bytes = f.read()

        try:
            public_key.verify(signature, manifest_bytes)
            logger.info(
                "Update package signature verified",
                version=manifest["version"],
                key_id=key_id
            )
            return True
        except InvalidSignature:
            raise ValueError("Invalid signature - package may be tampered")

    def _get_public_key(self, key_id: str) -> Optional[ed25519.Ed25519PublicKey]:
        """Get public key by ID."""
        for key in self.trusted_keys["keys"]:
            if key["key_id"] == key_id and not key.get("revoked", False):
                # Check key validity period
                from datetime import datetime
                now = datetime.now()
                valid_from = datetime.fromisoformat(key["valid_from"].replace("Z", "+00:00"))
                valid_until = datetime.fromisoformat(key["valid_until"].replace("Z", "+00:00"))

                if not (valid_from <= now <= valid_until):
                    logger.warning(
                        "Key expired or not yet valid",
                        key_id=key_id,
                        valid_from=key["valid_from"],
                        valid_until=key["valid_until"]
                    )
                    continue

                # Load public key
                public_key_hex = key["public_key"]
                public_key_bytes = bytes.fromhex(public_key_hex)
                return ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

        return None

    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
```

### 1.6 Update Workflow with Verification

```python
async def download_and_verify_update(
    self,
    version: str,
    backend: UpdateBackend
) -> Path:
    """Download update and verify signature."""
    temp_dir = Path("/tmp/mcp-raspi-update")
    temp_dir.mkdir(exist_ok=True)

    try:
        # 1. Download manifest
        manifest_path = temp_dir / f"mcp-raspi-server-{version}.manifest.json"
        await backend.download_file(
            f"releases/{version}/manifest.json",
            manifest_path
        )

        # 2. Download signature
        signature_path = temp_dir / f"mcp-raspi-server-{version}.tar.gz.sig"
        await backend.download_file(
            f"releases/{version}/package.tar.gz.sig",
            signature_path
        )

        # 3. Download package
        package_path = temp_dir / f"mcp-raspi-server-{version}.tar.gz"
        await backend.download_file(
            f"releases/{version}/package.tar.gz",
            package_path
        )

        # 4. Verify signature
        verifier = SignatureVerifier(Path("/opt/mcp-raspi/keys"))
        verifier.verify_package(package_path, signature_path, manifest_path)

        logger.info(
            "Update package downloaded and verified",
            version=version,
            package_size=package_path.stat().st_size
        )

        return package_path

    except Exception as e:
        logger.error("Update download/verification failed", error=str(e))
        # Clean up temp files
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
```

### 1.7 Configuration

```yaml
updates:
  # ... existing config ...

  signature_verification:
    enabled: true  # MUST be true in production
    keys_path: "/opt/mcp-raspi/keys"
    allow_expired_keys: false  # Only for testing/emergencies
    require_manifest: true

    # Key rotation (Phase 2+)
    auto_update_keys: false
    keys_update_url: "https://releases.example.com/keys/trusted-keys.json"
```

---

## 2. Differential/Delta Updates (Phase 2+)

### 2.1 Overview

Delta updates transmit only changed files, reducing bandwidth and update time on slow/metered connections.

**Benefits**:
- 80-95% bandwidth reduction for minor updates
- Faster downloads on slow connections
- Lower data costs on cellular/metered connections
- Reduced load on update servers

**Tradeoffs**:
- More complex update logic
- Requires previous version on disk
- CPU overhead for delta computation/application

### 2.2 Delta Update Strategy

**Binary Diff Algorithm**: bsdiff/bspatch (efficient for binary files)
**Package Structure**: Full package + delta patches

```
releases/
  1.2.0/
    full/
      mcp-raspi-server-1.2.0.tar.gz      # Full package (15 MB)
      mcp-raspi-server-1.2.0.tar.gz.sig
      manifest.json
    delta/
      from-1.1.0/
        delta.bsdiff                      # Delta from 1.1.0 → 1.2.0 (2 MB)
        delta.bsdiff.sig
        delta-manifest.json
      from-1.1.5/
        delta.bsdiff                      # Delta from 1.1.5 → 1.2.0 (1 MB)
        delta.bsdiff.sig
        delta-manifest.json
```

### 2.3 Delta Manifest

```json
{
  "version": "1.2.0",
  "from_version": "1.1.5",
  "delta_type": "bsdiff",
  "delta_file": "delta.bsdiff",
  "delta_sha256": "d5e7f0a3...",
  "delta_size_bytes": 1048576,
  "full_package_sha256": "a3c5e8f1...",
  "signature_file": "delta.bsdiff.sig",
  "signing_key_id": "primary-2025",
  "created_at": "2025-12-03T12:00:00Z",
  "estimated_apply_time_seconds": 45,
  "bandwidth_savings_percent": 93
}
```

### 2.4 Delta Update Implementation

```python
import subprocess
from typing import Optional

class DeltaUpdater:
    """Handles differential/delta updates."""

    def __init__(self, releases_path: Path):
        self.releases_path = releases_path

    async def apply_delta_update(
        self,
        from_version: str,
        to_version: str,
        delta_path: Path,
        backend: UpdateBackend
    ) -> Path:
        """
        Apply delta patch to upgrade from one version to another.

        Returns:
            Path to resulting full package.
        """
        # 1. Locate current version package
        current_package = self.releases_path / from_version / "package.tar.gz"
        if not current_package.exists():
            raise ValueError(f"Current version package not found: {current_package}")

        # 2. Create output path for patched package
        output_package = Path(f"/tmp/mcp-raspi-update/patched-{to_version}.tar.gz")
        output_package.parent.mkdir(parents=True, exist_ok=True)

        # 3. Apply bsdiff patch
        logger.info(
            "Applying delta update",
            from_version=from_version,
            to_version=to_version,
            delta_size=delta_path.stat().st_size
        )

        try:
            subprocess.run(
                ["bspatch", str(current_package), str(output_package), str(delta_path)],
                check=True,
                capture_output=True,
                timeout=300  # 5 minute timeout
            )

            logger.info(
                "Delta update applied successfully",
                output_size=output_package.stat().st_size
            )

            return output_package

        except subprocess.CalledProcessError as e:
            logger.error(
                "Delta patch application failed",
                stderr=e.stderr.decode()
            )
            raise ValueError(f"Failed to apply delta patch: {e.stderr.decode()}")

    async def download_delta_or_full(
        self,
        from_version: str,
        to_version: str,
        backend: UpdateBackend
    ) -> tuple[Path, bool]:
        """
        Download delta update if available, otherwise full package.

        Returns:
            (package_path, is_delta) tuple.
        """
        # 1. Try to download delta manifest
        try:
            delta_manifest_url = f"releases/{to_version}/delta/from-{from_version}/delta-manifest.json"
            delta_manifest_path = Path(f"/tmp/mcp-raspi-update/delta-manifest.json")

            await backend.download_file(delta_manifest_url, delta_manifest_path)

            with open(delta_manifest_path, "r") as f:
                delta_manifest = json.load(f)

            # 2. Download delta patch
            delta_path = Path(f"/tmp/mcp-raspi-update/delta.bsdiff")
            delta_sig_path = Path(f"/tmp/mcp-raspi-update/delta.bsdiff.sig")

            await backend.download_file(
                f"releases/{to_version}/delta/from-{from_version}/delta.bsdiff",
                delta_path
            )
            await backend.download_file(
                f"releases/{to_version}/delta/from-{from_version}/delta.bsdiff.sig",
                delta_sig_path
            )

            # 3. Verify delta signature
            verifier = SignatureVerifier(Path("/opt/mcp-raspi/keys"))
            verifier.verify_package(delta_path, delta_sig_path, delta_manifest_path)

            # 4. Apply delta
            patched_package = await self.apply_delta_update(
                from_version,
                to_version,
                delta_path,
                backend
            )

            logger.info(
                "Delta update completed",
                bandwidth_saved_percent=delta_manifest["bandwidth_savings_percent"]
            )

            return (patched_package, True)

        except Exception as e:
            logger.warning(
                "Delta update unavailable or failed, falling back to full package",
                error=str(e)
            )

            # Fallback to full package download
            full_package = await self.download_full_package(to_version, backend)
            return (full_package, False)
```

### 2.5 Configuration

```yaml
updates:
  # ... existing config ...

  delta_updates:
    enabled: false  # Phase 2+
    prefer_delta: true  # Try delta first, fallback to full
    max_delta_age_days: 90  # Only use deltas from versions within 90 days
    bandwidth_threshold_mbps: 5  # Only use delta if bandwidth < 5 Mbps
```

---

## 3. Update Scheduling & Maintenance Windows (Phase 2+)

### 3.1 Overview

Scheduled updates allow administrators to control when updates occur, avoiding disruption during critical times.

**Use Cases**:
- IoT devices with predictable usage patterns
- Production systems with defined maintenance windows
- Devices on metered connections (update during off-peak)
- Multi-device fleets (coordinated updates)

### 3.2 Schedule Configuration

```yaml
updates:
  # ... existing config ...

  schedule:
    enabled: false  # Phase 2+
    mode: "maintenance_window"  # maintenance_window | immediate | manual

    # Maintenance windows (UTC)
    maintenance_windows:
      - day_of_week: "sunday"     # sunday, monday, ..., saturday
        start_time: "02:00"       # HH:MM in UTC
        duration_minutes: 120
        allow_reboot: true

      - day_of_week: "wednesday"
        start_time: "14:00"
        duration_minutes: 60
        allow_reboot: false       # Only non-reboot updates

    # Outside maintenance windows
    allow_security_updates: true   # Security patches always allowed
    allow_minor_updates: false     # Only in maintenance windows
    allow_major_updates: false     # Only in maintenance windows

    # Update window behavior
    defer_if_active: true          # Skip update if system is active
    activity_threshold:
      cpu_percent: 50              # Defer if CPU > 50%
      active_connections: 5        # Defer if > 5 MCP connections
      gpio_activity: true          # Defer if GPIO pins in use

    # Automatic check schedule
    check_interval_hours: 6        # Check for updates every 6 hours
    randomize_check: true          # Add random delay (0-60 min) to avoid thundering herd
```

### 3.3 Schedule Evaluation

```python
from datetime import datetime, time, timedelta
from typing import Optional
import random

class UpdateScheduler:
    """Evaluates update schedules and maintenance windows."""

    def __init__(self, config: UpdateScheduleConfig):
        self.config = config

    def can_update_now(
        self,
        update_type: str,  # security | minor | major
        requires_reboot: bool
    ) -> tuple[bool, Optional[str]]:
        """
        Check if update can proceed now.

        Returns:
            (can_update, reason) tuple.
        """
        if self.config.mode == "immediate":
            return (True, None)

        if self.config.mode == "manual":
            return (False, "Manual approval required")

        # maintenance_window mode
        now = datetime.utcnow()
        in_window, window = self._in_maintenance_window(now)

        # Security updates always allowed?
        if update_type == "security" and self.config.allow_security_updates:
            if requires_reboot and in_window and window.allow_reboot:
                return (True, None)
            elif not requires_reboot:
                return (True, None)
            else:
                return (False, "Reboot required outside maintenance window")

        # Must be in maintenance window
        if not in_window:
            next_window = self._next_maintenance_window(now)
            if next_window:
                return (False, f"Outside maintenance window. Next window: {next_window}")
            else:
                return (False, "No maintenance windows configured")

        # Check reboot requirement
        if requires_reboot and not window.allow_reboot:
            return (False, "Reboot required but not allowed in this window")

        # Check activity threshold
        if self.config.defer_if_active:
            is_active, activity_reason = self._check_system_activity()
            if is_active:
                return (False, f"System activity threshold exceeded: {activity_reason}")

        return (True, None)

    def _in_maintenance_window(
        self,
        dt: datetime
    ) -> tuple[bool, Optional[MaintenanceWindow]]:
        """Check if datetime is within a maintenance window."""
        day_name = dt.strftime("%A").lower()
        current_time = dt.time()

        for window in self.config.maintenance_windows:
            if window.day_of_week != day_name:
                continue

            start_time = time.fromisoformat(window.start_time)
            end_time = (
                datetime.combine(dt.date(), start_time) +
                timedelta(minutes=window.duration_minutes)
            ).time()

            if start_time <= current_time <= end_time:
                return (True, window)

        return (False, None)

    def _next_maintenance_window(self, from_dt: datetime) -> Optional[datetime]:
        """Calculate next maintenance window."""
        # Find next window within 7 days
        for days_ahead in range(7):
            check_date = from_dt + timedelta(days=days_ahead)
            day_name = check_date.strftime("%A").lower()

            for window in self.config.maintenance_windows:
                if window.day_of_week == day_name:
                    start_time = time.fromisoformat(window.start_time)
                    window_dt = datetime.combine(check_date.date(), start_time)

                    if window_dt > from_dt:
                        return window_dt

        return None

    def _check_system_activity(self) -> tuple[bool, Optional[str]]:
        """Check if system is currently active."""
        import psutil

        threshold = self.config.activity_threshold

        # CPU threshold
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > threshold.cpu_percent:
            return (True, f"CPU usage {cpu_percent:.1f}% > {threshold.cpu_percent}%")

        # Active MCP connections (check from server state)
        # active_connections = server.get_active_connection_count()
        # if active_connections > threshold.active_connections:
        #     return (True, f"{active_connections} active connections")

        # GPIO activity (check if any pins are being actively used)
        # if threshold.gpio_activity and self._has_gpio_activity():
        #     return (True, "GPIO pins in active use")

        return (False, None)

    def should_check_for_updates_now(self) -> bool:
        """Determine if we should check for updates now."""
        if not self.config.check_interval_hours:
            return False

        # Load last check time
        last_check = self._load_last_check_time()
        if last_check is None:
            return True

        elapsed_hours = (datetime.utcnow() - last_check).total_seconds() / 3600

        # Add randomization to avoid thundering herd
        interval = self.config.check_interval_hours
        if self.config.randomize_check:
            interval += random.uniform(0, 1)  # Add 0-60 minutes

        return elapsed_hours >= interval
```

### 3.4 MCP Tool for Schedule Management

```json
{
  "method": "manage.get_update_schedule",
  "params": {}
}
```

**Response**:

```json
{
  "result": {
    "enabled": true,
    "mode": "maintenance_window",
    "next_maintenance_window": {
      "start": "2025-12-08T02:00:00Z",
      "end": "2025-12-08T04:00:00Z",
      "allows_reboot": true
    },
    "pending_updates": [
      {
        "version": "1.2.0",
        "type": "minor",
        "requires_reboot": true,
        "can_install_now": false,
        "blocked_reason": "Outside maintenance window"
      }
    ],
    "last_check": "2025-12-03T12:00:00Z",
    "next_check": "2025-12-03T18:00:00Z"
  }
}
```

```json
{
  "method": "manage.override_update_schedule",
  "params": {
    "duration_minutes": 60,
    "reason": "Emergency security patch"
  }
}
```

---

## 4. Coordinated Multi-Device Updates (Phase 2+)

### 4.1 Overview

Coordinate updates across fleets of devices to maintain service availability and avoid simultaneous failures.

**Strategies**:
- **Rolling updates**: Update devices one-by-one or in small batches
- **Canary updates**: Update 1-5% first, monitor, then proceed
- **Blue-green**: Maintain two device groups, update one at a time
- **Staged rollout**: Gradual percentage increase over time

### 4.2 Fleet Update Configuration

```yaml
updates:
  # ... existing config ...

  fleet:
    enabled: false  # Phase 2+
    fleet_id: "production-sensors"
    coordination_backend: "redis"  # redis | consul | etcd | api
    coordination_url: "redis://fleet-coordinator.example.com:6379"

    # Update strategy
    strategy: "rolling"  # rolling | canary | blue_green | staged
    rolling:
      batch_size: 5          # Update 5 devices at a time
      batch_delay_minutes: 30  # Wait 30 min between batches
      max_failures: 2        # Abort if > 2 failures in batch

    canary:
      canary_percent: 5      # Update 5% first
      soak_time_hours: 24    # Monitor for 24 hours
      success_criteria:
        max_error_rate: 0.01  # < 1% error rate
        min_uptime_percent: 99  # > 99% uptime

    staged:
      stages:
        - percent: 10
          duration_hours: 24
        - percent: 50
          duration_hours: 48
        - percent: 100
          duration_hours: 0

    # Health checks during rollout
    health_check_interval_seconds: 60
    rollback_on_failure: true
```

### 4.3 Coordination Protocol

Devices coordinate via shared backend (Redis, Consul, etc.):

```python
import redis
from typing import Optional
import json

class FleetCoordinator:
    """Coordinates updates across device fleet."""

    def __init__(self, config: FleetUpdateConfig):
        self.config = config
        self.redis_client = redis.from_url(config.coordination_url)
        self.fleet_id = config.fleet_id
        self.device_id = self._get_device_id()

    async def request_update_slot(self, version: str) -> Optional[int]:
        """
        Request permission to update to version.

        Returns:
            Batch number if granted, None if should wait.
        """
        key = f"fleet:{self.fleet_id}:update:{version}"

        # Get current batch info
        batch_info = self.redis_client.hgetall(key)
        if not batch_info:
            # First device - initialize
            self.redis_client.hset(key, mapping={
                "current_batch": 0,
                "batch_size": self.config.rolling.batch_size,
                "devices_in_batch": 0,
                "failed_devices": 0
            })
            batch_info = self.redis_client.hgetall(key)

        current_batch = int(batch_info[b"current_batch"])
        devices_in_batch = int(batch_info[b"devices_in_batch"])
        failed_devices = int(batch_info[b"failed_devices"])

        # Check if too many failures
        if failed_devices >= self.config.rolling.max_failures:
            logger.error(
                "Fleet update aborted due to failures",
                failed_count=failed_devices
            )
            return None

        # Check if current batch is full
        if devices_in_batch >= self.config.rolling.batch_size:
            # Wait for next batch
            return None

        # Join current batch
        new_count = self.redis_client.hincrby(key, "devices_in_batch", 1)

        # Record this device in batch
        self.redis_client.sadd(
            f"fleet:{self.fleet_id}:update:{version}:batch:{current_batch}",
            self.device_id
        )

        logger.info(
            "Granted update slot",
            batch=current_batch,
            devices_in_batch=new_count
        )

        return current_batch

    async def report_update_result(
        self,
        version: str,
        batch: int,
        success: bool
    ) -> None:
        """Report update result to coordinator."""
        key = f"fleet:{self.fleet_id}:update:{version}"

        if success:
            # Record success
            self.redis_client.sadd(
                f"fleet:{self.fleet_id}:update:{version}:success",
                self.device_id
            )
        else:
            # Record failure
            self.redis_client.hincrby(key, "failed_devices", 1)
            self.redis_client.sadd(
                f"fleet:{self.fleet_id}:update:{version}:failed",
                self.device_id
            )

        # Check if batch is complete
        batch_devices = self.redis_client.scard(
            f"fleet:{self.fleet_id}:update:{version}:batch:{batch}"
        )
        completed_devices = (
            self.redis_client.scard(f"fleet:{self.fleet_id}:update:{version}:success") +
            self.redis_client.scard(f"fleet:{self.fleet_id}:update:{version}:failed")
        )

        # If batch complete, advance to next batch after delay
        # (This would typically be handled by a separate coordinator service)
```

### 4.4 Update Orchestration Service (Phase 2+)

Separate service that monitors fleet updates and advances batches:

```python
class FleetUpdateOrchestrator:
    """Centralized fleet update orchestrator."""

    def __init__(self, config: FleetUpdateConfig):
        self.config = config
        self.redis_client = redis.from_url(config.coordination_url)

    async def orchestrate_update(self, fleet_id: str, version: str) -> None:
        """Orchestrate rolling update across fleet."""
        logger.info("Starting fleet update", fleet_id=fleet_id, version=version)

        # Get fleet device list
        devices = self.redis_client.smembers(f"fleet:{fleet_id}:devices")
        total_devices = len(devices)

        batch_size = self.config.rolling.batch_size
        batch_delay = self.config.rolling.batch_delay_minutes * 60

        for batch_num in range((total_devices + batch_size - 1) // batch_size):
            logger.info(f"Starting batch {batch_num}")

            # Wait for batch to complete
            while True:
                batch_devices = self.redis_client.scard(
                    f"fleet:{fleet_id}:update:{version}:batch:{batch_num}"
                )
                completed = (
                    self.redis_client.scard(f"fleet:{fleet_id}:update:{version}:success") +
                    self.redis_client.scard(f"fleet:{fleet_id}:update:{version}:failed")
                )

                if completed >= min(batch_size, total_devices - batch_num * batch_size):
                    break

                await asyncio.sleep(30)

            # Check for failures
            failed_count = self.redis_client.scard(
                f"fleet:{fleet_id}:update:{version}:failed"
            )

            if failed_count >= self.config.rolling.max_failures:
                logger.error("Aborting fleet update due to failures")
                return

            # Advance to next batch
            self.redis_client.hset(
                f"fleet:{fleet_id}:update:{version}",
                "current_batch",
                batch_num + 1
            )
            self.redis_client.hset(
                f"fleet:{fleet_id}:update:{version}",
                "devices_in_batch",
                0
            )

            # Wait before next batch
            await asyncio.sleep(batch_delay)

        logger.info("Fleet update completed successfully")
```

---

## 5. Enhanced Rollback Features (Phase 2+)

### 5.1 Multi-Version Rollback

Keep multiple previous versions for more flexible rollback:

```yaml
updates:
  # ... existing config ...

  rollback:
    keep_versions: 3  # Keep last 3 versions (current + 2 previous)
    auto_rollback_after_failures: 3
    manual_rollback_allowed: true

    # Health monitoring for auto-rollback
    health_check:
      enabled: true
      interval_seconds: 60
      failure_threshold: 3  # 3 consecutive failures triggers rollback
      checks:
        - name: "mcp_server_responsive"
          type: "http"
          url: "http://127.0.0.1:8000/health"
          timeout_seconds: 5

        - name: "ipc_agent_responsive"
          type: "unix_socket"
          path: "/var/run/mcp-raspi/agent.sock"
          timeout_seconds: 3

        - name: "error_rate_acceptable"
          type: "metric"
          metric: "mcp.error_rate"
          threshold: 0.10  # < 10% error rate
```

### 5.2 MCP Tools for Rollback Management

```json
{
  "method": "manage.list_available_versions",
  "params": {}
}
```

**Response**:

```json
{
  "result": {
    "current_version": "1.2.0",
    "available_versions": [
      {
        "version": "1.2.0",
        "installed_at": "2025-12-03T12:00:00Z",
        "status": "current",
        "health": "healthy",
        "can_rollback_from": true
      },
      {
        "version": "1.1.5",
        "installed_at": "2025-11-15T10:00:00Z",
        "status": "previous_good",
        "health": "n/a",
        "can_rollback_to": true
      },
      {
        "version": "1.1.0",
        "installed_at": "2025-10-20T14:00:00Z",
        "status": "archived",
        "health": "n/a",
        "can_rollback_to": true
      }
    ]
  }
}
```

```json
{
  "method": "manage.rollback_to_version",
  "params": {
    "version": "1.1.5",
    "reason": "Critical bug in 1.2.0"
  }
}
```

---

## 6. Implementation Checklist

### Phase 1 (Current + Enhanced)
- ✅ Basic update download and installation
- ✅ Version tracking with version.json
- ✅ Single-version rollback (current → previous_good)
- ✅ `manage.check_for_updates` MCP tool
- ⚠️ **ADD**: Ed25519 signature verification
- ⚠️ **ADD**: Manifest file validation
- ⚠️ **ADD**: Trusted key management

### Phase 2+ (Future)
- ⏭️ Differential/delta updates with bsdiff
- ⏭️ Update scheduling and maintenance windows
- ⏭️ Activity-aware update deferral
- ⏭️ Coordinated multi-device fleet updates
- ⏭️ Rolling/canary/staged deployment strategies
- ⏭️ Multi-version rollback (keep 3+ versions)
- ⏭️ Automated health-based rollback
- ⏭️ Key rotation and transparency logs
- ⏭️ Update orchestration service
- ⏭️ Fleet update monitoring dashboard

---

**End of Document**

---

<!-- Merged from 10-addendum-error-recovery-strategies.md -->


## 1. Corrupted version.json Recovery

### 1.1 Overview

The `version.json` file tracks current and previous versions for update/rollback functionality. Corruption can prevent server startup or rollback.

**Causes**:
- Power loss during write
- Disk corruption
- Manual editing errors
- Concurrent write attempts

### 1.2 version.json Structure

```json
{
  "format_version": "1.0",
  "current_version": "1.2.0",
  "previous_good_version": "1.1.5",
  "update_history": [
    {
      "version": "1.2.0",
      "installed_at": "2025-12-03T12:00:00Z",
      "updated_from": "1.1.5",
      "status": "active"
    },
    {
      "version": "1.1.5",
      "installed_at": "2025-11-15T10:00:00Z",
      "updated_from": "1.1.0",
      "status": "previous_good"
    }
  ],
  "last_modified": "2025-12-03T12:00:05Z",
  "checksum": "sha256:a3c5e8f1..."
}
```

### 1.3 Detection & Recovery

```python
# src/mcp_raspi/updates/version_manager.py

import json
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

@dataclass
class VersionInfo:
    """Version information."""
    format_version: str
    current_version: str
    previous_good_version: Optional[str]
    update_history: list
    checksum: Optional[str] = None

class VersionManager:
    """Manages version.json with corruption recovery."""

    VERSION_FILE = Path("/opt/mcp-raspi/version.json")
    BACKUP_FILE = Path("/opt/mcp-raspi/version.json.backup")

    def __init__(self):
        self.version_info: Optional[VersionInfo] = None

    def load(self) -> VersionInfo:
        """
        Load version info with automatic recovery.

        Returns:
            VersionInfo object

        Raises:
            VersionFileCorruptedError: If recovery fails
        """
        try:
            # Try primary file
            return self._load_from_file(self.VERSION_FILE)

        except (json.JSONDecodeError, FileNotFoundError, ValueError) as e:
            logger.error(
                "version.json corrupted or missing",
                error=str(e),
                path=self.VERSION_FILE
            )

            # Try backup file
            try:
                logger.info("Attempting recovery from backup")
                version_info = self._load_from_file(self.BACKUP_FILE)

                # Restore primary from backup
                self._save_to_file(self.VERSION_FILE, version_info)
                logger.info("version.json restored from backup")

                return version_info

            except Exception as backup_error:
                logger.error(
                    "Backup recovery failed",
                    error=str(backup_error)
                )

                # Try reconstruction from filesystem
                try:
                    logger.info("Attempting reconstruction from filesystem")
                    version_info = self._reconstruct_from_filesystem()
                    self._save_to_file(self.VERSION_FILE, version_info)
                    self._save_to_file(self.BACKUP_FILE, version_info)
                    logger.info("version.json reconstructed")

                    return version_info

                except Exception as reconstruct_error:
                    logger.critical(
                        "Version file reconstruction failed",
                        error=str(reconstruct_error)
                    )

                    # Last resort: create minimal version file
                    return self._create_minimal_version_file()

    def _load_from_file(self, path: Path) -> VersionInfo:
        """
        Load and validate version info from file.

        Args:
            path: Path to version file

        Returns:
            VersionInfo object

        Raises:
            Various exceptions on failure
        """
        with open(path, 'r') as f:
            data = json.load(f)

        # Validate structure
        if "current_version" not in data:
            raise ValueError("Missing current_version field")

        # Verify checksum if present
        if "checksum" in data:
            # Extract checksum
            stored_checksum = data.pop("checksum")

            # Calculate checksum
            data_json = json.dumps(data, sort_keys=True)
            calculated_checksum = "sha256:" + hashlib.sha256(
                data_json.encode()
            ).hexdigest()

            if stored_checksum != calculated_checksum:
                raise ValueError(
                    f"Checksum mismatch: {stored_checksum} != {calculated_checksum}"
                )

            # Restore checksum
            data["checksum"] = stored_checksum

        # Create VersionInfo
        return VersionInfo(
            format_version=data.get("format_version", "1.0"),
            current_version=data["current_version"],
            previous_good_version=data.get("previous_good_version"),
            update_history=data.get("update_history", []),
            checksum=data.get("checksum")
        )

    def _save_to_file(self, path: Path, version_info: VersionInfo) -> None:
        """
        Save version info to file with checksum.

        Args:
            path: Path to save to
            version_info: Version info to save
        """
        data = {
            "format_version": version_info.format_version,
            "current_version": version_info.current_version,
            "previous_good_version": version_info.previous_good_version,
            "update_history": version_info.update_history,
            "last_modified": datetime.now().isoformat()
        }

        # Calculate checksum
        data_json = json.dumps(data, sort_keys=True)
        checksum = "sha256:" + hashlib.sha256(data_json.encode()).hexdigest()
        data["checksum"] = checksum

        # Atomic write (write to temp, then rename)
        temp_path = path.with_suffix('.tmp')

        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Sync to disk
        os.fsync(f.fileno())

        # Atomic rename
        temp_path.rename(path)

        logger.info("version.json saved", path=path)

    def _reconstruct_from_filesystem(self) -> VersionInfo:
        """
        Reconstruct version info by inspecting /opt/mcp-raspi/releases/.

        Returns:
            Reconstructed VersionInfo

        Raises:
            RuntimeError: If reconstruction fails
        """
        releases_dir = Path("/opt/mcp-raspi/releases")

        if not releases_dir.exists():
            raise RuntimeError("Releases directory not found")

        # Find all installed versions
        versions = []
        for version_dir in releases_dir.iterdir():
            if version_dir.is_dir():
                # Check if valid version (has bin/ directory)
                if (version_dir / "bin").exists():
                    versions.append({
                        "version": version_dir.name,
                        "path": version_dir,
                        "mtime": version_dir.stat().st_mtime
                    })

        if not versions:
            raise RuntimeError("No valid versions found in releases/")

        # Sort by modification time (most recent first)
        versions.sort(key=lambda v: v["mtime"], reverse=True)

        # Current version is most recent
        current_version = versions[0]["version"]

        # Previous good is second most recent (if exists)
        previous_good = versions[1]["version"] if len(versions) > 1 else None

        logger.info(
            "Reconstructed version info from filesystem",
            current=current_version,
            previous=previous_good,
            total_versions=len(versions)
        )

        return VersionInfo(
            format_version="1.0",
            current_version=current_version,
            previous_good_version=previous_good,
            update_history=[
                {
                    "version": v["version"],
                    "installed_at": datetime.fromtimestamp(
                        v["mtime"]
                    ).isoformat(),
                    "status": "reconstructed"
                }
                for v in versions
            ]
        )

    def _create_minimal_version_file(self) -> VersionInfo:
        """
        Create minimal version file as last resort.

        Returns:
            Minimal VersionInfo
        """
        # Try to detect version from current/ symlink
        current_link = Path("/opt/mcp-raspi/current")

        if current_link.exists() and current_link.is_symlink():
            target = current_link.resolve()
            current_version = target.name
        else:
            current_version = "unknown"

        logger.warning(
            "Created minimal version file",
            current_version=current_version
        )

        version_info = VersionInfo(
            format_version="1.0",
            current_version=current_version,
            previous_good_version=None,
            update_history=[]
        )

        # Save immediately
        self._save_to_file(self.VERSION_FILE, version_info)
        self._save_to_file(self.BACKUP_FILE, version_info)

        return version_info

    def save(self, version_info: VersionInfo) -> None:
        """
        Save version info with backup.

        Args:
            version_info: Version info to save
        """
        # Save to primary file
        self._save_to_file(self.VERSION_FILE, version_info)

        # Save backup
        self._save_to_file(self.BACKUP_FILE, version_info)
```

---

## 2. Partial Systemd Unit Update Recovery

### 2.1 Overview

During updates, systemd unit files may be partially updated (e.g., server updated but agent not), leading to inconsistent state.

**Scenarios**:
- Update interrupted mid-process
- Permission errors during unit file copy
- Systemd daemon-reload failure

### 2.2 Detection

```python
# src/mcp_raspi/updates/systemd_validator.py

from pathlib import Path
import subprocess

class SystemdValidator:
    """Validates systemd unit consistency."""

    EXPECTED_UNITS = [
        "mcp-raspi-server.service",
        "raspi-ops-agent.service"
    ]

    UNIT_DIR = Path("/etc/systemd/system")

    def validate_units(self, expected_version: str) -> list:
        """
        Validate systemd units are consistent.

        Args:
            expected_version: Expected version for all units

        Returns:
            List of validation issues (empty if valid)
        """
        issues = []

        for unit_name in self.EXPECTED_UNITS:
            unit_path = self.UNIT_DIR / unit_name

            # Check existence
            if not unit_path.exists():
                issues.append({
                    "unit": unit_name,
                    "issue": "missing",
                    "severity": "critical"
                })
                continue

            # Check ExecStart points to correct version
            with open(unit_path, 'r') as f:
                content = f.read()

            if f"releases/{expected_version}" not in content:
                issues.append({
                    "unit": unit_name,
                    "issue": "wrong_version",
                    "severity": "critical",
                    "expected": expected_version
                })

        # Check if systemd is aware of units
        try:
            result = subprocess.run(
                ["systemctl", "list-unit-files", "--type=service"],
                capture_output=True,
                text=True,
                check=True
            )

            for unit_name in self.EXPECTED_UNITS:
                if unit_name not in result.stdout:
                    issues.append({
                        "unit": unit_name,
                        "issue": "not_loaded",
                        "severity": "warning"
                    })

        except subprocess.CalledProcessError as e:
            logger.error("Failed to list systemd units", error=e.stderr)

        return issues

    def fix_units(self, target_version: str) -> None:
        """
        Fix systemd unit issues.

        Args:
            target_version: Version to fix units for
        """
        for unit_name in self.EXPECTED_UNITS:
            source_unit = (
                Path(f"/opt/mcp-raspi/releases/{target_version}/systemd")
                / unit_name
            )

            if not source_unit.exists():
                logger.error(
                    "Source unit file missing",
                    unit=unit_name,
                    version=target_version
                )
                continue

            # Copy unit file
            dest_unit = self.UNIT_DIR / unit_name

            try:
                shutil.copy2(source_unit, dest_unit)
                logger.info("Restored systemd unit", unit=unit_name)

            except Exception as e:
                logger.error(
                    "Failed to restore unit",
                    unit=unit_name,
                    error=str(e)
                )

        # Reload systemd
        try:
            subprocess.run(
                ["systemctl", "daemon-reload"],
                check=True,
                capture_output=True
            )
            logger.info("Systemd reloaded")

        except subprocess.CalledProcessError as e:
            logger.error("Systemd reload failed", error=e.stderr)
```

### 2.3 Update Safety Checks

```python
# Before update
def pre_update_checks(target_version: str) -> bool:
    """
    Run safety checks before update.

    Returns:
        True if safe to proceed
    """
    issues = []

    # 1. Check disk space
    root_usage = psutil.disk_usage("/")
    if root_usage.percent > 90:
        issues.append("Insufficient disk space (>90% used)")

    # 2. Check current units are valid
    validator = SystemdValidator()
    unit_issues = validator.validate_units(get_current_version())
    if unit_issues:
        issues.append(f"Current units invalid: {unit_issues}")

    # 3. Check target version exists
    target_path = Path(f"/opt/mcp-raspi/releases/{target_version}")
    if not target_path.exists():
        issues.append(f"Target version not found: {target_version}")

    # 4. Check version.json is valid
    try:
        version_manager = VersionManager()
        version_manager.load()
    except Exception as e:
        issues.append(f"version.json corrupted: {e}")

    if issues:
        logger.error("Pre-update checks failed", issues=issues)
        return False

    return True

# After update
def post_update_verification(target_version: str) -> bool:
    """
    Verify update succeeded.

    Returns:
        True if update successful
    """
    checks = []

    # 1. Verify units point to correct version
    validator = SystemdValidator()
    unit_issues = validator.validate_units(target_version)
    checks.append(("units", len(unit_issues) == 0, unit_issues))

    # 2. Verify services start
    for service in ["mcp-raspi-server", "raspi-ops-agent"]:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True
            )
            is_active = result.returncode == 0
            checks.append((f"service_{service}", is_active, result.stdout))

        except Exception as e:
            checks.append((f"service_{service}", False, str(e)))

    # 3. Verify version.json updated
    version_manager = VersionManager()
    version_info = version_manager.load()
    checks.append((
        "version_json",
        version_info.current_version == target_version,
        version_info.current_version
    ))

    # Log results
    all_passed = all(passed for _, passed, _ in checks)

    if not all_passed:
        logger.error(
            "Post-update verification failed",
            checks=[
                {
                    "check": name,
                    "passed": passed,
                    "detail": detail
                }
                for name, passed, detail in checks
            ]
        )

    return all_passed
```

---

## 3. Hung Operation Recovery

### 3.1 Overview

Operations may hang due to hardware issues, deadlocks, or external failures. The system must detect and recover from hung operations.

**Hung Operation Types**:
- GPIO operations (hardware failure)
- I2C operations (device not responding)
- Camera operations (device busy)
- Service operations (systemd hung)
- IPC calls (agent hung)

### 3.2 Operation Timeout Enforcement

```python
# src/mcp_raspi/server/operation_timeout.py

import asyncio
from typing import Callable, Any
from functools import wraps

def with_timeout(timeout_seconds: float):
    """
    Decorator to enforce operation timeout.

    Args:
        timeout_seconds: Timeout in seconds

    Raises:
        TimeoutError: If operation exceeds timeout
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )

            except asyncio.TimeoutError:
                logger.error(
                    "Operation timeout",
                    function=func.__name__,
                    timeout=timeout_seconds,
                    args=args[:2],  # Log first 2 args only
                )

                # Attempt cleanup
                await _cleanup_hung_operation(func.__name__, args, kwargs)

                raise TimeoutError(
                    f"Operation {func.__name__} timed out after {timeout_seconds}s"
                )

        return wrapper
    return decorator

async def _cleanup_hung_operation(
    func_name: str,
    args: tuple,
    kwargs: dict
) -> None:
    """
    Attempt to clean up hung operation.

    Args:
        func_name: Function name
        args: Function arguments
        kwargs: Function keyword arguments
    """
    logger.info("Attempting cleanup of hung operation", function=func_name)

    # Operation-specific cleanup
    if "gpio" in func_name:
        await _cleanup_gpio_operation(args, kwargs)
    elif "i2c" in func_name:
        await _cleanup_i2c_operation(args, kwargs)
    elif "camera" in func_name:
        await _cleanup_camera_operation()

async def _cleanup_gpio_operation(args: tuple, kwargs: dict) -> None:
    """Clean up hung GPIO operation."""
    # Release pin if possible
    if args and isinstance(args[0], int):
        pin = args[0]
        logger.info("Releasing GPIO pin", pin=pin)

        # Force release pin (best effort)
        try:
            await ipc_client.call("gpio_cleanup", {"pin": pin}, timeout=2.0)
        except:
            pass  # Ignore errors during cleanup

async def _cleanup_camera_operation() -> None:
    """Clean up hung camera operation."""
    logger.info("Releasing camera resources")

    try:
        await ipc_client.call("camera_reset", {}, timeout=2.0)
    except:
        pass

# Usage
@with_timeout(timeout_seconds=10.0)
async def gpio_write_pin(pin: int, value: int) -> None:
    """Write GPIO pin with timeout protection."""
    await ipc_client.call("gpio_write", {"pin": pin, "value": value})
```

### 3.3 Watchdog for Critical Operations

```python
# src/mcp_raspi/server/watchdog.py

import asyncio
from datetime import datetime, timedelta

class OperationWatchdog:
    """Monitors long-running operations and triggers recovery."""

    def __init__(self):
        self.monitored_operations = {}
        self.watchdog_task = None

    async def start(self) -> None:
        """Start watchdog monitoring."""
        self.watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def stop(self) -> None:
        """Stop watchdog."""
        if self.watchdog_task:
            self.watchdog_task.cancel()

    def register_operation(
        self,
        operation_id: str,
        max_duration_seconds: float,
        cleanup_handler: Callable
    ) -> None:
        """
        Register operation for watchdog monitoring.

        Args:
            operation_id: Unique operation ID
            max_duration_seconds: Maximum allowed duration
            cleanup_handler: Cleanup function to call if timeout
        """
        self.monitored_operations[operation_id] = {
            "started_at": datetime.now(),
            "max_duration": max_duration_seconds,
            "cleanup_handler": cleanup_handler,
            "expired": False
        }

    def unregister_operation(self, operation_id: str) -> None:
        """Mark operation as completed."""
        self.monitored_operations.pop(operation_id, None)

    async def _watchdog_loop(self) -> None:
        """Watchdog monitoring loop."""
        while True:
            await asyncio.sleep(5)  # Check every 5 seconds

            now = datetime.now()

            for op_id, op_info in list(self.monitored_operations.items()):
                if op_info["expired"]:
                    continue

                elapsed = (now - op_info["started_at"]).total_seconds()

                if elapsed > op_info["max_duration"]:
                    logger.error(
                        "Operation exceeded maximum duration",
                        operation_id=op_id,
                        elapsed=elapsed,
                        max_duration=op_info["max_duration"]
                    )

                    # Mark as expired
                    op_info["expired"] = True

                    # Execute cleanup
                    try:
                        await op_info["cleanup_handler"]()
                    except Exception as e:
                        logger.error(
                            "Cleanup handler failed",
                            operation_id=op_id,
                            error=str(e)
                        )

                    # Unregister
                    self.monitored_operations.pop(op_id, None)
```

---

## 4. System Recovery Procedures

### 4.1 Recovery from Crashed Services

```bash
#!/bin/bash
# /usr/local/bin/mcp-raspi-recover.sh
# Emergency recovery script

echo "MCP Raspi Emergency Recovery"
echo "============================"

# 1. Check service status
echo "Checking service status..."
systemctl status mcp-raspi-server raspi-ops-agent

# 2. Attempt restart
echo "Attempting service restart..."
systemctl restart raspi-ops-agent
sleep 2
systemctl restart mcp-raspi-server
sleep 5

# 3. Check if recovered
if systemctl is-active --quiet mcp-raspi-server; then
    echo "✓ Services recovered"
    exit 0
fi

# 4. Check for corrupted version.json
echo "Checking version.json..."
if ! python3 -c "import json; json.load(open('/opt/mcp-raspi/version.json'))" 2>/dev/null; then
    echo "⚠ version.json corrupted - restoring from backup"
    cp /opt/mcp-raspi/version.json.backup /opt/mcp-raspi/version.json
fi

# 5. Retry restart
systemctl restart raspi-ops-agent
systemctl restart mcp-raspi-server
sleep 5

if systemctl is-active --quiet mcp-raspi-server; then
    echo "✓ Services recovered after version.json restore"
    exit 0
fi

# 6. Try rollback to previous version
echo "⚠ Attempting rollback to previous version..."
/usr/local/bin/mcp-raspi-rollback.sh

# 7. Final check
if systemctl is-active --quiet mcp-raspi-server; then
    echo "✓ Services recovered after rollback"
    exit 0
else
    echo "✗ Recovery failed - manual intervention required"
    echo "Check logs: journalctl -u mcp-raspi-server -n 100"
    exit 1
fi
```

### 4.2 Automatic Recovery Systemd Unit

```ini
# /etc/systemd/system/mcp-raspi-server.service

[Unit]
Description=MCP Raspberry Pi Server
After=network.target raspi-ops-agent.service
Requires=raspi-ops-agent.service

[Service]
Type=simple
User=mcp-raspi
WorkingDirectory=/opt/mcp-raspi/current
ExecStart=/opt/mcp-raspi/current/bin/mcp-raspi-server --config /etc/mcp-raspi/config.yml

# Automatic restart on failure
Restart=on-failure
RestartSec=10s
StartLimitInterval=200s
StartLimitBurst=5

# If fails 5 times in 200s, run recovery script
ExecStartPre=/usr/local/bin/mcp-raspi-pre-start-check.sh
ExecStopPost=/usr/local/bin/mcp-raspi-post-stop-check.sh

# Resource limits
MemoryMax=250M
MemoryHigh=200M

[Install]
WantedBy=multi-user.target
```

---

## 5. Implementation Checklist

### Phase 1 (Current + Enhanced)
- ✅ Basic error handling
- ⚠️ **ADD**: version.json corruption recovery
- ⚠️ **ADD**: Systemd unit validation
- ⚠️ **ADD**: Operation timeouts
- ⚠️ **ADD**: Emergency recovery script

### Phase 2+ (Future)
- ⏭️ Operation watchdog
- ⏭️ Automated recovery procedures
- ⏭️ Health monitoring with auto-healing
- ⏭️ Crash dump collection
- ⏭️ Post-mortem analysis tools

---

**End of Document**
