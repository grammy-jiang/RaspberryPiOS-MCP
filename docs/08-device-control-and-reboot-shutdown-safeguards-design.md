# 08. Device Control & Reboot/Shutdown Safeguards Design

## 1. Document Purpose

- Define the overall design for device control (GPIO, I2C, camera, etc.) and reboot/shutdown operations on Raspberry Pi.
- Focus on safety mechanisms to keep the system safe even when the MCP server is exposed to the public internet.
- Serve as the implementation guide for MCP tools:
  - `gpio.*`, `i2c.*`, `camera.*`
  - `system.reboot`, `system.shutdown`

This design is closely related to:

- `01-raspberry-pi-mcp-server-requirements-specification.md` – functional and non-functional requirements (especially FR‑9–FR‑16).
- `02-raspberry-pi-mcp-server-high-level-architecture-design.md` – privileged agent, dependency strategy, extension mechanisms.
- `04-security-oauth-integration-and-access-control-design.md` – security, OAuth, access control, and audit.
- `05-mcp-tools-interface-and-json-schema-specification.md` – MCP tools and JSON Schemas for `gpio.*`, `i2c.*`, `camera.*`, `system.*`.
- `06-system-information-and-metrics-module-design.md` and `07-service-and-process-management-module-design.md` – health checks, auditing, and integration with other modules.

## 2. Device Control Overview

### 2.1 Control Domains

- **GPIO & PWM**:
  - Digital input/output.
  - Pin mode configuration.
  - PWM control for fans, motors, LEDs, etc.
- **I2C / other buses**:
  - Device discovery and constrained read/write.
- **Camera**:
  - Photo capture (and Phase 2+ video recording).
- **Power & system control**:
  - Reboot and shutdown.

### 2.2 Goals

- Provide flexible hardware control suitable for automation and experimentation.
- Ensure that with default configuration, it is hard to damage hardware or make the system unusable.
- Require explicit enablement, rate limiting, and audit logging for all high-risk operations.

Dependency strategy (consistent with `02` §2.2):

- Prefer mature high-level Python libraries:
  - `gpiozero` for GPIO/PWM control.
  - `smbus2` for I2C access.
  - `picamera2` for CSI camera capture (photos/basic video).
- When a high-level library is unavailable or does not support a specific device, fall back to:
  - `/sys`, `/dev`, Raspberry Pi CLI tools (for example `libcamera-*`).
  - Mark the corresponding capability as degraded or unavailable in the capability matrix.

## 3. GPIO & PWM Design

### 3.1 Pin Abstraction

- Use logical BCM numbers to refer to GPIO pins consistently.
- Maintain a configuration-driven list of “allowed pins”:
  - Only pins in this whitelist can be controlled by the MCP server.
  - For pins not on the list, deny all read/write/PWM operations (or restrict to read-only if desired, see configuration).
- Optionally attach metadata to each pin in configuration:
  - Intended purpose (e.g. “fan control”, “LED”).
  - Expected logic levels.
  - Whether PWM is allowed.

### 3.2 Operations

- Read pin level:
  - `gpio.read_pin`, available only when the pin is configured as input or explicitly allowed for reading.
- Write pin level:
  - `gpio.write_pin`, supports optional `duration_ms` parameter to revert after a specified time.
- Configure mode and pull-up/pull-down:
  - `gpio.configure_pin` to change direction and internal pull resistor.
- PWM control:
  - `gpio.set_pwm` to set frequency and duty cycle on PWM-capable pins.

Detailed parameter and result schemas are defined in document 05.

### 3.3 Safeguards

- Default behavior:
  - Disable all GPIO output by default; allow only read-only operations unless explicitly enabled in configuration.
- Sensitive pins:
  - Mark pins used for power, system buses (I2C/SPI/UART), or other critical functions as non-configurable by default.
  - Require advanced users to explicitly enable them in configuration if necessary.
- PWM limits:
  - Enforce safe ranges for PWM frequency and duty cycle to avoid unusually high frequencies or extreme duty cycles that may stress hardware.
- Safe state on restart:
  - On MCP server restart or device reboot, ensure all MCP-managed GPIO pins are returned to a safe state:
    - For example input mode or low level.
    - This may rely on both Pi defaults and explicit re-initialization logic.

Electrical safety (non-code considerations):

- Documentation should remind users to:
  - Respect official Raspberry Pi voltage and current limits.
  - Avoid driving high-current loads directly from GPIO.
- For relays, motors, and similar peripherals:
  - Recommend isolation/driver boards.
  - Provide example wiring diagrams in user documentation (not necessarily in this design file).

### 3.4 Python Classes & Function Signatures (GPIO)

Define `GpioService` in `mcp_raspi.modules.gpio`:

```python
from typing import List, Optional
from mcp_raspi.models.gpio import GpioPinInfo


class GpioService:
    async def list_pins(self) -> List[GpioPinInfo]: ...

    async def configure_pin(self, pin: int, mode: str, pull: str = "none") -> GpioPinInfo: ...

    async def read_pin(self, pin: int) -> str: ...

    async def write_pin(
        self,
        pin: int,
        value: str,
        duration_ms: Optional[int] = None,
    ) -> GpioPinInfo: ...

    async def set_pwm(
        self,
        pin: int,
        frequency_hz: float,
        duty_cycle_percent: float,
    ) -> GpioPinInfo: ...
```

Implementation notes:

