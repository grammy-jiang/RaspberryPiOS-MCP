# Test Matrix – Raspberry Pi MCP Server

This file complements the “Minimal Test Matrix” section in document 11 and helps plan test coverage across devices and environments.

## 1. Dimensions

- **Device dimension (`Device`)**
  - `low` – lower‑spec devices, e.g. Pi 3 / Zero 2W.
  - `high` – higher‑spec devices, e.g. Pi 4 / Pi 5.
- **Environment dimension (`Environment`)**
  - `dev` – development (local/VM).
  - `test` – test environment (real devices with sandbox enabled).
  - `preprod` – pre‑production environment (close to production configuration).
  - `prod` – production environment.
- **Functional dimension (`Function Area`)**
  - `system/metrics` – system information & metrics module (document 06).
  - `service/process` – service & process management (document 07).
  - `device/power` – device control & reboot/shutdown (document 08).
  - `logging/diagnostics` – logging & diagnostics (document 09).
  - `update/rollback` – self‑update & rollback (document 10).
  - `security/access` – security & access control (document 04).

## 2. Minimal Matrix (Recommended)

The table below shows recommended combinations that should have explicit test coverage.  
`✓` indicates that the combination should have concrete test scenarios.  
Annotations such as `(unit/ci)` indicate the primary test style.

| Device | Env     | system/metrics      | service/process      | device/power              | logging/diagnostics     | update/rollback               | security/access              |
|--------|---------|---------------------|----------------------|---------------------------|-------------------------|-------------------------------|------------------------------|
| any    | dev     | ✓ (unit/ci)         | ✓ (unit/ci)          | ✓ (unit/ci, sandbox)      | ✓ (unit/ci)             | ✓ (unit/ci, fake FS/IPC)      | ✓ (unit/ci, policy checks)   |
| low    | test    | ✓ (integration)     | ✓ (integration)      | ✓ (GPIO/I2C sandbox+hw)   | ✓ (logs query, metrics) | ✓ (update dry‑run, rollback)  | ✓ (role tests, rate limits)  |
| high   | test    | ✓ (integration/E2E) | ✓ (integration/E2E)  | ✓ (full device + reboot)  | ✓ (full logs + stress)  | ✓ (full update + rollback)    | ✓ (OAuth/Cloudflare)         |
| high   | preprod | ✓ (smoke)           | ✓ (smoke)            | ✓ (selected real ops)     | ✓ (smoke)               | ✓ (update on one node first)  | ✓ (policy + audit review)    |
| high   | prod    | ✓ (runtime monitor) | ✓ (runtime monitor)  | ✓ (guarded ops only)      | ✓ (runtime monitor)     | ✓ (carefully staged updates)  | ✓ (continuous enforcement)   |

Notes:

- `dev/any`:
  - Primarily covered by unit and integration tests in CI with simulated environments (no real hardware).
- `low/test` and `high/test`:
  - Must run on real devices:
    - `low/test` focuses on resource constraints and core functionality.
    - `high/test` carries most E2E tests, including self‑update and hardware operations.
- `preprod` and `prod`:
  - Focus on runtime monitoring and controlled update processes.
  - Actual scope depends on operational policies.

## 3. Mapping to Test Suites

Map combinations in the matrix to concrete test suites or markers (for example pytest `-m` markers):

- `unit` – covers most `dev/any` scenarios.
- `integration` – covers system integration in `test` environments.
- `e2e` – covers `high/test` and selected `preprod` scenarios.
- `smoke` – covers minimal acceptance cases in `preprod` and `prod` (see `docs/acceptance-checklist.md`).

In CI and operations tooling:

- Use markers or environment variables to:
  - Select appropriate subsets of tests for each environment.
  - Ensure that:
    - `unit` and `integration` run on every PR.
    - `e2e` and `smoke` run in scheduled or pre‑release pipelines, or on dedicated hardware.

