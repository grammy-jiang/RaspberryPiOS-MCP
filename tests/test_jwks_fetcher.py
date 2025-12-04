"""
Tests for the JWKS fetcher module.

Tests cover:
- JWKS fetching and caching
- Cache expiration and refresh
- Error handling for network failures
- Key parsing and lookup
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

import httpx
import pytest

from mcp_raspi.config import CloudflareAuthConfig
from mcp_raspi.security.jwks_fetcher import JWKSFetcher, JWKSFetchError

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_jwks() -> dict[str, Any]:
    """Sample JWKS response for testing."""
    return {
        "keys": [
            {
                "kid": "test-key-1",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                "e": "AQAB",
            },
            {
                "kid": "test-key-2",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                "e": "AQAB",
            },
        ]
    }


@pytest.fixture
def jwks_fetcher() -> JWKSFetcher:
    """Create a JWKSFetcher for testing."""
    return JWKSFetcher(
        jwks_url="https://test.cloudflareaccess.com/cdn-cgi/access/certs",
        cache_ttl_seconds=3600,
    )


# =============================================================================
# Tests for JWKSFetcher Initialization
# =============================================================================


class TestJWKSFetcherInit:
    """Tests for JWKSFetcher initialization."""

    def test_init_with_url(self) -> None:
        """Test JWKSFetcher initialization with URL."""
        fetcher = JWKSFetcher(
            jwks_url="https://example.com/certs",
            cache_ttl_seconds=1800,
        )
        assert fetcher.jwks_url == "https://example.com/certs"
        assert fetcher.cache_ttl_seconds == 1800

    def test_from_config(self) -> None:
        """Test JWKSFetcher creation from config."""
        config = CloudflareAuthConfig(
            jwks_url="https://team.cloudflareaccess.com/cdn-cgi/access/certs",
            audience="test-audience",
            issuer="https://team.cloudflareaccess.com",
            jwks_cache_ttl_seconds=7200,
        )
        fetcher = JWKSFetcher.from_config(config)
        assert fetcher.jwks_url == config.jwks_url
        assert fetcher.cache_ttl_seconds == 7200


# =============================================================================
# Tests for JWKS Fetching
# =============================================================================


class TestJWKSFetching:
    """Tests for JWKS fetching functionality."""

    @pytest.mark.asyncio
    async def test_get_keys_success(
        self, jwks_fetcher: JWKSFetcher, sample_jwks: dict[str, Any]
    ) -> None:
        """Test successful JWKS fetch."""
        mock_response = mock.MagicMock()  # Use MagicMock since json() is sync
        mock_response.json.return_value = sample_jwks
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            keys = await jwks_fetcher.get_keys()

            assert len(keys) == 2
            assert "test-key-1" in keys
            assert "test-key-2" in keys
            assert keys["test-key-1"]["alg"] == "RS256"

    @pytest.mark.asyncio
    async def test_get_keys_uses_cache(
        self, jwks_fetcher: JWKSFetcher, sample_jwks: dict[str, Any]
    ) -> None:
        """Test that subsequent calls use cached keys."""
        mock_response = mock.MagicMock()  # Use MagicMock since json() is sync
        mock_response.json.return_value = sample_jwks
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # First call - should fetch
            keys1 = await jwks_fetcher.get_keys()
            # Second call - should use cache
            keys2 = await jwks_fetcher.get_keys()

            # Should only fetch once
            assert mock_client.get.call_count == 1
            assert keys1 == keys2

    @pytest.mark.asyncio
    async def test_get_keys_empty_url(self) -> None:
        """Test error when JWKS URL is empty."""
        fetcher = JWKSFetcher(jwks_url="", cache_ttl_seconds=3600)

        with pytest.raises(JWKSFetchError, match="JWKS URL not configured"):
            await fetcher.get_keys()

    @pytest.mark.asyncio
    async def test_get_keys_network_error(self, jwks_fetcher: JWKSFetcher) -> None:
        """Test error handling for network failures."""
        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection failed")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(JWKSFetchError, match="Failed to fetch JWKS"):
                await jwks_fetcher.get_keys()

    @pytest.mark.asyncio
    async def test_get_keys_invalid_json(self, jwks_fetcher: JWKSFetcher) -> None:
        """Test error handling for invalid JSON response."""
        mock_response = mock.MagicMock()  # json() is sync
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(JWKSFetchError, match="Invalid JWKS response"):
                await jwks_fetcher.get_keys()

    @pytest.mark.asyncio
    async def test_get_keys_missing_keys_field(self, jwks_fetcher: JWKSFetcher) -> None:
        """Test error when JWKS response missing 'keys' field."""
        mock_response = mock.MagicMock()  # json() is sync
        mock_response.json.return_value = {"invalid": "response"}
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(JWKSFetchError, match="Failed to parse JWKS keys"):
                await jwks_fetcher.get_keys()


# =============================================================================
# Tests for Cache Behavior
# =============================================================================


class TestJWKSCaching:
    """Tests for JWKS caching behavior."""

    def test_cache_initially_invalid(self, jwks_fetcher: JWKSFetcher) -> None:
        """Test that cache is initially invalid."""
        assert jwks_fetcher._is_cache_valid() is False

    @pytest.mark.asyncio
    async def test_cache_valid_after_fetch(
        self, jwks_fetcher: JWKSFetcher, sample_jwks: dict[str, Any]
    ) -> None:
        """Test that cache is valid after successful fetch."""
        mock_response = mock.MagicMock()  # json() is sync
        mock_response.json.return_value = sample_jwks
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await jwks_fetcher.get_keys()
            assert jwks_fetcher._is_cache_valid() is True

    def test_clear_cache(self, jwks_fetcher: JWKSFetcher) -> None:
        """Test cache clearing."""
        # Set up some cached data
        jwks_fetcher._keys = {"key1": {"alg": "RS256"}}
        jwks_fetcher._cache_expiry = datetime.now(UTC) + timedelta(hours=1)

        assert jwks_fetcher._is_cache_valid() is True

        jwks_fetcher.clear_cache()

        assert jwks_fetcher._is_cache_valid() is False
        assert jwks_fetcher._keys == {}

    @pytest.mark.asyncio
    async def test_force_refresh(
        self, jwks_fetcher: JWKSFetcher, sample_jwks: dict[str, Any]
    ) -> None:
        """Test force refresh bypasses cache."""
        mock_response = mock.MagicMock()  # json() is sync
        mock_response.json.return_value = sample_jwks
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # First fetch
            await jwks_fetcher.get_keys()
            assert mock_client.get.call_count == 1

            # Force refresh should fetch again
            await jwks_fetcher.force_refresh()
            assert mock_client.get.call_count == 2


# =============================================================================
# Tests for Key Lookup
# =============================================================================


class TestKeyLookup:
    """Tests for key lookup functionality."""

    @pytest.mark.asyncio
    async def test_get_key_by_kid(
        self, jwks_fetcher: JWKSFetcher, sample_jwks: dict[str, Any]
    ) -> None:
        """Test getting a specific key by kid."""
        mock_response = mock.MagicMock()  # json() is sync
        mock_response.json.return_value = sample_jwks
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await jwks_fetcher.get_keys()

            key1 = jwks_fetcher.get_key_by_kid("test-key-1")
            assert key1 is not None
            assert key1["alg"] == "RS256"

            key_unknown = jwks_fetcher.get_key_by_kid("unknown-key")
            assert key_unknown is None

    def test_get_key_by_kid_empty_cache(self, jwks_fetcher: JWKSFetcher) -> None:
        """Test getting key from empty cache returns None."""
        key = jwks_fetcher.get_key_by_kid("any-key")
        assert key is None


# =============================================================================
# Tests for Key Parsing
# =============================================================================


class TestKeyParsing:
    """Tests for JWK to public key parsing."""

    @pytest.mark.asyncio
    async def test_parse_rsa_keys(
        self, jwks_fetcher: JWKSFetcher, sample_jwks: dict[str, Any]
    ) -> None:
        """Test parsing RSA keys from JWKS."""
        mock_response = mock.MagicMock()  # json() is sync
        mock_response.json.return_value = sample_jwks
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            keys = await jwks_fetcher.get_keys()

            # Verify keys were parsed
            assert len(keys) == 2
            for _kid, key_data in keys.items():
                assert "key" in key_data
                assert "alg" in key_data
                assert key_data["alg"] == "RS256"

    @pytest.mark.asyncio
    async def test_skip_key_without_kid(self, jwks_fetcher: JWKSFetcher) -> None:
        """Test that keys without kid are skipped."""
        jwks_without_kid = {
            "keys": [
                {
                    "kty": "RSA",
                    "alg": "RS256",
                    "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                    "e": "AQAB",
                }
            ]
        }
        mock_response = mock.MagicMock()  # json() is sync
        mock_response.json.return_value = jwks_without_kid
        mock_response.raise_for_status = mock.Mock()

        with mock.patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock.AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            keys = await jwks_fetcher.get_keys()
            assert len(keys) == 0
