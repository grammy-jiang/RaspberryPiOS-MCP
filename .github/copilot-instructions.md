# Copilot Coding Agent Instructions for `RaspberryPiOS-MCP`

This repo currently contains **design and documentation only** for a future Raspberry Pi MCP Server implementation. There is **no runnable code, no `pyproject.toml`, and no CI configuration yet**. Treat this repository as a specification source when generating new code in follow‑up changes.

You should **trust this file first** for repo‑level guidance. Only search the tree when something you need is not covered here or appears to be out of date.

---

## 1. High‑level overview

- Purpose: Design for a **Raspberry Pi MCP Server** that manages and observes Raspberry Pi OS devices, with:
  - safe device control (GPIO/I2C/camera, reboot/shutdown safeguards),
  - system information & metrics collection,
  - service & process management via systemd/psutil,
  - secure internet exposure via Cloudflare Tunnel + OAuth,
  - self‑update and rollback flows.
- Current state: **Docs‑only**; all behavior, interfaces and workflows are specified in `docs/` but not yet implemented.
- Planned implementation stack (from `README.md` + `docs/13-*`):
  - Language: **Python 3.11+** (Raspberry Pi OS).
  - Server/core: `fastapi`, `uvicorn`, `pydantic`, `pyyaml`, `pyjwt`.
  - System & metrics: `psutil`.
  - Device control: `gpiozero`, `smbus2`, optional `spidev`, `pyserial`, `picamera2`.
  - Service/process mgmt: `dbus-next` + `systemctl` wrappers.
  - Dev tools: `uv` (env + run), `pytest`, `pytest-asyncio`, `pytest-cov`, `tox`, `ruff`, `mypy`.
- Expected Python package layout (see `docs/13-python-development-standards-and-tools.md`):
  - `src/mcp_raspi/` – non‑privileged MCP server.
  - `src/mcp_raspi_ops/` – privileged ops agent.
  - `tests/` – unit/integration tests, with subdirs like `tests/server/`, `tests/ops/`, `tests/integration/`.

The numbered docs in `docs/` are the **canonical design** (01 requirements, 02 architecture, 05 MCP tools & schemas, 06–10 modules, 11 testing, 12 deployment, 13 Python standards, 14 configuration). When unsure about behavior, consult them in order rather than guessing.

---

## 2. Build, test, and run commands

Because this repo is docs‑only, there is currently **nothing to build or test**. However, the design already specifies the future standard commands. When you later add code and packaging files, follow these conventions exactly so that CI and other agents behave predictably.

Always assume the following baseline:

- **Python**: 3.11+.
- **Environment / dependency manager**: `uv`.
- **Test runner**: `pytest` (+ `pytest-asyncio`, `pytest-cov`).
- **Lint / format**: `ruff` (and optionally `mypy`).

Once `pyproject.toml` and `src/` exist, the typical local flow **should be**:

```bash
# 1) Create and activate virtualenv (local dev)
uv venv .venv
source .venv/bin/activate

# 2) Install project with dev extras (requires pyproject.toml)
uv pip install -e " .[dev] "

# 3) Run tests
uv run pytest
uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing

# 4) Lint & format
uv run ruff check src tests
uv run ruff format src tests

# 5) (Optional) Type checking
uv run mypy src tests

# 6) Run dev servers (once CLI entry points exist)
uv run mcp-raspi-server --config ./dev-config.yml
sudo uv run raspi-ops-agent --config ./dev-config.yml
```

Notes for agents:

- **Do not run these commands until you have added `pyproject.toml`, `src/`, and optional `tests/`**. In the current state they will fail because the repo has no code or packaging metadata.
- When you create `pyproject.toml`, respect the conventions in `docs/13-*`:
  - `requires-python = ">=3.11"`.
  - Use `src/` layout, define `mcp-raspi-server` and `raspi-ops-agent` as `project.scripts` entry points.
  - Provide a `dev` optional dependency group with `pytest`, `pytest-asyncio`, `pytest-cov`, `tox`, `ruff`, `mypy` etc.
- When adding CI (e.g., GitHub Actions), mirror the same commands under `uv`; see the CI skeleton in `docs/13-*`.

If commands fail due to missing tools (`uv`, `ruff`, etc.), prefer to **update docs and config** rather than inventing a different toolchain.

---

## 3. Project layout and key files

Current tree (simplified):

