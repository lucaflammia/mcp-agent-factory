"""
RedisSessionManager — async Redis-backed session store for cross-agent state.

Provides a simple set/get/delete interface over any redis.asyncio client
(real redis.asyncio or fakeredis.aioredis for tests).

Values are serialized as JSON strings so structured Pydantic model dicts
round-trip cleanly.

Usage::

	import fakeredis.aioredis
	client = fakeredis.aioredis.FakeRedis()
	session = RedisSessionManager(client)
	await session.set("key", {"result": 42})
	data = await session.get("key")   # {"result": 42}
"""
from __future__ import annotations

import json
from typing import Any


class RedisSessionManager:
	"""
	Async session store backed by a redis.asyncio-compatible client.

	Parameters
	----------
	client :
		Any object with async get(key), set(key, value), delete(key) methods.
		Accepts redis.asyncio.Redis or fakeredis.aioredis.FakeRedis.
	"""

	def __init__(self, client: Any) -> None:
		self._client = client

	async def set(self, key: str, value: dict[str, Any]) -> None:
		"""Persist *value* dict under *key* as a JSON string."""
		await self._client.set(key, json.dumps(value))

	async def get(self, key: str) -> dict[str, Any] | None:
		"""Retrieve and deserialize the value stored under *key*, or None."""
		raw = await self._client.get(key)
		if raw is None:
			return None
		if isinstance(raw, bytes):
			raw = raw.decode()
		return json.loads(raw)

	async def delete(self, key: str) -> None:
		"""Remove the value stored under *key*."""
		await self._client.delete(key)
