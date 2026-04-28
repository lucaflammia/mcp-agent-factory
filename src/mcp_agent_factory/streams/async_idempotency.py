"""AsyncIdempotencyGuard — async prompt-cache backed by Redis (or fakeredis)."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300  # seconds


def _prompt_hash(tool_name: str, args: dict[str, Any]) -> str:
	"""Return a stable SHA-256 hex digest for a (tool_name, args) pair."""
	payload = json.dumps({"tool": tool_name, "args": args}, sort_keys=True)
	return hashlib.sha256(payload.encode()).hexdigest()


class AsyncIdempotencyGuard:
	"""Async prompt-level result cache using a Redis-compatible client.

	``redis_client`` may be a real ``redis.asyncio.Redis`` instance or a
	``fakeredis.aioredis.FakeRedis`` for tests.  The interface is the same.
	"""

	def __init__(self, redis_client: Any, ttl: int = _DEFAULT_TTL) -> None:
		self._r = redis_client
		self._ttl = ttl

	def cache_key(self, tool_name: str, args: dict[str, Any]) -> str:
		return f"prompt_cache:{_prompt_hash(tool_name, args)}"

	async def get(self, key: str) -> str | None:
		"""Return cached result string or None."""
		try:
			value = await self._r.get(key)
		except Exception as exc:  # noqa: BLE001
			logger.warning('{"event":"prompt_cache_read_error","detail":"%s"}', exc)
			return None
		if value is None:
			return None
		return value.decode() if isinstance(value, bytes) else value

	async def set(self, key: str, value: str) -> None:
		"""Store *value* under *key* with the configured TTL.

		Write failures are logged but never propagated — the caller must not
		fail a request because of a cache write error.
		"""
		try:
			await self._r.set(key, value, ex=self._ttl)
		except Exception as exc:  # noqa: BLE001
			logger.warning('{"event":"prompt_cache_write_error","detail":"%s"}', exc)
