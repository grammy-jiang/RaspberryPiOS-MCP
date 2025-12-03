# 13. Python Development Standards & Tooling

## 1. Document Purpose

- Standardize Python coding style, project layout, and dependency management in this repository.
- Define the tools and commands for development, testing, formatting, linting, and CI.
- Provide consistent engineering practices for implementing `mcp_raspi` and `mcp_raspi_ops`.

Preferred toolchain:

- `uv` – Python environment and dependency management.
- `ruff` – formatting and static checks.
- `pytest` + `pytest-asyncio` + `pytest-cov` – tests and coverage.
- `tox` – multi‑env testing and unified entry point (optional but recommended).

## 2. Python Version & Runtime

- Target version:
  - **Python 3.11+** (aligned with Raspberry Pi OS capabilities).
- Production environment:
  - Use system Python or official Python 3.11 builds.
  - Do not commit interpreters or virtual environments to the repository.

### 2.1 Version Policy

- Minimum Python version:
  - Should match the stable version on supported Raspberry Pi OS releases (typically 3.11.x).
- Constraints:
  - Avoid relying on micro‑version specific behavior.
  - In `pyproject.toml`:
    - Set `requires-python = ">=3.11"`.
  - In CI:
    - At least test 3.11.
- When extending support to newer versions (e.g. 3.12):
  - Add CI jobs for the new version.
  - Ensure all code and dependencies pass tests before updating `requires-python`.

### 2.2 Runtime Environments

- Development:
  - Recommended:

    ```bash
    uv venv .venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"
    ```

  - Do not commit `.venv/` to the repository (keep in `.gitignore`).
- Test/CI:
  - CI pipelines install Python and `uv`.
  - Use commands from documents 11 and 13 (§5, §7) to run tests and linting.
- Production:
  - Based on deployment mode (documents 10 and 12):
    - Python package + releases layout:
      - Use versioned virtual environments under `/opt/mcp-raspi/releases/<version>/venv`.
    - APT mode (Phase 2+):
      - Use system Python, managed by OS lifecycle.
  - Avoid production deployments with:
    - Dev virtual environments.
    - Unmanaged `pip install -e .` usage.

## 3. Project Layout & Packages

Align project layout with document 02:

- `src/mcp_raspi/` – MCP server (non‑privileged).
- `src/mcp_raspi_ops/` – privileged agent (`raspi-ops-agent`).
- `tests/` – unit and integration tests:
  - `tests/server/` – server‑related tests.
  - `tests/ops/` – privileged agent tests.
  - `tests/integration/` – cross‑module and E2E tests.

Use:

- `pyproject.toml` + `uv` for all dependencies.
- A `src/` layout to prevent tests from accidentally importing local modules outside the package.

The project should be publishable as a Python package (e.g. `mcp-raspi`), with CLI entry points defined in `pyproject.toml`:

```toml
[project]
name = "mcp-raspi"

[project.scripts]
mcp-raspi-server = "mcp_raspi.server.app:main"
raspi-ops-agent = "mcp_raspi_ops.main:main"
```

### 3.1 Configuration Model

Configuration conventions:

- A single top‑level configuration model (for example `AppConfig`) defined with Pydantic:
  - Contains all config sections:
    - Server.
    - Security and roles.
    - Tool policies.
    - GPIO/I2C whitelists.
    - Logging & metrics.
    - Update and OS update policies.
    - Testing/sandbox (document 14).
  - Provides safe defaults:
    - Localhost listen (`127.0.0.1`).
    - Dangerous tools disabled.
    - Conservative resource settings.

Config loading must follow the layering strategy from document 02:

1. Built‑in defaults.
2. Config file:
   - `/etc/mcp-raspi/config.yml` or a path provided via `--config`.
3. Environment variables:
   - Prefix `MCP_RASPI_`.
   - Nested fields using `__` separators (document 14).
4. Command line arguments:
   - Limited to high‑value overrides (for example `--config`, `--log-level`, `--debug`).

Unit tests:

- Must cover config layering behavior and precedence rules.

### 3.2 Module & Package Conventions

Suggested structure for `mcp_raspi`:

- `mcp_raspi.server.*`:
  - HTTP/MCP protocol surface.
  - JSON‑RPC layer.
  - Tool routing.
  - `ToolContext` and error mapping to JSON‑RPC.
- `mcp_raspi.modules.*`:
  - Domain services:
    - `system_info`, `metrics`, `services`, `processes`, `gpio`, `i2c`, `camera`, `update`, etc.
    - See documents 06–10 for design details.
- `mcp_raspi.models.*`:
  - Pydantic data models:
    - Match JSON Schemas defined in document 05.
