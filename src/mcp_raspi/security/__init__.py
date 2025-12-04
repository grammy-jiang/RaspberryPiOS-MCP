"""
Security module for the Raspberry Pi MCP Server.

This module implements authentication, authorization, and audit logging
following the design specifications in doc 04 (Security, OAuth Integration
& Access Control Design).

Components:
- JWKSFetcher: Fetches and caches Cloudflare Access JWKS public keys
- JWTValidator: Validates JWT tokens from Cloudflare Access
- RBAC: Role-based access control with @require_role decorator
- AuditLogger: Structured audit logging for privileged operations
"""

from mcp_raspi.security.audit_logger import AuditLogger
from mcp_raspi.security.jwks_fetcher import JWKSFetcher
from mcp_raspi.security.jwt_validator import AuthContext, JWTValidator
from mcp_raspi.security.rbac import (
    RBACEnforcer,
    require_role,
)

__all__ = [
    "JWKSFetcher",
    "JWTValidator",
    "AuthContext",
    "RBACEnforcer",
    "require_role",
    "AuditLogger",
]