- `GpioPinInfo`:
  - Must match the schema for `gpio.list_pins` results in document 05 (`pins` array elements).
- Dependencies:
  - Prefer `gpiozero` for pin state and PWM control.
  - If `gpiozero` is not available, fall back to lower-level backends such as `RPi.GPIO` or `/sys/class/gpio`, following the dependency fallback rules in document 02.
- Before performing any write operations (`configure_pin`, `write_pin`, `set_pwm`), `GpioService` must check:
  - The pin is in the allowed list from configuration.
  - The requested mode and parameters are within safe ranges (frequency, duty cycle, etc.).
  - The current caller has sufficient permissions:
    - Use the security module and `ToolContext` roles to verify authorization.

## 4. I2C & Other Buses Design

### 4.1 Address & Bus Whitelisting

- For each I2C bus, define allowed addresses or address ranges in configuration.
- By default:
  - Only detected device addresses may be operated on.
- For writes:
  - Be especially conservative.
  - Allow per-device enablement in configuration for write operations.

### 4.2 Operations

- `i2c.list_buses`:
  - List available I2C bus numbers.
- `i2c.scan_bus`:
  - Scan the specified bus for reachable device addresses.
- `i2c.read`:
  - Read a bounded number of bytes from a bus/address (and optional register).
- `i2c.write`:
  - Write a bounded number of bytes to a bus/address (and optional register).

### 4.3 Safeguards

- Limit the maximum number of bytes per read/write:
  - To avoid long blocking operations.
- Record write operations:
  - Optionally enable “double-write confirmation” in tests or with particularly sensitive devices.
- For certain devices (for example EEPROMs or controllers that can brick the system):
  - Completely forbid writes.

In configuration (document 14), each I2C address should have a mode:

- `read_only` – only reads are allowed.
- `full` – reads and writes allowed.
- `disabled` – no access allowed.

In `mcp_raspi.modules.i2c` define:

```python
from typing import List
from mcp_raspi.models.i2c import I2cBusInfo, I2cDeviceInfo


class I2cService:
    async def list_buses(self) -> List[I2cBusInfo]: ...

    async def scan_bus(self, bus: int) -> List[I2cDeviceInfo]: ...

    async def read(
        self,
        bus: int,
        address: int,
        register: int,
        length: int,
    ) -> bytes: ...

    async def write(
        self,
        bus: int,
        address: int,
        register: int | None,
        data: bytes,
    ) -> None: ...
```

Implementation notes:

- `I2cBusInfo` and `I2cDeviceInfo`:
  - Must match the schemas for `i2c.list_buses` and `i2c.scan_bus` results in document 05.
- Dependencies:
  - Prefer `smbus2` for I2C access.
  - If `smbus2` is unavailable, fall back to `/dev/i2c-*` device nodes with appropriate permission checks and error handling.
- For `read` / `write`:
  - Implement mode and address checks (`read_only` / `full` / `disabled`) before performing any I/O.
  - Completely forbid writes to `disabled` or specially-protected addresses (for example EEPROMs).
  - Configure reasonable timeouts and optional retries to avoid prolonged blocking.

## 5. Camera Control

### 5.1 Operations

- `camera.take_photo`:
  - Capture a photo and save it to a configured directory.
- Future extensions (Phase 2+):
  - `camera.start_recording` / `camera.stop_recording` for short video recording.

### 5.2 Storage & Privacy

- Media storage:
  - The media root directory is explicitly configured, with appropriate filesystem permissions (see document 14).
  - Path traversal must be prevented; all outputs must be confined within this directory.
- Returned paths:
  - Prefer relative paths or virtual paths in results.
  - Avoid exposing full filesystem structure unless absolutely necessary.
- HTTP or other media serving:
  - If media is exposed through HTTP, it must respect authentication and potentially include time-limited access URLs.

In `mcp_raspi.modules.camera` define:

```python
from mcp_raspi.models.camera import PhotoCaptureResult


class CameraService:
    async def take_photo(self, resolution: str, fmt: str) -> PhotoCaptureResult: ...
```

Implementation notes:

- `PhotoCaptureResult`:
  - Must match the schema for `camera.take_photo` in document 05 (`file_path` and optional `public_url`).
- Dependencies:
  - Use `picamera2` where available for image capture.
  - If not available, fall back to CLI tools such as `libcamera-still` and place the resulting files under the configured media root.
- Security and safety:
  - Always ensure media files are stored under the configured root directory.
  - Return relative `file_path` values; higher layers (reverse proxy, static file server) derive `public_url`.
  - Apply authorization and rate limits (via the security module) to prevent excessive capture in a short period.

## 6. Reboot & Shutdown Design

### 6.1 Reboot

- `system.reboot` is implemented via the privileged agent executing system-level reboot commands.
- Key design points:
  - Optional `delay_seconds` parameter:
    - Allows clients to inform users about upcoming reboot.
  - Record reboot reason:
    - From the tool parameters and/or internal context (for example triggered by update).
  - Audit logging:
    - Record entries before/after scheduling the reboot.
  - Rate limiting:
    - Enforce limits such as “at most one reboot per hour”.

### 6.2 Shutdown

- `system.shutdown` is higher-risk than reboot and requires stronger safeguards:
  - Disabled by default; only available when explicitly enabled in configuration.
  - Requires the highest role (for example `admin`).
  - Optionally requires an extra confirmation code:
    - For example, a random code supplied in the request and shown to the human user for confirmation.
  - Must be audited in detail and rate-limited.

