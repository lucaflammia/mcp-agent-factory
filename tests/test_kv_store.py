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


# ------------------------------------------------------------------
# Topic affinity
# ------------------------------------------------------------------

async def test_has_affinity_true(kv):
    await kv.add_phrase("agents", "autonomous agent")
    assert await kv.has_affinity("agents", "autonomous agent") is True


async def test_has_affinity_false(kv):
    assert await kv.has_affinity("agents", "deep learning") is False


async def test_affinity_topic_isolation(kv):
    await kv.add_phrase("agents", "orchestration")
    await kv.add_phrase("sessions", "session token")
    assert await kv.has_affinity("agents", "session token") is False
    assert await kv.has_affinity("sessions", "orchestration") is False


async def test_phrases_returns_all(kv):
    await kv.add_phrase("config", "feature flag")
    await kv.add_phrase("config", "rate limit")
    await kv.add_phrase("config", "timeout")
    result = await kv.phrases("config")
    assert result == ["feature flag", "rate limit", "timeout"]


async def test_phrases_not_leaked_into_keys(kv):
    """add_phrase must not appear in keys() results."""
    await kv.add_phrase("agents", "agent loop")
    await kv.set("agents", "a1", {"status": "idle"})
    keys = await kv.keys("agents")
    assert "__phrases__" not in keys
    assert keys == ["a1"]


async def test_affinity_unknown_topic_raises(kv):
    with pytest.raises(ValueError, match="Unknown topic"):
        await kv.has_affinity("unknown", "phrase")

    with pytest.raises(ValueError, match="Unknown topic"):
        await kv.add_phrase("unknown", "phrase")
