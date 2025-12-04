"""
JWT validation for Cloudflare Access authentication.

This module validates JWTs from Cloudflare Access, extracting user identity
and mapping JWT claims to internal roles.

Design follows Doc 04 §3 (Authentication) and §4 (Authorization).
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
)

from mcp_raspi.errors import ToolError
from mcp_raspi.security.jwks_fetcher import JWKSFetcher

if TYPE_CHECKING:
    from mcp_raspi.config import SecurityConfig

logger = logging.getLogger("mcp_raspi.security.jwt_validator")


class AuthenticationError(ToolError):
    """Error raised when authentication fails."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize an AuthenticationError."""
        super().__init__(
            error_code="unauthenticated",
            message=message,
            details=details,
        )


@dataclass
class AuthContext:
    """
    Authentication context extracted from a validated JWT or local auth.

    Attributes:
        user_id: User identifier (from 'sub' claim or email).
        email: User email address (from 'email' claim).
        groups: External groups from JWT claims.
        role: Resolved internal role (viewer, operator, admin).
        authenticated: Whether the user is authenticated.
        auth_method: Authentication method used ('jwt', 'local_token', 'permissive').
        token_exp: Token expiration time (if applicable).
    """

    user_id: str
    email: str | None = None
    groups: list[str] = field(default_factory=list)
    role: str = "viewer"
    authenticated: bool = True
    auth_method: str = "jwt"
    token_exp: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "groups": self.groups,
            "role": self.role,
            "authenticated": self.authenticated,
            "auth_method": self.auth_method,
            "token_exp": self.token_exp.isoformat() if self.token_exp else None,
        }