Define `PowerService` in `mcp_raspi.modules.system_power`:

```python
from typing import Optional


class PowerService:
    async def reboot(self, reason: Optional[str], delay_seconds: int) -> None: ...

    async def shutdown(
        self,
        reason: Optional[str],
        delay_seconds: int,
        force: bool = False,
    ) -> None: ...
```

### 6.3 Failure Handling

On failure to schedule reboot/shutdown (for example insufficient permissions, missing commands):

- Return clear error codes and messages via `ToolError`.
- Write high-priority logs, prompting administrators to inspect configuration or system state.

If the MCP server fails to restart after a reboot:

- Resolution falls to external system monitoring (systemd configuration, external monitoring tools) or manual intervention.

Implementation notes:

- Parameter and result schemas for `system.reboot` / `system.shutdown`:
  - Must match the definitions in document 05.
  - `PowerService` is responsible for constructing and executing safe system commands (`systemctl reboot`, `systemctl poweroff`, etc.) based on the parameters.
- All power operations must be executed via the privileged agent:
  - The MCP server must not invoke reboot/shutdown commands directly.
- Before invoking:
  - Check caller role (only `admin` can execute shutdown and similar high-risk operations).
  - Apply rate limiting (avoid reboot storms).
- After invoking:
  - Write audit logs including caller, reason, delay, and result.
  - On failure, raise `ToolError` with `failed_precondition` or `unavailable`, so the JSON‑RPC layer can build the error response.

## 7. Integration with Privileged Agent

### 7.1 Responsibilities

Role separation:

- MCP server (unprivileged):
  - Authenticate and authorize callers (document 04).
  - Check whitelists, rate limits, and parameter validity for device and power operations.
  - Construct IPC requests for privileged operations and send them to `raspi-ops-agent`.
  - Map agent responses into tool result models or `ToolError`.
- `raspi-ops-agent` (privileged):
  - Receive constrained operation requests from the MCP server.
  - Execute hardware access or power commands in a privileged environment.
  - Perform a second layer of safety checks:
    - Ranges and whitelists for pins, I2C addresses, resolutions, and delays.
  - Return structured results or errors to the MCP server.

### 7.2 IPC Operations & Mapping

At the IPC protocol level (see `02` §6), suggested operation names and mappings:

- GPIO:
  - `gpio.read`, `gpio.write`, `gpio.configure`, `gpio.pwm`
  - Mapped from `gpio.read_pin`, `gpio.write_pin`, `gpio.configure_pin`, `gpio.set_pwm`.
- I2C:
  - `i2c.read`, `i2c.write`, `i2c.scan`
  - Mapped from `i2c.read`, `i2c.write`, `i2c.scan_bus`.
- Camera:
  - `camera.capture`
  - Mapped from `camera.take_photo`.
- Power:
  - `system.reboot`, `system.shutdown`
  - Mapped directly from tools with the same names.

Example flow (`gpio.write_pin`):

1. Tool handler `handle_gpio_write_pin`:
   - Parses parameters into a Pydantic model and performs whitelist and role checks.
2. Constructs IPC request:
   - For example: `{"operation": "gpio.write", "params": {"pin": 17, "value": "high", "duration_ms": 1000}, ...}`.
3. In `raspi-ops-agent`, `GpioHandler.write`:
   - Re-validates allowed pin and mode.
   - Uses `gpiozero` or low-level backend to perform the write.
   - Returns either success data or a structured error (including internal error codes and details).
4. MCP server:
   - Maps success data to `GpioPinInfo` and returns it as the MCP tool result.
   - On error, constructs a `ToolError` which is then represented as a JSON‑RPC error (document 05).

### 7.3 Parameter Validation & Safety

Two layers of validation:

- **Server-side**:
  - Validate MCP tool parameters with JSON Schema and Pydantic models.
  - Apply configuration-driven whitelists and rate limits:
    - Reject obviously invalid pins/addresses/modes.
- **Agent-side**:
  - Even if the server has validated parameters, the agent must perform minimal safety checks:
    - Pin/address falls within allowed ranges.
    - Modes, lengths, and resolutions are acceptable for the hardware.
    - Power operation parameters (for example `delay_seconds`) are within configured safe ranges.
  - On violation:
    - Refuse execution and return an error to avoid dangerous operations even in the presence of server or configuration bugs.

### 7.4 Error Propagation

On the agent side:

- Errors may arise from hardware failures, permission issues, devices not present, etc.
- The agent must:
  - Return structured error information in its IPC response:
    - Error codes.
    - Human-readable messages.
    - Additional diagnostic details where safe and useful.

On the MCP server side:

- Map agent errors to `ToolError` with appropriate symbolic error codes:
  - For example `failed_precondition`, `unavailable`, `internal` (see document 05 §9.1).
- The JSON‑RPC layer converts `ToolError` into standard JSON‑RPC error objects as described in document 05 §2.3.

This layered approach:

- Keeps device control modules focused on domain logic and safety policies.
- Centralizes JSON‑RPC protocol handling in the shared server layer.

### 7.5 Testing Hooks

To support testing and simulation:

- On the MCP server:
  - Provide injectable IPC client interfaces for `gpio.*`, `i2c.*`, `camera.*`, and power operations.
  - For unit tests:
    - Replace these with fake/mock IPC clients so tests can verify server logic without a real privileged agent.
