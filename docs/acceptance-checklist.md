# Acceptance Checklist – Raspberry Pi MCP Server

This checklist is based on:

- Document 11 §6 (Testing & Acceptance).
- Document 12 §6 (Operations Runbook).

Use it as a minimal smoke test after each deployment or significant upgrade. Record results and block release if any critical item fails.

## 1. Basic Startup & Connectivity

- [ ] `mcp-raspi-server` and `raspi-ops-agent` systemd units are `active (running)`:
  - `systemctl status mcp-raspi-server`
  - `systemctl status raspi-ops-agent`
- [ ] MCP server listens on the expected address and port (for example `127.0.0.1:8000`):
  - Confirm basic connectivity via local `curl` or an MCP client.
- [ ] If Cloudflare Tunnel is enabled:
  - `cloudflared` service is running.
  - MCP server is reachable through the protected public hostname.

## 2. Core Functionality

- [ ] `system.get_basic_info` returns reasonable hardware/OS information:
  - Hostname, model, CPU arch, OS and kernel versions.
- [ ] `system.get_health_snapshot` returns plausible CPU/memory/disk usage:
  - Values are broadly consistent with `top` / `free` / `df`.
- [ ] If metrics sampling is enabled:
  - `metrics.*` tools return data without persistent errors.

## 3. Security & Access Control

- [ ] Authorized user (`admin` role) can successfully call:
  - Read‑only tools (system info, metrics).
  - Allowed control tools (for example specific service or GPIO operations).
- [ ] Unauthorized users/roles (for example `viewer`) calling high‑risk tools (self‑update, shutdown, OS updates, power control):
  - Receive `permission_denied` or `failed_precondition` errors.
  - Corresponding calls are recorded in the audit log.
- [ ] OAuth/Cloudflare Access policies are correct:
  - Non‑authorized accounts cannot access the MCP hostname over the internet.

## 4. Logging & Diagnostics

- [ ] Application and audit log files exist and are writable:
  - Defaults: `/var/log/mcp-raspi/app.log`, `/var/log/mcp-raspi/audit.log`.
  - Recent entries show:
    - Startup.
    - Basic tool calls.
    - Permission denials for unauthorized actions.
- [ ] Log query tools work:
  - `logs.get_recent_app_logs` returns recent application log entries.
  - `logs.get_recent_audit_logs` returns recent audit entries.
- [ ] Health/diagnostic tools (or internal endpoints) report:
  - MCP server status OK.
  - Privileged agent reachable and healthy.

## 5. Device Control & Power Management

- [ ] In sandbox mode (for example `testing.sandbox_mode=full` or `partial`):
  - High‑risk operations (reboot/shutdown/OS update) only log intent and do not actually execute in test environments.
- [ ] In a non‑sandbox test environment:
  - For configured GPIO/I2C devices:
    - Reads/writes succeed within documented constraints.
    - Whitelists and parameter limits are enforced.
  - If reboot testing is allowed:
    - `system.reboot` successfully triggers a reboot.
    - After reboot, MCP server and agent are restored by systemd.
    - Logs and audit records before/after reboot are complete.

## 6. Self‑Update & Rollback

- [ ] In a test environment, perform at least one successful `manage.update_server`:
  - Call returns `status.status="succeeded"` (or equivalent success state).
  - `manage.get_server_status.version` changes to the target version.
  - `version.json.current_version` and `previous_good_version` are consistent with expectations.
- [ ] Simulate a failed update (in non‑production):
  - For example:
    - Use a deliberately broken version.
    - Or simulate network failure.
  - Ensure:
    - Update flow fails with an appropriate `error_code`.
    - Automatic or manual rollback restores `manage.get_server_status.version` to the previous known good version.
    - Logs and audit entries clearly show:
      - Failure cause.
      - Rollback operations.

## 7. Backup & Recovery (Spot Check)

- [ ] Verify that regular backups run successfully:
  - At minimum:
    - `/etc/mcp-raspi/`
    - `/var/lib/mcp-raspi/`
  - Confirm:
    - Recent backup timestamp.
    - Expected contents.
- [ ] In a test environment, validate restore procedure (see document 12 §6.4):
  - Simulate failure or fresh install on a test device.
  - Restore configuration and state from backups.
  - After restore, re‑run:
    - Startup checks.
    - Core functionality.
    - Security and logging checks from this checklist.
  - Confirm the system matches expected state.

---

For each release:

- Attach the results of this checklist to the release notes or change log.
- If any critical item fails:
  - Roll back or block the release.
  - Investigate and resolve the issue before retrying deployment.