class JWTValidator:
    """
    Validates JWTs from Cloudflare Access.

    This class handles:
    - JWT signature verification using JWKS
    - Token expiration validation
    - Audience and issuer validation
    - Claim extraction and role mapping

    Example:
        >>> validator = JWTValidator.from_config(config)
        >>> auth_ctx = await validator.validate_token(token)
        >>> print(auth_ctx.user_id, auth_ctx.role)
    """

    def __init__(
        self,
        jwks_fetcher: JWKSFetcher,
        audience: str,
        issuer: str,
        role_mappings: dict[str, str],
        default_role: str = "viewer",
    ) -> None:
        """
        Initialize the JWT validator.

        Args:
            jwks_fetcher: JWKSFetcher for fetching public keys.
            audience: Expected audience claim.
            issuer: Expected issuer claim.
            role_mappings: Mapping from JWT groups to internal roles.
            default_role: Default role if no mapping matches.
        """
        self._jwks_fetcher = jwks_fetcher
        self._audience = audience
        self._issuer = issuer
        self._role_mappings = role_mappings
        self._default_role = default_role

    @classmethod
    def from_config(
        cls,
        config: SecurityConfig,
        jwks_fetcher: JWKSFetcher | None = None,
    ) -> JWTValidator:
        """
        Create a JWTValidator from configuration.

        Args:
            config: SecurityConfig with authentication settings.
            jwks_fetcher: Optional pre-configured JWKSFetcher.

        Returns:
            Configured JWTValidator instance.
        """
        if jwks_fetcher is None:
            jwks_fetcher = JWKSFetcher.from_config(config.cloudflare_auth)

        return cls(
            jwks_fetcher=jwks_fetcher,
            audience=config.cloudflare_auth.audience,
            issuer=config.cloudflare_auth.issuer,
            role_mappings=config.role_mappings.groups_to_roles,
            default_role="viewer",
        )

    async def validate_token(self, token: str) -> AuthContext:
        """
        Validate a JWT and extract authentication context.

        Args:
            token: The JWT string to validate.

        Returns:
            AuthContext with extracted user information.

        Raises:
            AuthenticationError: If token validation fails.
        """
        if not token:
            raise AuthenticationError(
                message="No authentication token provided",
                details={"reason": "missing_token"},
            )

        # Get the key ID from token header
        try:
            unverified_header = jwt.get_unverified_header(token)
        except DecodeError as e:
            raise AuthenticationError(
                message="Invalid token format",
                details={"reason": "decode_error", "error": str(e)},
            ) from e

        kid = unverified_header.get("kid")
        if not kid:
            raise AuthenticationError(
                message="Token missing key ID (kid)",
                details={"reason": "missing_kid"},
            )

        # Fetch JWKS and get the key
        try:
            await self._jwks_fetcher.get_keys()
        except Exception as e:
            logger.error("Failed to fetch JWKS: %s", str(e))
            raise AuthenticationError(
                message="Failed to fetch authentication keys",
                details={"reason": "jwks_fetch_failed", "error": str(e)},
            ) from e

        key_data = self._jwks_fetcher.get_key_by_kid(kid)
        if key_data is None:
            # Try refreshing in case the key was rotated
            try:
                await self._jwks_fetcher.force_refresh()
                key_data = self._jwks_fetcher.get_key_by_kid(kid)
            except Exception as e:
                # Log the exception during JWKS refresh; will raise AuthenticationError below if key still not found.
                logger.error("Exception during JWKS force_refresh: %s", str(e))

            if key_data is None:
                raise AuthenticationError(
                    message="Unknown signing key",
                    details={"reason": "unknown_kid", "kid": kid},
                )

        # Validate the token
        try:
            payload = jwt.decode(
                token,
                key_data["key"],
                algorithms=[key_data["alg"]],
                audience=self._audience,
                issuer=self._issuer,
            )
        except ExpiredSignatureError as e:
            raise AuthenticationError(
                message="Token has expired",
                details={"reason": "token_expired"},
            ) from e
        except InvalidSignatureError as e:
            raise AuthenticationError(
                message="Invalid token signature",
                details={"reason": "invalid_signature"},
            ) from e
        except InvalidAudienceError as e:
            raise AuthenticationError(
                message="Invalid token audience",
                details={"reason": "invalid_audience", "expected": self._audience},
            ) from e
        except InvalidIssuerError as e:
            raise AuthenticationError(
                message="Invalid token issuer",
                details={"reason": "invalid_issuer", "expected": self._issuer},
            ) from e
        except InvalidTokenError as e:
            raise AuthenticationError(
                message="Invalid token",
                details={"reason": "invalid_token", "error": str(e)},
            ) from e

        # Extract claims and build AuthContext
        return self._extract_auth_context(payload)

    def _extract_auth_context(self, payload: dict[str, Any]) -> AuthContext:
        """
        Extract AuthContext from validated JWT payload.

        Args:
            payload: Decoded JWT payload.

        Returns:
            AuthContext with user information.
        """
        # Extract user identity
        user_id = payload.get("sub", "")
        email = payload.get("email")

        # Use email as user_id if sub is not meaningful
        if not user_id and email:
            user_id = email

        # Extract groups from various possible claim names
        groups: list[str] = []
        for claim_name in ["groups", "roles", "cf_groups", "custom:groups"]:
            claim_value = payload.get(claim_name)
            if isinstance(claim_value, list):
                groups.extend(claim_value)
            elif isinstance(claim_value, str):
                groups.append(claim_value)

        # Map groups to role
        role = self._map_groups_to_role(groups)

        # Extract expiration
        exp = payload.get("exp")
        token_exp = None
        if exp:
            with contextlib.suppress(TypeError, ValueError):
                token_exp = datetime.fromtimestamp(exp, tz=UTC)

        return AuthContext(
            user_id=user_id,
            email=email,
            groups=groups,
            role=role,
            authenticated=True,
            auth_method="jwt",
            token_exp=token_exp,
        )

    def _map_groups_to_role(self, groups: list[str]) -> str:
        """
        Map external groups to internal role.

        Uses the highest privilege role if multiple groups match.
        Role hierarchy: admin > operator > viewer

        Args:
            groups: List of external groups from JWT.

        Returns:
            Internal role name.
        """
        # Define role hierarchy (higher index = higher privilege)
        role_hierarchy = ["viewer", "operator", "admin"]
        highest_role = self._default_role

        for group in groups:
            mapped_role = self._role_mappings.get(group)
            if mapped_role:
                # Check if this role is higher in hierarchy
                try:
                    if role_hierarchy.index(mapped_role) > role_hierarchy.index(
                        highest_role
                    ):
                        highest_role = mapped_role
                except ValueError:
                    # Unknown role, use it if we have default
                    if highest_role == self._default_role:
                        highest_role = mapped_role

        return highest_role