- On the agent:
  - Provide pluggable low-level access implementations:
    - For example, virtual GPIO/I2C devices or in-memory simulations.
  - This allows automated tests in environments without real hardware.
- Implement injection via:
  - Dependency injection and configuration flags, not ad-hoc test-only branches in production code.

### 7.6 Python IPC Client Interface

On the MCP server side, define a shared async IPC client in `mcp_raspi.ipc.client`:

```python
from typing import Any, Dict, Optional
from pydantic import BaseModel
from mcp_raspi.server.context import ToolContext


class OpsAgentRequest(BaseModel):
    id: str
    operation: str
    timestamp: str
    caller: Dict[str, Any]
    params: Dict[str, Any]


class OpsAgentResponse(BaseModel):
    id: str
    status: str  # "ok" | "error"
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class OpsAgentClient:
    async def call(
        self,
        ctx: ToolContext,
        operation: str,
        params: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> OpsAgentResponse: ...
```

Implementation notes:

- Transport:
  - Use a Unix domain socket to communicate with `raspi-ops-agent`.
  - Follow the request/response JSON envelope and framing defined in `02` §6.2–6.3.
- Correlation:
  - `id` should be a request-unique identifier (for example derived from the JSON‑RPC request ID or a new UUID).
  - This enables correlation in logs and audits.
- Caller metadata:
  - `caller` is built from `ToolContext` and includes:
    - User identity.
    - Roles.
    - Source (for example ChatGPT session).
  - The agent can use this for minimal extra audit and safety checks.
- Timeouts:
  - Default timeout loaded from `AppConfig.ipc.request_timeout_seconds` (document 14).
  - Callers may override per-operation timeouts for operations like reboot/shutdown.
- Error mapping:
  - All low-level I/O errors (connection failure, timeout, malformed response) should be converted to `ToolError` with `error_code="unavailable"` or similar.

The IPC client should be easily replaceable in tests:

- For example via dependency injection or a factory that can return fake clients.

### 7.7 Agent‑Side Handler Structure

On the `raspi-ops-agent` side, define a simple operation router in `mcp_raspi_ops.handlers`:

```python
from typing import Any, Dict, Callable, Awaitable

HandlerFunc = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class OpsRouter:
    def __init__(self) -> None:
        self._handlers: Dict[str, HandlerFunc] = {}

    def register(self, operation: str, handler: HandlerFunc) -> None: ...

    async def dispatch(
        self,
        operation: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]: ...
```

Recommended operations to register (consistent with §7.2):

- `gpio.read`, `gpio.write`, `gpio.configure`, `gpio.pwm`
- `i2c.read`, `i2c.write`, `i2c.scan`
- `camera.capture`
- `system.reboot`, `system.shutdown`

Implementation notes:

- Each handler (for example `GpioHandler.write`, `I2cHandler.read`, `CameraHandler.capture`, `PowerHandler.reboot`) must:
  - Parse raw `params` into appropriate Pydantic models (aligned with server-side tool parameter schemas).
  - Perform safety checks (whitelists, ranges, and power policies).
  - Call the corresponding hardware library or system command.
  - Return a structured `Dict[str, Any]` as `OpsAgentResponse.data`.
- Error handling:
  - Capture all exceptions and convert them into a consistent error object structure:
    - With internal error code, message, and optional technical details.
  - Populate `OpsAgentResponse.error` accordingly.
- Protocol separation:
  - The agent is unaware of JSON‑RPC.
  - It only implements its own IPC protocol and interacts with hardware/system calls.
  - JSON‑RPC mapping is fully handled by the MCP server (aligned with document 05).

This design allows Phase 2+ to add new privileged operations without breaking existing device and power control.

## 8. Testing & Safety Validation

Testing for this module must strictly follow TDD:

- Before implementing or changing behavior for GPIO/I2C/camera/power operations:
  - Write or update tests to describe the expected behavior and safety invariants.
  - Then implement or adjust the code until tests pass.

### 8.1 Unit Tests (Self-contained, Mock-based)

Configuration and parameter validation:

- Tests must cover:
  - Loading and validation of GPIO whitelists, I2C device modes, camera directories, rate limits, and related configuration.
  - Use mocks/stubs for:
    - `gpiozero`, `smbus2`, `picamera2`.
    - Reboot/shutdown system calls (for example monkeypatching the low-level functions or the agent handlers).
  - Unit tests must not rely on real hardware or actual system commands.

Behavior and error paths:

- For each public method in `GpioService`, `I2cService`, `CameraService`, and `PowerService`:
  - At least one success-path test:
    - Valid pin/address/parameters → expected result model.
  - At least one error-path test:
    - Out-of-whitelist pin/address, invalid argument, or underlying library failure → `ToolError` with an appropriate `error_code`, such as:
      - `invalid_argument`
      - `permission_denied`
      - `failed_precondition`
- Model validation:
  - Verify that models such as `GpioPinInfo`, `I2cBusInfo`, `PhotoCaptureResult`:
    - Match the JSON Schemas in document 05 (field names, types, required/optional).
    - Raise validation errors for invalid input.

### 8.2 Hardware & Integration Tests

Hardware-backed integration tests (on appropriate test devices):

- GPIO/PWM:
  - In a test environment with LEDs, fans, relays, etc., verify:
    - `gpio.list_pins` shows correct pin modes and states.
    - `gpio.configure_pin`, `gpio.write_pin`, `gpio.set_pwm` change physical behavior as expected.
    - After service restart or device reboot, MCP-managed pins return to safe states.
