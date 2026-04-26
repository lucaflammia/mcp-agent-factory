"""Tests for RedisKVStore using fakeredis."""
from __future__ import annotations

import pytest
import fakeredis.aioredis

from mcp_agent_factory.kv import RedisKVStore


@pytest.fixture
async def kv():
    client = fakeredis.aioredis.FakeRedis()
    store = RedisKVStore(client, topics=["agents", "sessions", "config"])
    yield store
    await client.aclose()


async def test_set_and_get(kv):
    await kv.set("agents", "agent-1", {"status": "idle"})
    result = await kv.get("agents", "agent-1")
    assert result == {"status": "idle"}


async def test_get_missing_returns_none(kv):
    assert await kv.get("agents", "nonexistent") is None


async def test_delete(kv):
    await kv.set("sessions", "s1", {"user": "alice"})
    await kv.delete("sessions", "s1")
    assert await kv.get("sessions", "s1") is None


async def test_topic_isolation(kv):
    await kv.set("agents", "x", 1)
    await kv.set("sessions", "x", 2)
    assert await kv.get("agents", "x") == 1
    assert await kv.get("sessions", "x") == 2


async def test_keys(kv):
    await kv.set("config", "host", "localhost")
    await kv.set("config", "port", 6379)
    keys = await kv.keys("config")
    assert sorted(keys) == ["host", "port"]


async def test_unknown_topic_raises(kv):
    with pytest.raises(ValueError, match="Unknown topic"):
        await kv.set("unknown", "k", "v")

    with pytest.raises(ValueError, match="Unknown topic"):
        await kv.get("unknown", "k")

    with pytest.raises(ValueError, match="Unknown topic"):
        await kv.keys("unknown")


async def test_values_roundtrip_types(kv):
    await kv.set("agents", "int-val", 42)
    await kv.set("agents", "list-val", [1, 2, 3])
    await kv.set("agents", "nested", {"a": {"b": True}})

    assert await kv.get("agents", "int-val") == 42
    assert await kv.get("agents", "list-val") == [1, 2, 3]
    assert await kv.get("agents", "nested") == {"a": {"b": True}}