class LocalAuthenticator:
    """
    Local authentication for development and testing.

    Supports:
    - Static token authentication
    - Permissive mode (no authentication required)

    WARNING: Only use in development/testing environments!
    """

    def __init__(
        self,
        static_token: str | None = None,
        permissive_mode: bool = False,
        default_role: str = "admin",
        default_user_id: str = "local-dev-user",
    ) -> None:
        """
        Initialize local authenticator.

        Args:
            static_token: Optional static token for authentication.
            permissive_mode: If True, allows all requests.
            default_role: Default role for authenticated users.
            default_user_id: Default user ID for local auth.
        """
        self._static_token = static_token
        self._permissive_mode = permissive_mode
        self._default_role = default_role
        self._default_user_id = default_user_id

    @classmethod
    def from_config(cls, config: SecurityConfig) -> LocalAuthenticator:
        """Create a LocalAuthenticator from configuration."""
        return cls(
            static_token=config.local_auth.static_token,
            permissive_mode=config.local_auth.permissive_mode,
            default_role=config.local_auth.default_role,
            default_user_id=config.local_auth.default_user_id,
        )

    def authenticate(self, token: str | None = None) -> AuthContext:
        """
        Authenticate using local auth mode.

        Args:
            token: Optional token to validate.

        Returns:
            AuthContext for the local user.

        Raises:
            AuthenticationError: If authentication fails.
        """
        if self._permissive_mode:
            logger.warning("Permissive mode enabled - all requests allowed")
            return AuthContext(
                user_id=self._default_user_id,
                email=None,
                groups=[],
                role=self._default_role,
                authenticated=True,
                auth_method="permissive",
            )

        if self._static_token and token:
            if token == self._static_token:
                return AuthContext(
                    user_id=self._default_user_id,
                    email=None,
                    groups=[],
                    role=self._default_role,
                    authenticated=True,
                    auth_method="local_token",
                )
            else:
                raise AuthenticationError(
                    message="Invalid local token",
                    details={"reason": "invalid_token"},
                )

        raise AuthenticationError(
            message="No authentication token provided",
            details={"reason": "missing_token"},
        )


class AuthProvider:
    """
    Unified authentication provider that supports both Cloudflare and local auth.

    This class selects the appropriate authentication method based on
    configuration and handles the authentication flow.
    """

    def __init__(
        self,
        mode: str,
        jwt_validator: JWTValidator | None = None,
        local_authenticator: LocalAuthenticator | None = None,
    ) -> None:
        """
        Initialize the auth provider.

        Args:
            mode: Authentication mode ('cloudflare' or 'local').
            jwt_validator: JWT validator for Cloudflare mode.
            local_authenticator: Local authenticator for local mode.
        """
        self._mode = mode
        self._jwt_validator = jwt_validator
        self._local_authenticator = local_authenticator

    @classmethod
    def from_config(cls, config: SecurityConfig) -> AuthProvider:
        """
        Create an AuthProvider from configuration.

        Args:
            config: SecurityConfig with authentication settings.

        Returns:
            Configured AuthProvider instance.
        """
        jwt_validator = None
        local_authenticator = None

        if config.mode == "cloudflare":
            jwt_validator = JWTValidator.from_config(config)
        else:
            local_authenticator = LocalAuthenticator.from_config(config)

        return cls(
            mode=config.mode,
            jwt_validator=jwt_validator,
            local_authenticator=local_authenticator,
        )

    async def authenticate(
        self,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> AuthContext:
        """
        Authenticate a request.

        Args:
            token: Direct token (if available).
            headers: Request headers (to extract token from).

        Returns:
            AuthContext with user information.

        Raises:
            AuthenticationError: If authentication fails.
        """
        # Extract token from headers if not provided directly
        if token is None and headers:
            token = self._extract_token_from_headers(headers)

        if self._mode == "cloudflare":
            if self._jwt_validator is None:
                raise AuthenticationError(
                    message="JWT validator not configured",
                    details={"reason": "configuration_error"},
                )
            return await self._jwt_validator.validate_token(token or "")
        else:
            if self._local_authenticator is None:
                raise AuthenticationError(
                    message="Local authenticator not configured",
                    details={"reason": "configuration_error"},
                )
            return self._local_authenticator.authenticate(token)

    def _extract_token_from_headers(self, headers: dict[str, str]) -> str | None:
        """
        Extract JWT token from request headers.

        Checks common header names:
        - Cf-Access-Jwt-Assertion (Cloudflare Access)
        - Authorization (Bearer token)

        Args:
            headers: Request headers.

        Returns:
            Token string or None if not found.
        """
        # Cloudflare Access header
        token = headers.get("Cf-Access-Jwt-Assertion") or headers.get(
            "cf-access-jwt-assertion"
        )
        if token:
            return token

        # Standard Authorization header
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        return None