- I2C:
  - With real I2C sensors/devices (for example temperature/humidity sensors), verify:
    - `i2c.list_buses`, `i2c.scan_bus`, `i2c.read`, `i2c.write` behave as designed.
  - In controlled setups:
    - Test `read_only` / `full` / `disabled` modes.
    - Confirm that operations on disabled addresses are rejected with appropriate errors.
- Camera:
  - On devices with cameras, verify:
    - `camera.take_photo` produces image files under the configured media root, with `file_path` being relative.
    - When cameras are unavailable or initialization fails:
      - The service raises `ToolError`.
      - The capability matrix marks camera capabilities as unavailable.
- Power control:
  - In a test environment, verify reboot behavior:
    - `system.reboot` triggers system reboot and the MCP server is restarted via systemd.
    - Audit logs contain the reboot reason and caller information.
  - For `system.shutdown`:
    - Tests must be performed only in highly controlled environments or via a “sandbox mode” that records intent without actually powering off.

### 8.3 Security & Abuse‑Resilience Tests

Authorization and rejection behavior:

- From unauthorized accounts:
  - Attempt calls to `gpio.*`, `i2c.*`, `camera.*`, and power tools.
  - Confirm:
    - Operations are denied with `permission_denied`.
    - Audit logs record caller identity, tool name, and rejection reason.

Abuse and rate limiting:

- Simulate high-frequency GPIO/I2C and power operations:
  - Confirm rate limits trigger and return `resource_exhausted`.
  - Confirm logs and alerts are generated where configured.
- Simulate privileged agent unavailability (IPC failures):
  - Confirm device control and power operations return `unavailable`.
  - Confirm errors are logged with sufficient detail for diagnosis.

### 8.4 Documentation & Configuration Validation

- Provide example configurations for:
  - Test environments.
  - Production environments.
  - Differences may include:
    - GPIO/I2C whitelists.
    - Camera media paths.
    - Rate limit values.
- In tests:
  - Validate that these configurations load correctly and that behavior matches expectations.
- Keep user-facing documentation and default configuration aligned with implementation:
  - Especially around dangerous operations, risk descriptions, and safeguards.
- When adding new device control features or changing safety policies:
  - Update tests and documentation first.
  - Then update implementation, keeping TDD and documentation-driven development in place.

## 9. Implementation Checklist

- GPIO configuration:
  - Define Pydantic models and YAML schema for GPIO configuration, mapping “allowed pins” and related metadata.
  - On startup, load and validate configuration.
  - Enforce:
    - Non-whitelisted pins are read-only or entirely inaccessible.
  - Integrate these rules with the security module:
    - Check both roles and pin whitelists in `GpioService` entry points.
- I2C address and mode checks:
  - Implement logic for `read_only` / `full` / `disabled` modes.
  - Validate address ranges and modes in both server and agent layers.
  - Add extra protection or complete write bans for particularly sensitive addresses (for example EEPROMs).
- GPIO safe recovery:
  - In `GpioService` and/or the agent:
    - Ensure that on MCP server or agent crash/restart, all managed pins are restored to safe states (e.g. input/low).
  - Reflect the recovery strategy in `SystemInfoService` or the capability matrix to aid diagnostics.
- Power command encapsulation:
  - In the privileged agent:
    - Implement safe wrappers for reboot/shutdown:
      - Only allow predefined commands (`systemctl reboot`, `systemctl poweroff`, etc.).
      - Reject arbitrary shell commands or arbitrary arguments.
    - Perform range checks on `delay_seconds`, `force`, and related parameters.
- Auditing of power operations:
  - For `system.reboot` and `system.shutdown`, enforce audit logging:
    - Include caller identity, reason, delay, and actual outcome.
  - In tests:
    - Verify audit entries in various scenarios (success, failure, denied).
- Error handling and JSON‑RPC mapping:
  - Follow the error-handling conventions in document 05:
    - Represent device and power errors as `ToolError` (or subclasses).
    - Centralize conversion from `ToolError` to JSON‑RPC errors with appropriate error codes:
      - `invalid_argument`, `permission_denied`, `failed_precondition`, `resource_exhausted`, `unavailable`, `internal`, etc.
- TDD and CI:
  - Before any change to device or power behavior:
    - Update or add unit and integration tests based on this design and document 11.
  - Use CI coverage thresholds and security-focused tests to ensure:
    - The implementation stays aligned with this design.
    - Safety and behavior constraints remain intact over time.


---

<!-- Merged from 08-addendum-device-control-extensions.md -->

---

## 1. PWM Frequency Limits by Device Model

### 1.1 Hardware PWM Capabilities

**Raspberry Pi PWM Hardware Channels**:
- Pi 3/3+/4/5: 2 hardware PWM channels
  - Channel 0: GPIO 12, 18 (ALT0), GPIO 32 (ALT5), GPIO 52 (ALT1)
  - Channel 1: GPIO 13, 19 (ALT0), GPIO 33 (ALT5), GPIO 53 (ALT1)
- Zero/Zero W/Zero 2W: Same as above (2 channels)

