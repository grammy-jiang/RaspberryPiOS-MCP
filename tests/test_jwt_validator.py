"""
Tests for the JWT validator module.

Tests cover:
- JWT validation with mocked JWKS
- Token expiration handling
- Audience and issuer validation
- Claim extraction and role mapping
- Local authentication mode
- Auth provider flow
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_raspi.config import (
    CloudflareAuthConfig,
    LocalAuthConfig,
    RoleMappingsConfig,
    SecurityConfig,
)
from mcp_raspi.security.jwks_fetcher import JWKSFetcher
from mcp_raspi.security.jwt_validator import (
    AuthContext,
    AuthenticationError,
    AuthProvider,
    JWTValidator,
    LocalAuthenticator,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rsa_key_pair() -> tuple[Any, Any]:
    """Generate RSA key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def jwt_validator(rsa_key_pair: tuple[Any, Any]) -> JWTValidator:
    """Create a JWTValidator with mocked JWKS fetcher."""
    _, public_key = rsa_key_pair

    # Create mock JWKS fetcher
    mock_fetcher = mock.AsyncMock(spec=JWKSFetcher)
    mock_fetcher.get_keys.return_value = {
        "test-kid": {"key": public_key, "alg": "RS256"}
    }
    mock_fetcher.get_key_by_kid.return_value = {"key": public_key, "alg": "RS256"}

    return JWTValidator(
        jwks_fetcher=mock_fetcher,
        audience="test-audience",
        issuer="https://test.cloudflareaccess.com",
        role_mappings={"mcp-admins": "admin", "mcp-operators": "operator"},
        default_role="viewer",
    )


