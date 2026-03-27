"""
OAuth middleware for the MCP Gateway bridge.

OAuthMiddleware manages Bearer token injection for outbound requests.
In production it would perform a client_credentials flow; since the M002
auth server only supports authorization_code, we expose a token_factory
hook so tests can inject tokens directly.

Observability: token fetch attempts and cache hits logged at DEBUG.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

# A callable that returns (token_str, exp_timestamp).
TokenFactory = Callable[[], tuple[str, int]]


class OAuthMiddleware:
	"""
	Injects a Bearer token into request headers.

	Parameters
	----------
	token_factory:
		Callable ``() -> (token_str, expires_at_unix)``.
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
		token, expires_at = self._factory()
		self._token = token
		self._expires_at = float(expires_at)
		logger.debug("oauth_middleware: token cached until %s", expires_at)
		return self._token

	async def inject(self, headers: dict) -> dict:
		"""Return *headers* extended with an Authorization: Bearer header."""
		token = await self.get_token()
		return {**headers, "Authorization": f"Bearer {token}"}
