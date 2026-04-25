"""
OAuth middleware for the MCP Gateway bridge.

OAuthMiddleware manages Bearer token injection for outbound requests.
Supports both sync and async token factories so tests can inject tokens
directly, and real deployments can perform async HTTP calls (e.g. the
client_credentials flow implemented in make_client_credentials_factory).

Observability: token fetch attempts and cache hits logged at DEBUG.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# A sync or async callable that returns (token_str, exp_timestamp).
TokenFactory = Callable[[], tuple[str, int] | Coroutine[Any, Any, tuple[str, int]]]


def make_client_credentials_factory(
    auth_server_url: str,
    client_id: str,
    client_secret: str,
    scope: str = "tools:call",
) -> TokenFactory:
    """
    Return an async token factory that fetches a token via client_credentials.

    Parameters
    ----------
    auth_server_url:
        Base URL of the auth server (e.g. ``http://localhost:8001``).
    client_id, client_secret:
        Credentials registered with the auth server via POST /register.
    scope:
        Space-separated OAuth scopes to request.
    """
    async def _factory() -> tuple[str, int]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{auth_server_url.rstrip('/')}/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": scope,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        expires_at = int(time.time()) + data.get("expires_in", 3600)
        logger.debug("oauth_middleware: client_credentials token acquired")
        return data["access_token"], expires_at

    return _factory


class OAuthMiddleware:
    """
    Injects a Bearer token into request headers.

    Parameters
    ----------
    token_factory:
        Sync or async callable ``() -> (token_str, expires_at_unix)``.
        Called lazily; result is cached until ``expires_at - 60`` seconds.
    """

    def __init__(self, token_factory: TokenFactory) -> None:
        self._factory = token_factory
        self._token: str | None = None
        self._expires_at: float = 0.0

    def _is_valid(self) -> bool:
        return self._token is not None and time.time() < self._expires_at - 60

    async def get_token(self) -> str:
        """Return a cached or freshly-fetched token."""
        if self._is_valid():
            logger.debug("oauth_middleware: cache hit, token still valid")
            return self._token  # type: ignore[return-value]

        logger.debug("oauth_middleware: fetching new token")
        result = self._factory()
        # Support both sync and async factories
        if hasattr(result, "__await__"):
            token, expires_at = await result  # type: ignore[misc]
        else:
            token, expires_at = result  # type: ignore[assignment]
        self._token = token
        self._expires_at = float(expires_at)
        logger.debug("oauth_middleware: token cached until %s", expires_at)
        return self._token

    async def inject(self, headers: dict) -> dict:
        """Return *headers* extended with an Authorization: Bearer header."""
        token = await self.get_token()
        return {**headers, "Authorization": f"Bearer {token}"}