@pytest.fixture
def make_token(rsa_key_pair: tuple[Any, Any]):
    """Factory to create JWT tokens for testing."""
    private_key, _ = rsa_key_pair

    def _make_token(
        sub: str = "test-user",
        email: str | None = "test@example.com",
        groups: list[str] | None = None,
        aud: str = "test-audience",
        iss: str = "https://test.cloudflareaccess.com",
        exp: datetime | None = None,
        kid: str = "test-kid",
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create a signed JWT token."""
        if exp is None:
            exp = datetime.now(UTC) + timedelta(hours=1)

        payload: dict[str, Any] = {
            "sub": sub,
            "aud": aud,
            "iss": iss,
            "exp": exp,
            "iat": datetime.now(UTC),
        }

        if email:
            payload["email"] = email

        if groups:
            payload["groups"] = groups

        if additional_claims:
            payload.update(additional_claims)

        return jwt.encode(
            payload,
            private_key,
            algorithm="RS256",
            headers={"kid": kid},
        )

    return _make_token


# =============================================================================
# Tests for AuthContext
# =============================================================================


class TestAuthContext:
    """Tests for AuthContext dataclass."""

    def test_auth_context_creation(self) -> None:
        """Test creating an AuthContext."""
        ctx = AuthContext(
            user_id="user123",
            email="user@example.com",
            groups=["group1", "group2"],
            role="operator",
            authenticated=True,
            auth_method="jwt",
        )

        assert ctx.user_id == "user123"
        assert ctx.email == "user@example.com"
        assert ctx.groups == ["group1", "group2"]
        assert ctx.role == "operator"
        assert ctx.authenticated is True
        assert ctx.auth_method == "jwt"

    def test_auth_context_defaults(self) -> None:
        """Test AuthContext default values."""
        ctx = AuthContext(user_id="user123")

        assert ctx.email is None
        assert ctx.groups == []
        assert ctx.role == "viewer"
        assert ctx.authenticated is True
        assert ctx.auth_method == "jwt"
        assert ctx.token_exp is None

    def test_auth_context_to_dict(self) -> None:
        """Test AuthContext serialization."""
        exp_time = datetime.now(UTC)
        ctx = AuthContext(
            user_id="user123",
            email="user@example.com",
            role="admin",
            token_exp=exp_time,
        )

        result = ctx.to_dict()

        assert result["user_id"] == "user123"
        assert result["email"] == "user@example.com"
        assert result["role"] == "admin"
        assert result["token_exp"] == exp_time.isoformat()


# =============================================================================
# Tests for JWTValidator
# =============================================================================


class TestJWTValidatorValidation:
    """Tests for JWT validation."""

    @pytest.mark.asyncio
    async def test_validate_valid_token(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test validating a valid JWT."""
        token = make_token()

        auth_ctx = await jwt_validator.validate_token(token)

        assert auth_ctx.user_id == "test-user"
        assert auth_ctx.email == "test@example.com"
        assert auth_ctx.authenticated is True
        assert auth_ctx.auth_method == "jwt"

    @pytest.mark.asyncio
    async def test_validate_token_with_groups(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test JWT with groups claim."""
        token = make_token(groups=["mcp-admins", "other-group"])

        auth_ctx = await jwt_validator.validate_token(token)

        assert auth_ctx.groups == ["mcp-admins", "other-group"]
        assert auth_ctx.role == "admin"  # Mapped from mcp-admins

    @pytest.mark.asyncio
    async def test_validate_empty_token(self, jwt_validator: JWTValidator) -> None:
        """Test error when token is empty."""
        with pytest.raises(AuthenticationError, match="No authentication token"):
            await jwt_validator.validate_token("")

    @pytest.mark.asyncio
    async def test_validate_none_token(self, jwt_validator: JWTValidator) -> None:
        """Test error when token is None."""
        with pytest.raises(AuthenticationError):
            await jwt_validator.validate_token(None)  # type: ignore

    @pytest.mark.asyncio
    async def test_validate_malformed_token(self, jwt_validator: JWTValidator) -> None:
        """Test error for malformed token."""
        with pytest.raises(AuthenticationError, match="Invalid token format"):
            await jwt_validator.validate_token("not-a-valid-jwt")

    @pytest.mark.asyncio
    async def test_validate_token_missing_kid(
        self, jwt_validator: JWTValidator, rsa_key_pair: tuple[Any, Any]
    ) -> None:
        """Test error when token missing kid header."""
        private_key, _ = rsa_key_pair
        token = jwt.encode(
            {"sub": "test", "aud": "test-audience", "iss": "https://test.cloudflareaccess.com"},
            private_key,
            algorithm="RS256",
            # No kid in headers
        )

        with pytest.raises(AuthenticationError, match="missing key ID"):
            await jwt_validator.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_expired_token(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test error for expired token."""
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        token = make_token(exp=expired_time)

        with pytest.raises(AuthenticationError, match="Token has expired"):
            await jwt_validator.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_wrong_audience(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test error for wrong audience."""
        token = make_token(aud="wrong-audience")

        with pytest.raises(AuthenticationError, match="Invalid token audience"):
            await jwt_validator.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_wrong_issuer(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test error for wrong issuer."""
        token = make_token(iss="https://wrong-issuer.com")

        with pytest.raises(AuthenticationError, match="Invalid token issuer"):
            await jwt_validator.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_unknown_key(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test error for unknown signing key."""
        # Configure mock to return None for unknown kid
        jwt_validator._jwks_fetcher.get_key_by_kid.return_value = None
        jwt_validator._jwks_fetcher.force_refresh = mock.AsyncMock()

        token = make_token(kid="unknown-kid")

        with pytest.raises(AuthenticationError, match="Unknown signing key"):
            await jwt_validator.validate_token(token)


# =============================================================================
# Tests for Role Mapping
# =============================================================================


class TestRoleMapping:
    """Tests for JWT group to role mapping."""

    @pytest.mark.asyncio
    async def test_map_admin_group(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test mapping admin group to admin role."""
        token = make_token(groups=["mcp-admins"])

        auth_ctx = await jwt_validator.validate_token(token)

        assert auth_ctx.role == "admin"

    @pytest.mark.asyncio
    async def test_map_operator_group(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test mapping operator group to operator role."""
        token = make_token(groups=["mcp-operators"])

        auth_ctx = await jwt_validator.validate_token(token)

        assert auth_ctx.role == "operator"

    @pytest.mark.asyncio
    async def test_map_highest_privilege(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test that highest privilege role is selected."""
        token = make_token(groups=["mcp-operators", "mcp-admins"])

        auth_ctx = await jwt_validator.validate_token(token)

        assert auth_ctx.role == "admin"  # Highest privilege

    @pytest.mark.asyncio
    async def test_default_role_when_no_mapping(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test default role when no groups match."""
        token = make_token(groups=["unknown-group"])

        auth_ctx = await jwt_validator.validate_token(token)

        assert auth_ctx.role == "viewer"  # Default

    @pytest.mark.asyncio
    async def test_default_role_no_groups(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test default role when no groups provided."""
        token = make_token()

        auth_ctx = await jwt_validator.validate_token(token)

        assert auth_ctx.role == "viewer"


# =============================================================================
# Tests for LocalAuthenticator
# =============================================================================


class TestLocalAuthenticator:
    """Tests for local authentication mode."""

    def test_permissive_mode(self) -> None:
        """Test permissive mode allows all requests."""
        auth = LocalAuthenticator(
            permissive_mode=True,
            default_role="admin",
            default_user_id="dev-user",
        )

        ctx = auth.authenticate()

        assert ctx.user_id == "dev-user"
        assert ctx.role == "admin"
        assert ctx.authenticated is True
        assert ctx.auth_method == "permissive"

    def test_static_token_valid(self) -> None:
        """Test valid static token authentication."""
        auth = LocalAuthenticator(
            static_token="secret-token",
            default_role="operator",
            default_user_id="local-user",
        )

        ctx = auth.authenticate(token="secret-token")

        assert ctx.user_id == "local-user"
        assert ctx.role == "operator"
        assert ctx.auth_method == "local_token"

    def test_static_token_invalid(self) -> None:
        """Test invalid static token rejected."""
        auth = LocalAuthenticator(
            static_token="secret-token",
        )

        with pytest.raises(AuthenticationError, match="Invalid local token"):
            auth.authenticate(token="wrong-token")

    def test_no_token_when_required(self) -> None:
        """Test error when no token provided and not permissive."""
        auth = LocalAuthenticator(
            static_token="secret-token",
            permissive_mode=False,
        )

        with pytest.raises(AuthenticationError, match="No authentication token"):
            auth.authenticate()

    def test_from_config(self) -> None:
        """Test LocalAuthenticator creation from config."""
        config = SecurityConfig(
            mode="local",
            local_auth=LocalAuthConfig(
                static_token="test-token",
                permissive_mode=False,
                default_role="viewer",
                default_user_id="config-user",
            ),
        )

        auth = LocalAuthenticator.from_config(config)

        ctx = auth.authenticate(token="test-token")
        assert ctx.user_id == "config-user"
        assert ctx.role == "viewer"


# =============================================================================
# Tests for AuthProvider
# =============================================================================


class TestAuthProvider:
    """Tests for unified AuthProvider."""

    @pytest.mark.asyncio
    async def test_cloudflare_mode(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test AuthProvider in cloudflare mode."""
        provider = AuthProvider(
            mode="cloudflare",
            jwt_validator=jwt_validator,
        )

        token = make_token()
        ctx = await provider.authenticate(token=token)

        assert ctx.authenticated is True
        assert ctx.auth_method == "jwt"

    @pytest.mark.asyncio
    async def test_local_mode(self) -> None:
        """Test AuthProvider in local mode."""
        local_auth = LocalAuthenticator(permissive_mode=True)
        provider = AuthProvider(
            mode="local",
            local_authenticator=local_auth,
        )

        ctx = await provider.authenticate()

        assert ctx.authenticated is True
        assert ctx.auth_method == "permissive"

    @pytest.mark.asyncio
    async def test_extract_token_from_cf_header(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test extracting token from Cloudflare Access header."""
        provider = AuthProvider(
            mode="cloudflare",
            jwt_validator=jwt_validator,
        )

        token = make_token()
        headers = {"Cf-Access-Jwt-Assertion": token}

        ctx = await provider.authenticate(headers=headers)

        assert ctx.authenticated is True

    @pytest.mark.asyncio
    async def test_extract_token_from_auth_header(
        self, jwt_validator: JWTValidator, make_token
    ) -> None:
        """Test extracting token from Authorization header."""
        provider = AuthProvider(
            mode="cloudflare",
            jwt_validator=jwt_validator,
        )

        token = make_token()
        headers = {"Authorization": f"Bearer {token}"}

        ctx = await provider.authenticate(headers=headers)

        assert ctx.authenticated is True

    @pytest.mark.asyncio
    async def test_missing_jwt_validator(self) -> None:
        """Test error when JWT validator not configured."""
        provider = AuthProvider(
            mode="cloudflare",
            jwt_validator=None,
        )

        with pytest.raises(AuthenticationError, match="JWT validator not configured"):
            await provider.authenticate(token="some-token")

    @pytest.mark.asyncio
    async def test_missing_local_authenticator(self) -> None:
        """Test error when local authenticator not configured."""
        provider = AuthProvider(
            mode="local",
            local_authenticator=None,
        )

        with pytest.raises(AuthenticationError, match="Local authenticator not configured"):
            await provider.authenticate()


# =============================================================================
# Tests for JWTValidator from Config
# =============================================================================


class TestJWTValidatorFromConfig:
    """Tests for creating JWTValidator from configuration."""

    def test_from_config(self) -> None:
        """Test JWTValidator creation from SecurityConfig."""
        config = SecurityConfig(
            mode="cloudflare",
            cloudflare_auth=CloudflareAuthConfig(
                jwks_url="https://test.cloudflareaccess.com/cdn-cgi/access/certs",
                audience="test-aud",
                issuer="https://test.cloudflareaccess.com",
            ),
            role_mappings=RoleMappingsConfig(
                groups_to_roles={"admins": "admin"}
            ),
        )

        validator = JWTValidator.from_config(config)

        assert validator._audience == "test-aud"
        assert validator._issuer == "https://test.cloudflareaccess.com"
        assert validator._role_mappings == {"admins": "admin"}

    def test_from_config_with_custom_fetcher(self) -> None:
        """Test JWTValidator creation with custom JWKS fetcher."""
        config = SecurityConfig(mode="cloudflare")
        mock_fetcher = mock.MagicMock(spec=JWKSFetcher)

        validator = JWTValidator.from_config(config, jwks_fetcher=mock_fetcher)

        assert validator._jwks_fetcher is mock_fetcher
