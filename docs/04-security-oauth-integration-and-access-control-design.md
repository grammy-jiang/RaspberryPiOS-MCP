# 04. Security, OAuth Integration & Access Control Design

## 1. Document Purpose

- Describe the security architecture, threat model, and trust boundaries of the Raspberry Pi MCP Server.  
- Define the overall approach to authentication (AuthN), authorization (AuthZ), and auditing (Audit).  
- Explain how to integrate with Cloudflare Tunnel / Access and OAuth/OIDC.

## 2. Threat Model & Trust Boundaries

### 2.1 Assets

- The managed Raspberry Pi device and the applications/data running on it.  
- The MCP server control plane (ability to reboot, shut down, self‑update, manage services, etc.).  
- Audit logs, system logs, and configuration files.  
- Sensitive credentials such as OAuth secrets, access tokens, Cloudflare Access JWTs.

### 2.2 Threats

- Unauthorized access to MCP tools to perform dangerous operations (reboot, shutdown, file deletion, etc.).  
- Attackers exploiting vulnerabilities in MCP Server or the privileged agent to escalate privileges or escape to root.  
- Misconfigured OAuth/Cloudflare leading to unauthenticated internet‑wide access.  
- Leaking secrets (tokens, passwords, private keys) in logs.  
- Abusing the self‑update mechanism as an injection channel for malicious code.

### 2.3 Trust Boundaries

- **External client ↔ Cloudflare Tunnel/Access** – public internet to Cloudflare edge.  
- **Cloudflare ↔ MCP Server** – Cloudflare to local `mcp-raspi-server` (typically mTLS or loopback).  
- **MCP Server ↔ Privileged Agent** – non‑privileged to privileged process IPC channel.  
- **MCP Server ↔ Local system resources** – filesystem, logs, metrics, etc.

## 3. Authentication

### 3.1 Cloudflare Tunnel & Access

- MCP Server listens only on localhost or LAN addresses by default (e.g., `127.0.0.1:8000`).  
- All public internet access goes through Cloudflare Tunnel with Cloudflare Access as the gateway:  
  - Cloudflare integrates with OAuth/OIDC identity providers (Google, GitHub, enterprise IdP, etc.).  
  - Users authenticate with Cloudflare/OAuth before reaching MCP Server.  
  - Cloudflare Access policies define which identities can access MCP Server.  
- Cloudflare forwards identity assertions to MCP Server, typically via `Cf-Access-Jwt-Assertion` headers.

### 3.2 Backend Validation

- MCP Server validates incoming requests from Cloudflare:  
  - Optionally check source IP (e.g., restrict to Cloudflare ranges or local loopback).  
  - Validate the JWT from `Cf-Access-Jwt-Assertion` (or equivalent header):  
    - Use Cloudflare public keys or JWKS.  
    - Verify signature, expiration (`exp`), audience (`aud`), and issuer (`iss`).  
- Map identity information in the JWT (email, groups, etc.) to internal roles.

### 3.3 Local‑Only Mode

- For pure LAN or lab environments, a “local mode” can be enabled:  
  - MCP Server accepts only connections from `127.0.0.1` or configured LAN ranges.  
  - Authentication can use static API tokens or mTLS instead of Cloudflare Access.  
- The design and docs MUST clearly distinguish production internet‑exposed deployments from local/dev deployments.

### 3.4 Example Header Handling Flow

In a typical production environment:

1. Receive HTTPS reverse proxy request from Cloudflare.  
2. Extract JWT from `Cf-Access-Jwt-Assertion` header.  
3. Fetch or cache public keys from Cloudflare’s JWKS URL.  
4. Validate signature, `exp`, `aud`, and `iss`.  
5. Extract identity attributes (`email`, `groups`, etc.) and map to internal role.  
6. Attach the resulting `AuthContext` to internal `ToolContext` for subsequent authorization and auditing.

## 4. Authorization

### 4.1 Role & Level Model

Define tool‑level safety levels (consistent with config):

- `read_only` – read‑only queries (system info, metrics, a subset of log viewing).  
- `safe_control` – limited impact on system state (GPIO output, safe service restarts, etc.).  
- `admin` – high‑risk operations (reboot, shutdown, self‑update, OS update, etc.).

Map external identities to internal roles, for example:

- `viewer` – allowed `read_only` tools only.  
- `operator` – allowed `read_only` + `safe_control`.  
- `admin` – allowed all tools (subject to extra safeguards).

### 4.2 Tool‑Level Policy

Each MCP tool has a policy entry in config:

- `enabled` – whether the tool is enabled.  
- `required_role` – the minimum internal role required to use this tool.  
- `safety_level` – one of `read_only`, `safe_control`, `admin`.  
- Optional `rate_limit` – request frequency limits.

The MCP Server MUST verify the caller’s role and tool policy before executing any tool.

Example YAML snippet:

```yaml
tools:
  system.get_basic_info:
    enabled: true
    required_role: "viewer"
    safety_level: "read_only"
  system.reboot:
    enabled: true
    required_role: "admin"
    safety_level: "admin"
    rate_limit:
      max_calls: 1
      per_seconds: 3600
  gpio.write_pin:
    enabled: true
    required_role: "operator"
    safety_level: "safe_control"
```

### 4.3 Rate Limiting & Safeguards

- Recommend or require rate limits for:  
  - `system.reboot` / `system.shutdown`.  
  - `manage.update_server` / `manage.update_os` (or `manage.preview_os_updates` / `manage.apply_os_updates`).  
  - Potentially dangerous high‑frequency hardware operations (e.g., rapid PWM adjustment tools).  
- Limits MAY be defined globally and per‑tool.  
- When rate limits are exceeded, the server SHOULD return a clear error (e.g., `error_code="resource_exhausted"`) and record a log entry.

### 4.4 Example Role Mapping

Assume the JWT contains:

- `email`: `alice@example.com`  
- `groups`: `["mcp-admins", "iot-ops"]`

Local configuration:

- `"mcp-admins"` → `admin`.  
- `"iot-ops"` → `operator`.  
- Default (no match) → `viewer`.

If a user belongs to multiple groups, use the highest privilege role. If no mapping applies, deny all tools.

## 5. Audit Logging

### 5.1 Audit Content

Every MCP tool call MUST be recorded in the audit log (without leaking secrets), including:

- Timestamp (UTC).  
- Tool name (e.g., `gpio.write_pin`).  
- Caller identity (user/client id derived from JWT or API token).  
- Key parameter summary (avoid secrets).  
- Call result (success/failure).  
- Error code and brief message (on failure).  
- Source IP (if available).

Example audit log entry (JSON):

```json
{
  "timestamp": "2025-01-01T12:34:56Z",
  "tool": "system.reboot",
  "caller": {
    "user": "alice@example.com",
    "role": "admin"
  },
  "status": "error",
  "error_code": "rate_limited",
  "source_ip": "198.51.100.23"
}
```

### 5.2 Storage & Retention

- Use structured formats (e.g., JSON lines) for audit logs.  
  - Default path: `/var/log/mcp-raspi/audit.log`.  
- Provide configuration for:  
  - Maximum file size and rotation strategy.  
  - Retention time (e.g., 30/90 days).  
  - Optional sync to a remote log system (Phase 2).

## 6. Secrets Management

### 6.1 Secret Storage

- NEVER hard‑code secrets in source code.  
- Store Cloudflare Access credentials, OAuth client secrets, API tokens, etc. in:  
  - System‑level secret files (e.g., `/etc/mcp-raspi/secrets.env` with restricted permissions).  
  - Or OS‑provided secret storage (keyring, key management service, etc.).  
- MCP Server reads secrets from environment variables or restricted config files.

### 6.2 In‑Memory Handling

- Avoid printing or logging secrets.  
- Do not echo tokens in error messages.  
- Minimize the time secrets are retained in memory; clear or allow GC as soon as possible.

## 7. Hardening & Least Privilege

### 7.1 MCP Server Process

- Run as a non‑root user (e.g., `mcp`).  
- File system permissions:  
  - Only grant read/write access where necessary (config, log directories).  
  - No direct write access to critical system directories (`/etc`, `/usr`, `/boot`, etc.).  
- Use `systemd` hardening options where supported:  
  - `PrivateTmp=yes`  
  - `ProtectSystem=strict`  
  - `ProtectHome=yes`  
  - `NoNewPrivileges=yes`  
  - Capability restrictions via `CapabilityBoundingSet`.  

### 7.2 Python Security Components

Recommended in `mcp_raspi.security`:

```python
from typing import Optional
from mcp_raspi.server.context import ToolContext


class AuthContext:
    user_email: str
    groups: list[str]
    role: str


class AuthProvider:
    async def authenticate(self, request) -> Optional[AuthContext]: ...


class ToolPolicyEnforcer:
    def is_allowed(self, ctx: ToolContext, tool_name: str) -> bool: ...
```

Implementation notes:

- `AuthProvider` SHOULD use `pyjwt` (or equivalent) to validate Cloudflare Access JWTs.  
- `ToolPolicyEnforcer` MUST apply config‑driven role mappings and tool policies (`tools.*`, `security.roles`), as described in docs 04 and 14.

### 7.3 Privileged Agent Process

- Responsible only for privileged operations; keep its code as small and simple as possible.  
- Listen only on a local Unix domain socket; MUST NOT expose a TCP port.  
- Validate all incoming requests:  
  - Operation type is whitelisted.  
  - Parameters are within expected bounds (e.g., GPIO pin numbers, I2C addresses).  
- Optionally use `seccomp` or similar mechanisms to restrict allowed syscalls where feasible.

## 8. Self‑Update Security

- Update sources MUST be trusted:  
  - Use HTTPS with certificate validation to fetch releases.  
  - Or use APT to install from trusted repositories.  
- Recommended to verify integrity of downloaded artifacts (e.g., signature checks).  
- Updates MUST follow an “all‑or‑nothing” principle to avoid half‑applied updates.  
- Rollback strategy MUST:  
  - Keep the last known‑good version (code/package).  
  - Automatically restore to the previous version on update failure, and log details.

Configuration snippet (aligned with docs 10 and 14 `updates.*` fields):

```yaml
updates:
  enable_remote_server_update: true
  enable_os_update: false
  trusted_origins:
    - "https://example.com/releases/"
  require_signature: true
```

## 9. Development & Testing (Security‑Focused)

- Perform static analysis and dependency vulnerability scanning on critical modules.  
- In test environments, simulate attack scenarios:  
  - Unauthenticated access attempts.  
  - Privilege escalation attempts (calling admin tools from non‑admin role).  
  - Abuse of dangerous tools at high frequency.  
  - Malicious input injection (overlong strings, boundary values, malformed JSON, etc.).  
- Fuzz the privileged agent IPC interface to uncover validation and error‑handling gaps.  
- Ensure security‑relevant configuration (role mappings, tool policies, rate limits) has adequate unit and integration test coverage (see docs 11 and 13).

---

<!-- Merged from 04-addendum-security-advanced-topics.md -->

## 10. Certificate & Key Rotation

### 10.1 Overview

Regular rotation of cryptographic keys and certificates reduces the impact of key compromise and meets compliance requirements.

**Rotation Targets**:
- Update signing keys (Ed25519 for package signatures)
- OAuth/JWT validation keys (Cloudflare Access)
- TLS certificates (if applicable)
- IPC authentication tokens (Phase 2+)

### 10.2 Update Signing Key Rotation

#### Rotation Strategy

**Key Lifecycle**:
- **Primary key**: Active signing key (valid 12 months)
- **Backup key**: Secondary signing key (overlapping validity)
- **Retired keys**: Kept for signature verification of old releases

**Rotation Schedule**: Every 12 months, or immediately on compromise

(See full implementation in addendum file for detailed Python code and automation)

### 10.3 OAuth/JWT Key Rotation

For Cloudflare Access integration, JWT validation keys are managed by Cloudflare. Devices must fetch JWKS (JSON Web Key Set) periodically with proper caching and retry logic.

## 11. Security Update Policy for Dependencies

### 11.1 Python Dependency Security

Regular vulnerability scanning with tools like `safety` and automated CI/CD security checks are essential. Update tiers prioritize critical security updates for immediate application.

### 11.2 System Package Security Updates

Automated security updates via `unattended-upgrades` on Raspberry Pi OS with appropriate configuration for security-only updates and automatic reboots during maintenance windows.

## 12. Penetration Testing

### 12.1 Testing Scope

Regular penetration testing covering:
- Authentication & Authorization bypass attempts
- Input validation (SQL injection, command injection, path traversal)
- API security (rate limits, parameter tampering)
- Network security (TLS, IPC eavesdropping)
- Hardware security (GPIO/I2C abuse)
- Data security (log injection, sensitive data exposure)

### 12.2 Automated Security Testing

Comprehensive test suites for authentication, input validation, and rate limiting scenarios integrated into CI/CD pipeline.

## 13. GDPR & Privacy Considerations

### 13.1 Personal Data Handling

Careful treatment of personal data in logs and metrics with data minimization principles:
- Pseudonymization of email addresses
- Optional IP address hashing or removal
- Never log JWT tokens or passwords
- Configurable data retention periods

### 13.2 Data Subject Rights

Implementation of GDPR-required functionality:
- **Right to Access**: Tools to export all user data
- **Right to Erasure**: Secure deletion of user data with admin confirmation
- Privacy-by-design principles throughout the architecture