**Hardware PWM Frequency Ranges**:
| Model | Min Frequency | Max Frequency | Recommended Range |
|-------|---------------|---------------|-------------------|
| **Pi 5** | 1 Hz | 125 MHz / divider | 100 Hz - 50 kHz |
| **Pi 4** | 1 Hz | 54 MHz / divider | 100 Hz - 50 kHz |
| **Pi 3/3+** | 1 Hz | 19.2 MHz / divider | 100 Hz - 50 kHz |
| **Pi Zero 2W** | 1 Hz | 1000 MHz / divider | 100 Hz - 50 kHz |
| **Software PWM** | 1 Hz | ~1 kHz | 50 Hz - 500 Hz |

### 1.2 PWM Configuration Schema (Enhanced)

**Phase 1: Basic PWM (Fixed Frequency)**:
```json
{
  "method": "gpio.set_pwm",
  "params": {
    "pin": 18,
    "duty_cycle_percent": 50.0,
    "frequency_hz": 1000
  }
}
```

Phase 1 constraints:
- Fixed frequency set at PWM start
- Frequency range: 100 Hz - 10 kHz (safe range)
- Validates pin is in allowed_pins
- Validates pin supports PWM

**Phase 2+: Advanced PWM**:
```json
{
  "method": "gpio.set_pwm_advanced",
  "params": {
    "pin": 18,
    "duty_cycle_percent": 50.0,
    "frequency_hz": 25000,
    "mode": "hardware",  // or "software"
    "allow_frequency_change": true
  }
}
```

### 1.3 PWM Validation Rules

**Implementation**:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class PwmLimits:
    min_freq_hz: int
    max_freq_hz: int
    recommended_min_hz: int
    recommended_max_hz: int
    hardware_channels: list[int]

PWM_LIMITS_BY_MODEL = {
    "pi5": PwmLimits(
        min_freq_hz=1,
        max_freq_hz=50000,
        recommended_min_hz=100,
        recommended_max_hz=10000,
        hardware_channels=[12, 13, 18, 19]
    ),
    "pi4": PwmLimits(
        min_freq_hz=1,
        max_freq_hz=50000,
        recommended_min_hz=100,
        recommended_max_hz=10000,
        hardware_channels=[12, 13, 18, 19]
    ),
    "pi3": PwmLimits(
        min_freq_hz=1,
        max_freq_hz=50000,
        recommended_min_hz=100,
        recommended_max_hz=10000,
        hardware_channels=[12, 13, 18, 19]
    ),
    "zero2w": PwmLimits(
        min_freq_hz=1,
        max_freq_hz=50000,
        recommended_min_hz=100,
        recommended_max_hz=10000,
        hardware_channels=[12, 13, 18, 19]
    ),
    "software": PwmLimits(
        min_freq_hz=1,
        max_freq_hz=1000,
        recommended_min_hz=50,
        recommended_max_hz=500,
        hardware_channels=[]
    )
}

def validate_pwm_frequency(
    pin: int,
    frequency_hz: int,
    model: str
) -> tuple[bool, Optional[str]]:
    """
    Validate PWM frequency for given pin and model.
    Returns (is_valid, error_message).
    """
    # Determine if hardware or software PWM
    limits = PWM_LIMITS_BY_MODEL.get(model, PWM_LIMITS_BY_MODEL["software"])
    is_hardware_pin = pin in limits.hardware_channels

    if not is_hardware_pin:
        limits = PWM_LIMITS_BY_MODEL["software"]

    if frequency_hz < limits.min_freq_hz:
        return False, f"Frequency {frequency_hz} Hz below minimum {limits.min_freq_hz} Hz"

    if frequency_hz > limits.max_freq_hz:
        return False, f"Frequency {frequency_hz} Hz above maximum {limits.max_freq_hz} Hz"

    # Warn if outside recommended range
    if frequency_hz < limits.recommended_min_hz or frequency_hz > limits.recommended_max_hz:
        warning = f"Frequency {frequency_hz} Hz outside recommended range {limits.recommended_min_hz}-{limits.recommended_max_hz} Hz"
        # Log warning but allow
        return True, warning

    return True, None
```

### 1.4 PWM Use Cases & Frequency Guidance

| Use Case | Typical Frequency | Notes |
|----------|-------------------|-------|
| **LED dimming** | 100-1000 Hz | Avoid visible flicker |
| **Servo control** | 50 Hz | Standard servo PWM |
| **DC motor speed** | 1000-5000 Hz | Higher = smoother |
| **Fan control** | 25 Hz (4-wire PWM) | PWM fans |
| **Buzzer/tone** | 100-10000 Hz | Frequency = pitch |
| **Analog simulation** | 1000-10000 Hz | With RC filter |

---

## 2. SPI Support (Phase 2+)

### 2.1 SPI Overview

**SPI Buses on Raspberry Pi**:
- **SPI0**: Main SPI bus (pins 19, 21, 23, 24, 26)
  - MOSI (GPIO 10), MISO (GPIO 9), SCLK (GPIO 11)
  - CE0 (GPIO 8), CE1 (GPIO 7)
- **SPI1**: Auxiliary SPI (GPIO 16-21)
  - MOSI (GPIO 20), MISO (GPIO 19), SCLK (GPIO 21)
  - CE0 (GPIO 18), CE1 (GPIO 17), CE2 (GPIO 16)

**Performance**:
- Max speed: 125 MHz (Pi 4/5), lower on older models
- Typical usage: 1-10 MHz for most devices
- Full duplex, synchronous communication

### 2.2 SPI Tool Interface

**`spi.list_buses`**:
```json
{
  "method": "spi.list_buses",
  "params": {}
}
```

Response:
```json
{
  "result": {
    "buses": [
      {
        "bus": 0,
        "device_paths": ["/dev/spidev0.0", "/dev/spidev0.1"],
        "max_speed_hz": 125000000,
        "mode": "full"  // or "read_only" or "disabled"
      }
    ]
  }
}
```

**`spi.transfer`**:
```json
{
  "method": "spi.transfer",
  "params": {
    "bus": 0,
    "chip_select": 0,
    "data": [0x01, 0x02, 0x03],
    "speed_hz": 1000000,
    "bits_per_word": 8,
    "mode": 0
  }
}
```

Response:
```json
{
  "result": {
    "rx_data": [0x00, 0x5A, 0xFF],
    "bytes_transferred": 3
  }
}
```

### 2.3 SPI Configuration

**In `AppConfig`**:
```yaml
spi:
  buses:
    - bus: 0
      mode: "full"  # full, read_only, disabled
      allow_chip_selects: [0, 1]  # Which CS pins to allow
      max_speed_hz: 10000000  # 10 MHz max
      devices:
        - name: "adc_chip"
          chip_select: 0
          description: "MCP3008 ADC"
