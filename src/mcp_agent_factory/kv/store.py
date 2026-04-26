"""Redis-backed key-value store with topic namespacing."""
from __future__ import annotations

import json
from typing import Any


class RedisKVStore:
    """
    Async key-value store backed by a redis.asyncio-compatible client.

    Keys are namespaced under a topic: ``kv:<topic>:<key>``.
    Accepts redis.asyncio.Redis or fakeredis.aioredis.FakeRedis.
    """

    def __init__(self, client: Any, topics: list[str]) -> None:
        self._client = client
        self._topics = set(topics)

    def _key(self, topic: str, key: str) -> str:
        if topic not in self._topics:
            raise ValueError(f"Unknown topic {topic!r}. Registered: {sorted(self._topics)}")
        return f"kv:{topic}:{key}"

    async def set(self, topic: str, key: str, value: Any) -> None:
        await self._client.set(self._key(topic, key), json.dumps(value))

    async def get(self, topic: str, key: str) -> Any | None:
        raw = await self._client.get(self._key(topic, key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    async def delete(self, topic: str, key: str) -> None:
        await self._client.delete(self._key(topic, key))

    async def keys(self, topic: str) -> list[str]:
        if topic not in self._topics:
            raise ValueError(f"Unknown topic {topic!r}. Registered: {sorted(self._topics)}")
        prefix = f"kv:{topic}:"
        raw_keys = await self._client.keys(f"{prefix}*")
        return [
            (k.decode() if isinstance(k, bytes) else k).removeprefix(prefix)
            for k in raw_keys
            # exclude the internal phrase-set key
            if (k.decode() if isinstance(k, bytes) else k) != f"{prefix}__phrases__"
        ]

    # ------------------------------------------------------------------
    # Topic affinity — phrase membership via Redis Set
    # ------------------------------------------------------------------

    def _phrase_key(self, topic: str) -> str:
        if topic not in self._topics:
            raise ValueError(f"Unknown topic {topic!r}. Registered: {sorted(self._topics)}")
        return f"kv:{topic}:__phrases__"

    async def add_phrase(self, topic: str, phrase: str) -> None:
        """Register *phrase* as belonging to *topic*."""
        await self._client.sadd(self._phrase_key(topic), phrase)

    async def has_affinity(self, topic: str, phrase: str) -> bool:
        """Return True if *phrase* was registered under *topic*."""
        return bool(await self._client.sismember(self._phrase_key(topic), phrase))

    async def phrases(self, topic: str) -> list[str]:
        """Return all phrases registered under *topic*."""
        raw = await self._client.smembers(self._phrase_key(topic))
        return sorted(m.decode() if isinstance(m, bytes) else m for m in raw)