- `README.md` – concise overview, doc index, and **planned implementation stack & dev flow**. Read this first.
- `docs/` – design specs and runbooks (numbered 01–14):
  - `01-raspberry-pi-mcp-server-requirements-specification.md` – requirements & scope.
  - `02-raspberry-pi-mcp-server-high-level-architecture-design.md` – high‑level architecture, components, data flows.
  - `03-raspberry-pi-platform-and-resource-constraints-design-note.md` – Raspberry Pi platform & resource constraints.
  - `04-security-oauth-integration-and-access-control-design.md` – security model, OAuth/Cloudflare Access.
  - `05-mcp-tools-interface-and-json-schema-specification.md` – MCP tool namespaces, operations, JSON schemas.
  - `06-system-information-and-metrics-module-design.md` – system/metrics module.
  - `07-service-and-process-management-module-design.md` – service & process mgmt.
  - `08-device-control-and-reboot-shutdown-safeguards-design.md` – device control & shutdown safeguards.
  - `09-logging-observability-and-diagnostics-design.md` – logging & observability.
  - `10-self-update-mechanism-and-rollback-strategy-design.md` – self‑update & rollback.
  - `11-testing-validation-and-sandbox-strategy.md` – testing levels, sandbox modes, test matrix guidance.
  - `12-deployment-systemd-integration-and-operations-runbook.md` – deployment, systemd units, operations runbook.
  - `13-python-development-standards-and-tools.md` – **authoritative for Python layout, tooling & commands**.
  - `14-configuration-reference-and-examples.md` – central `AppConfig` model & config examples.
  - `acceptance-checklist.md` – post‑deploy smoke‑test checklist.
  - `test-matrix.md` – high‑level test matrix.

There are **no** project configuration files yet:

- No `pyproject.toml`, `setup.cfg`, `tox.ini`, `.ruff.toml`, `.pre-commit-config.yaml`, or GitHub Actions workflows.
- No `src/` or `tests/` directories.

When you introduce these for the first time, align them with the expectations in `docs/11`, `docs/12`, and `docs/13` to avoid future mismatches.

---

## 4. Validation, CI, and pre‑checkin expectations

The design already defines the _intended_ validation story:

- Pre‑commit / local checks (once code exists):
  - `uv run ruff check src tests`
  - `uv run ruff format src tests`
  - `uv run pytest`
  - `uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing`
  - optionally `uv run mypy src tests`
- CI (GitHub Actions) should, at minimum:
  - install via `uv pip install -e " .[dev] "`;
  - run lint + tests + coverage with the same commands as local dev.
- Additional validation steps come from docs:
  - `docs/11-*` and `docs/test-matrix.md` define testing levels (unit/integration/E2E), sandbox modes, and required coverage for safety‑critical modules.
  - `docs/12-*` and `docs/10-*` describe deployment, self‑update and rollback flows you should respect when adding scripts or systemd units.
  - `docs/acceptance-checklist.md` lists smoke tests to perform after deploying to a Pi.

When implementing changes, **mirror these planned checks**. Do not invent ad‑hoc scripts that diverge from the documented flows unless you also update the relevant docs.

---

## 5. Guidance for future agents making code changes

- Treat this repository as the **source of truth for specs**; code must follow the behavior, schemas, and error semantics described in `docs/` (especially 02, 04, 05, 06–10, 14).
- When adding Python code:
  - Use the `src/` layout and naming described in `docs/13-*`.
  - Implement a central `AppConfig` (Pydantic) model aligned with `docs/14-*` and the config layering rules in `docs/02-*` + `docs/13-*`.
  - Implement logging, audit, and error types (`ToolError` style) consistent with `docs/05-*` and `docs/09-*`.
  - Use dependency injection and mocks to keep unit tests independent of real hardware/OS; follow the guidance in `docs/11-*`.
- For dangerous operations (reboot/shutdown, OS/self‑update, device control), respect the sandbox and safety designs in `docs/08-*`, `docs/10-*`, and `docs/11-*`.
- When adding CI or deployment artifacts:
  - Use `uv` in CI;
  - follow the systemd layouts and paths from `docs/12-*`;
  - keep versioning and release flows compatible with `docs/10-*`.

Finally, **assume this file is correct and up‑to‑date** unless you find explicit contradictions in the docs or repo. Only fall back to broad searches (`grep`, `find`, code search tools) when you cannot answer a question from this file plus the `docs/` contents.