```

### 2.4 SPI Safety Considerations

**Whitelisting**:
- Bus number whitelist (default: SPI0 only)
- Chip select whitelist per bus
- Speed limits (prevent hardware damage)

**Read-only mode**:
- Allow only read operations (MISO)
- Block MOSI writes for sensitive devices

**Validation**:
- Check device file exists (`/dev/spidev{bus}.{cs}`)
- Validate speed doesn't exceed max for bus
- Validate mode (0-3) is valid

---

## 3. UART/Serial Support (Phase 2+)

### 3.1 UART Overview

**UART Ports on Raspberry Pi**:
- **Primary UART (UART0/PL011)**: GPIO 14 (TX), GPIO 15 (RX)
  - High quality, hardware flow control
  - Can be used for Bluetooth (Pi 3+) or GPIO console
- **Mini UART (UART1)**: Secondary, lower quality
  - Used when primary assigned to Bluetooth

**Common Uses**:
- GPS modules
- Serial sensors (LoRa, ZigBee, etc.)
- Arduino/microcontroller communication
- Serial console (debugging)

### 3.2 UART Tool Interface

**`uart.list_ports`**:
```json
{
  "method": "uart.list_ports",
  "params": {}
}
```

Response:
```json
{
  "result": {
    "ports": [
      {
        "device": "/dev/ttyAMA0",
        "description": "PL011 UART",
        "type": "hardware",
        "available": true
      },
      {
        "device": "/dev/ttyS0",
        "description": "Mini UART",
        "type": "hardware",
        "available": true
      },
      {
        "device": "/dev/ttyUSB0",
        "description": "USB Serial Adapter",
        "type": "usb",
        "available": true
      }
    ]
  }
}
```

**`uart.open`**:
```json
{
  "method": "uart.open",
  "params": {
    "port": "/dev/ttyAMA0",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "none",  // none, even, odd
    "stopbits": 1,
    "timeout_ms": 1000
  }
}
```

Response:
```json
{
  "result": {
    "handle": "uart_handle_123",
    "port": "/dev/ttyAMA0"
  }
}
```

**`uart.read`**:
```json
{
  "method": "uart.read",
  "params": {
    "handle": "uart_handle_123",
    "max_bytes": 256,
    "timeout_ms": 1000
  }
}
```

Response:
```json
{
  "result": {
    "data": [0x24, 0x47, 0x50, 0x47, 0x47, 0x41],  // $GPGGA
    "bytes_read": 6
  }
}
```

**`uart.write`**:
```json
{
  "method": "uart.write",
  "params": {
    "handle": "uart_handle_123",
    "data": [0x41, 0x54, 0x0D, 0x0A]  // AT\r\n
  }
}
```

**`uart.close`**:
```json
{
  "method": "uart.close",
  "params": {
    "handle": "uart_handle_123"
  }
}
```

### 3.3 UART Configuration

**In `AppConfig`**:
```yaml
uart:
  allowed_ports:
    - "/dev/ttyAMA0"
    - "/dev/ttyS0"
    - "/dev/ttyUSB*"  # Wildcard for USB serial adapters
  max_open_ports: 4
  allowed_baudrates: [9600, 19200, 38400, 57600, 115200]
  read_only_ports: []  # Ports that can only read, not write
