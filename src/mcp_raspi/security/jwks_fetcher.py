"""
JWKS (JSON Web Key Set) fetcher for Cloudflare Access JWT validation.

This module handles fetching and caching Cloudflare's public keys used to
verify JWT signatures. Keys are cached to avoid hitting the JWKS endpoint
on every request.

Design follows Doc 04 §3 (Authentication) and §10 (OAuth/JWT Key Rotation).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from jwt.algorithms import RSAAlgorithm

if TYPE_CHECKING:
    from mcp_raspi.config import CloudflareAuthConfig

logger = logging.getLogger("mcp_raspi.security.jwks_fetcher")


class JWKSFetchError(Exception):
    """Exception raised when JWKS fetching fails."""

    pass


class JWKSFetcher:
    """
    Fetches and caches JSON Web Key Sets (JWKS) from Cloudflare Access.

    The JWKS contains the public keys used to verify JWT signatures.
    Keys are cached for a configurable TTL to minimize network requests.

    Attributes:
        jwks_url: URL to the JWKS endpoint.
        cache_ttl: How long to cache the keys (in seconds).

    Example:
        >>> fetcher = JWKSFetcher(
        ...     jwks_url="https://team.cloudflareaccess.com/cdn-cgi/access/certs",
        ...     cache_ttl_seconds=3600
        ... )
        >>> keys = await fetcher.get_keys()
    """

    def __init__(
        self,
        jwks_url: str,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        """
        Initialize the JWKS fetcher.

        Args:
            jwks_url: URL to fetch JWKS from.
            cache_ttl_seconds: How long to cache keys in seconds.
        """
        self._jwks_url = jwks_url
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._keys: dict[str, Any] = {}
        self._cache_expiry: datetime | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(cls, config: CloudflareAuthConfig) -> JWKSFetcher:
        """
        Create a JWKSFetcher from configuration.

        Args:
            config: CloudflareAuthConfig with JWKS settings.

        Returns:
            Configured JWKSFetcher instance.
        """
        return cls(
            jwks_url=config.jwks_url,
            cache_ttl_seconds=config.jwks_cache_ttl_seconds,
        )

    @property
    def jwks_url(self) -> str:
        """Return the JWKS URL."""
        return self._jwks_url

    @property
    def cache_ttl_seconds(self) -> int:
        """Return the cache TTL in seconds."""
        return int(self._cache_ttl.total_seconds())

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid."""
        if self._cache_expiry is None:
            return False
        return datetime.now(UTC) < self._cache_expiry

    async def get_keys(self) -> dict[str, Any]:
        """
        Get the cached keys or fetch fresh ones.

        Returns:
            Dictionary mapping key IDs (kid) to public key objects.

        Raises:
            JWKSFetchError: If fetching JWKS fails.
        """
        async with self._lock:
            if self._is_cache_valid():
                return self._keys

            await self._refresh_keys()
            return self._keys

    async def _refresh_keys(self) -> None:
        """
        Fetch fresh keys from the JWKS endpoint.

        Raises:
            JWKSFetchError: If fetching or parsing fails.
        """
        if not self._jwks_url:
            raise JWKSFetchError("JWKS URL not configured")

        logger.debug("Refreshing JWKS from %s", self._jwks_url)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self._jwks_url)
                response.raise_for_status()
                jwks_data = response.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch JWKS: %s", str(e))
            raise JWKSFetchError(f"Failed to fetch JWKS: {e}") from e
        except ValueError as e:
            logger.error("Failed to parse JWKS response: %s", str(e))
            raise JWKSFetchError(f"Invalid JWKS response: {e}") from e

        # Parse the keys
        try:
            self._keys = self._parse_jwks(jwks_data)
        except Exception as e:
            logger.error("Failed to parse JWKS keys: %s", str(e))
            raise JWKSFetchError(f"Failed to parse JWKS keys: {e}") from e

        # Update cache expiry
        self._cache_expiry = datetime.now(UTC) + self._cache_ttl
        logger.info("JWKS refreshed successfully, %d keys cached", len(self._keys))

    def _parse_jwks(self, jwks_data: dict[str, Any]) -> dict[str, Any]:
        """
        Parse JWKS data into a dictionary of keys.

        Args:
            jwks_data: Raw JWKS JSON data.

        Returns:
            Dictionary mapping key IDs to public key objects.
        """
        keys: dict[str, Any] = {}

        if "keys" not in jwks_data:
            raise ValueError("Invalid JWKS: missing 'keys' field")

        for key_data in jwks_data["keys"]:
            kid = key_data.get("kid")
            if not kid:
                logger.warning("Skipping key without 'kid' field")
                continue

            # Convert JWK to public key object
            try:
                algorithm = key_data.get("alg", "RS256")
                if algorithm.startswith("RS"):
                    # RSA key
                    public_key = RSAAlgorithm.from_jwk(key_data)
                    keys[kid] = {
                        "key": public_key,
                        "alg": algorithm,
                    }
                else:
                    logger.warning(
                        "Unsupported key algorithm: %s for kid=%s", algorithm, kid
                    )
            except Exception as e:
                logger.warning("Failed to parse key with kid=%s: %s", kid, str(e))
                continue

        return keys

    def get_key_by_kid(self, kid: str) -> dict[str, Any] | None:
        """
        Get a specific key by its key ID (kid).

        Note: This method does not refresh the cache. Call get_keys() first
        if you need to ensure the cache is up to date.

        Args:
            kid: Key ID to look up.

        Returns:
            Key data dictionary or None if not found.
        """
        return self._keys.get(kid)

    async def force_refresh(self) -> dict[str, Any]:
        """
        Force a refresh of the JWKS cache.

        Returns:
            Dictionary mapping key IDs to public key objects.

        Raises:
            JWKSFetchError: If fetching JWKS fails.
        """
        async with self._lock:
            await self._refresh_keys()
            return self._keys

    def clear_cache(self) -> None:
        """Clear the cached keys."""
        self._keys = {}
        self._cache_expiry = None