- `mcp_raspi.ipc.*`:
  - IPC client interfaces and supporting types for communicating with `raspi-ops-agent`.
- `mcp_raspi.logging`:
  - Logging helpers and `AuditLogger`.

For `mcp_raspi_ops`:

- `mcp_raspi_ops.main`:
  - Entry point.
  - IPC loop.
- `mcp_raspi_ops.handlers.*`:
  - Operation handlers:
    - GPIO, I2C, camera, power, update, etc.
    - See documents 08–10.
- `mcp_raspi_ops.models.*`:
  - Pydantic models for IPC request/response bodies.

## 4. Coding Style & Conventions

### 4.1 General Style

Base style:

- Follow PEP 8 where not overridden by `ruff` formatting.
- Use:
  - Descriptive variable names.
  - Clear function and method names.
  - Docstrings for public APIs and complex functions.

Imports:

- Use absolute imports within project modules:
  - `from mcp_raspi.modules.system_info import SystemInfoService`
- Group imports:
  - Standard library.
  - Third‑party.
  - Local packages.

### 4.2 Type Hints

Type hints are required for:

- Public functions and methods:
  - Especially at module boundaries (between server, modules, and agent).
- Data models:
  - Pydantic models should be fully typed.

Guidelines:

- Avoid `Any` in public APIs.
- Use:
  - `dict[str, Any]` instead of `Dict` where possible (Python 3.11 typing).
  - `list[...]` instead of `List[...]` similarly.
- Use `mypy` (see §5.3) to enforce a baseline of type safety.

### 4.3 Error Handling & `ToolError`

Domain errors:

- Express using the project’s unified `ToolError` (or subclasses) instead of:
  - Building JSON‑RPC error objects directly.
  - Returning ad‑hoc status codes.

Example:

```python
from mcp_raspi.server.errors import ToolError

raise ToolError(
    error_code="invalid_argument",
    message="Pin number must be between 1 and 40",
    details={"pin": pin},
)
```

Tool handlers:

- Catch `ToolError` at the entry layer.
- Map to JSON‑RPC errors using:
  - Error mapping rules in document 05 §2.3 and §9.

Guidelines:

- Do not swallow exceptions in business logic:
  - Expected errors (invalid arguments, permission issues, unavailable resources):
    - Use `ToolError`.
  - Unexpected errors:
    - Let them propagate.
    - Ensure they are logged with full stack trace and mapped to `internal` error codes.
- Logging:
  - Use `mcp_raspi.logging.get_logger` and `AuditLogger` rather than the root `logging` logger:
    - Ensures consistent JSON structure and audit fields (document 09).

## 5. Formatting, Linting & Type Checking

### 5.1 Ruff – Linting & Formatting

Use `ruff` as the unified lint and format tool:

- Enable formatter (`ruff format`) with Black‑style behavior, configured via `.ruff.toml`.

Recommended commands:

```bash
uv run ruff check src tests
uv run ruff format src tests
```

Rule sets:

- Enable common error and style checks:
  - F, E, W, I, B families and others as appropriate.
- Configure `.ruff.toml`:
  - To fine‑tune rules to project needs.

### 5.2 Type Checking (`mypy`)

Use `mypy` for static type checking:

- Run via:

  ```bash
  uv run mypy src tests
  ```

Requirements:

- Public APIs (service classes, tool handlers, IPC client methods):
  - Must have explicit types and avoid `Any`.
- Internal fast‑iteration code:
  - May temporarily use weaker typing, but must pass `mypy` before merging.

## 6. Testing & Coverage

### 6.1 Pytest Usage

Testing guidelines:

- File names:
  - `test_*.py`.
- Use pytest fixtures for:
  - Temporary config.
  - Temp dirs.
  - Mock IPC clients.
- For async code:
  - Use `pytest-asyncio` and `@pytest.mark.asyncio`.

Recommended command:

```bash
uv run pytest
```

#### 6.1.1 Test Organisation

Directory structure:

- `tests/server/`:
  - `mcp_raspi` unit and integration tests.
- `tests/ops/`:
  - `mcp_raspi_ops` tests.
- `tests/integration/`:
  - Cross‑process and cross‑module tests (see document 11).

Naming:

- Test functions:
  - `test_<behavior>` with meaningful names, for example:
    - `test_update_server_autorollback_on_boot_failure`.
- For complex modules:
  - Group tests by class:
    - `class TestUpdateService: ...`.

#### 6.1.2 Fixtures & Mocks

Common fixtures:

- `app_config`:
  - Builds minimal `AppConfig` for different environments.
- `fake_ops_client`:
  - Simulates IPC client behavior on the server side.
- `tmp_version_dir`:
  - Simulates `/opt/mcp-raspi` and `version.json` directories.

Mocking:

- Use `monkeypatch` or `unittest.mock` for external dependencies:
  - `psutil`, `subprocess`, `gpiozero`, `smbus2`, `dbus-next`, etc.
- For critical paths (security, updates, device control):
  - Prefer explicit fake implementations with well‑defined behaviors.

### 6.2 Coverage

Use `pytest-cov` for coverage reports:

```bash
uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing
```

Targets:

- See document 11 §8 for global/per‑module coverage goals:
  - Overall line coverage ≥ 85%.
  - Critical modules around 90%+.

## 7. Run & Dev Commands

The following commands are the **target standard** for this project and should be reflected in `README.md` once code exists.

### 7.1 Local Development

```bash
# Create and activate virtual environment
uv venv .venv
source .venv/bin/activate

# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Run coverage
uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing

# Run lint and formatting
uv run ruff check src tests
uv run ruff format src tests

# Optional: type checking
uv run mypy src tests
```

### 7.2 Running Servers (Development)

After installing `mcp-raspi` as a package (editable or release):

```bash
# Start MCP server (non-privileged)
uv run mcp-raspi-server --config ./dev-config.yml

# Start privileged agent (may require sudo)
sudo uv run raspi-ops-agent --config ./dev-config.yml
```

Notes:

- For early development:
  - `uv run python -m mcp_raspi.server.app` and `uv run python -m mcp_raspi_ops.main` are also acceptable.
  - `README.md` should document the canonical entry points used in examples.

## 8. CI Integration

### 8.1 CI Guidelines

When adding CI (e.g. GitHub Actions):

- Use `uv` for dependency installation and test runs.
- CI commands should match local commands defined here to avoid drift.
- Minimum CI steps:
  - `uv run pytest`.
  - `uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing`.
  - `uv run ruff check src tests`.
  - Optional: `uv run mypy src tests`.

### 8.2 Example CI Skeleton

Example GitHub Actions workflow:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v1
      - name: Install dependencies
        run: uv pip install -e ".[dev]"
      - name: Lint
        run: uv run ruff check src tests
      - name: Unit tests with coverage
        run: uv run pytest --cov=mcp_raspi --cov=mcp_raspi_ops --cov-report=term-missing
```

In a real workflow:

- Follow document 11:
  - Split jobs into `lint`, `unit`, `integration`, `hardware-e2e`.
  - Add:
    - `mypy`.
    - Packaging checks (for example `uv build`).

## 9. Packaging & Publishing

### 9.1 Packaging

Project packaging:

- Target:
  - Publish `mcp-raspi` to PyPI or a private index.
- Installation:
  - `uv pip install mcp-raspi` (or equivalent).
- Installed CLI tools:
  - `mcp-raspi-server`.
  - `raspi-ops-agent`.

Build/publish example:

```bash
# Build distribution artifacts (requires configured build backend in pyproject.toml)
uv build  # or: python -m build

# Publish to PyPI or internal index (example)
uv publish  # or: twine upload dist/*
```

Build backend:

- To be chosen at implementation time:
  - For example `hatchling`, `setuptools`, `poetry-core`.
- Must:
  - Follow PEP 517/518.
  - Remain compatible with common tooling.

### 9.2 Versioning & Channels

Semantic versioning:

- `MAJOR.MINOR.PATCH`:
  - `MAJOR`:
    - Backward incompatible changes (may require API/schema versioning).
  - `MINOR`:
    - Backward‑compatible new features.
  - `PATCH`:
    - Backward‑compatible bug fixes.

Pre‑releases and channels:

- Use pre‑release markers (e.g. `1.1.0b1`) for beta builds.
- Map `channel` semantics (document 10) to versions:
  - `channel="beta"`:
    - Pre‑release versions.
  - `channel="stable"`:
    - Latest non‑pre‑release.

Self‑update and versions:

- `UpdateBackend` (document 10):
  - Should interpret `channel`/`target_version` according to the above.
- Version information:
  - Must remain consistent across:
    - `manage.get_server_status.version`.
    - `version.json.current_version`.

## 10. Alignment with Other Documents

This standard is tightly coupled with:

- `02-raspberry-pi-mcp-server-high-level-architecture-design.md`:
  - Project structure and module layout.
- `05-mcp-tools-interface-and-json-schema-specification.md`:
  - Tool handler interfaces, schemas, and data models.
- `06–11`:
  - Module designs.
  - Testing and sandbox strategy.
- `14-configuration-reference-and-examples.md`:
  - Configuration schema and environment mappings.

When changing tooling or commands (e.g. replacing dependencies or adjusting `uv` usage), update:

- This document (`13`).
- Testing & CI document (`11`).
- `README.md`:
  - Especially the “Planned Implementation Stack & Dev Flow” section.