```

### 3.4 UART Safety Considerations

**Whitelisting**:
- Port path whitelist (prevent access to sensitive devices)
- Baudrate whitelist (prevent misconfiguration)
- Limit concurrent open ports

**Read-only mode**:
- Some ports may be read-only (monitoring only)

**Handle management**:
- Handles expire after inactivity
- Limit handles per client/role
- Auto-close on session end

---

## 4. Camera Video Recording (Phase 2+)

### 4.1 Video Recording Interface

**`camera.start_recording`**:
```json
{
  "method": "camera.start_recording",
  "params": {
    "duration_seconds": 30,
    "resolution": "1080p",  // 1080p, 720p, 480p
    "framerate": 30,
    "format": "h264",  // h264, mjpeg
    "output_path": "/var/lib/mcp-raspi/media/video_{timestamp}.h264",
    "quality": "high"  // low, medium, high
  }
}
```

Response:
```json
{
  "result": {
    "recording_id": "rec_abc123",
    "output_path": "/var/lib/mcp-raspi/media/video_20250103_120000.h264",
    "estimated_size_mb": 45,
    "status": "recording"
  }
}
```

**`camera.stop_recording`**:
```json
{
  "method": "camera.stop_recording",
  "params": {
    "recording_id": "rec_abc123"
  }
}
```

Response:
```json
{
  "result": {
    "recording_id": "rec_abc123",
    "output_path": "/var/lib/mcp-raspi/media/video_20250103_120000.h264",
    "duration_seconds": 25.3,
    "file_size_mb": 38.5,
    "status": "completed"
  }
}
```

**`camera.get_recording_status`**:
```json
{
  "method": "camera.get_recording_status",
  "params": {
    "recording_id": "rec_abc123"
  }
}
```

Response:
```json
{
  "result": {
    "recording_id": "rec_abc123",
    "status": "recording",  // recording, stopped, completed, failed
    "elapsed_seconds": 15.2,
    "duration_limit_seconds": 30,
    "output_path": "/var/lib/mcp-raspi/media/video_20250103_120000.h264",
    "current_size_mb": 22.8
  }
}
```

### 4.2 Video Recording Configuration

**In `AppConfig`**:
```yaml
camera:
  media_root: "/var/lib/mcp-raspi/media"
  max_photos_per_minute: 30
  video:
    enable_recording: false  # Phase 2+
    max_duration_seconds: 300  # 5 minutes max
    max_concurrent_recordings: 1
    max_file_size_mb: 500
    allowed_formats: ["h264", "mjpeg"]
    allowed_resolutions: ["1080p", "720p", "480p"]
    default_framerate: 30
```

### 4.3 Video Recording Safeguards

**Rate Limiting**:
- Max recordings per hour
- Max concurrent recordings
- Max total storage usage

**Resource Protection**:
- Monitor available disk space before starting
- Stop recording if disk space drops below threshold
- CPU/temperature monitoring (stop if overheating)

**Auto-cleanup**:
- Delete recordings older than N days
- Keep only last N recordings
- Configurable retention policy

### 4.4 Video Encoding Parameters

| Resolution | Bitrate (high) | Bitrate (medium) | Bitrate (low) | Use Case |
|------------|----------------|------------------|---------------|----------|
| **1080p** | 8 Mbps | 5 Mbps | 3 Mbps | High quality |
| **720p** | 5 Mbps | 3 Mbps | 2 Mbps | Good quality, less storage |
| **480p** | 3 Mbps | 2 Mbps | 1 Mbps | Space-saving |

**Framerate guidance**:
- 30 fps: Standard, smooth motion
- 24 fps: Cinematic, saves storage
- 15 fps: Time-lapse style, minimal storage

---

## 5. Device Control State Persistence (Phase 2+)

### 5.1 GPIO State Persistence

**Save current GPIO state**:
```json
{
  "method": "gpio.save_state",
  "params": {
    "name": "default_gpio_state",
    "include_pins": [17, 18, 27]
  }
}
```

Response:
```json
{
  "result": {
    "state_id": "gpio_state_123",
    "saved_at": "2025-01-03T12:00:00Z",
    "pins": {
      "17": {"mode": "output", "value": 1},
      "18": {"mode": "output", "value": 0, "pwm": {"enabled": false}},
      "27": {"mode": "input", "pull": "up"}
    }
  }
}
```

**Restore GPIO state**:
```json
{
  "method": "gpio.restore_state",
  "params": {
    "state_id": "gpio_state_123"
  }
}
```

**Auto-restore on boot**:
- Configure in `gpio.restore_on_boot: true`
- Systemd unit runs before mcp-raspi-server
- Applies last saved state or configured default

### 5.2 State Storage

**Location**: `/var/lib/mcp-raspi/device_states/gpio_state.json`

**Format**:
```json
{
  "version": 1,
  "saved_at": "2025-01-03T12:00:00Z",
  "states": {
    "default": {
      "pins": {
        "17": {"mode": "output", "value": 1},
        "18": {"mode": "output", "value": 0}
      }
    }
  }
}
```

---

## 6. Implementation Checklist

**Phase 1 (Current)**:
- [x] Basic PWM with fixed frequency (100 Hz - 10 kHz)
- [x] PWM duty cycle validation
- [x] Pin whitelist validation

**Phase 2A (SPI/UART)**:
- [ ] SPI bus enumeration and transfer
- [ ] SPI whitelist and speed limits
- [ ] UART port management
- [ ] UART read/write with handles
- [ ] UART safety constraints

**Phase 2B (Advanced PWM)**:
- [ ] PWM frequency validation by model
- [ ] Hardware vs software PWM detection
- [ ] Dynamic frequency changes
- [ ] PWM use case presets

**Phase 2C (Video Recording)**:
- [ ] Video recording start/stop/status
- [ ] H.264 encoding integration
- [ ] Storage and resource monitoring
- [ ] Recording retention policies

**Phase 3 (State Persistence)**:
- [ ] GPIO state save/restore
- [ ] Auto-restore on boot
- [ ] State versioning and migration

---

**Document Version**: 1.0
**Last Updated**: 2025-12-03
**Status**: Addendum to Doc 08
**Phase Coverage**: Phase 1 (PWM specs) + Phase 2+ (SPI/UART/Video)
