"""Tests for the kv/add_phrase and kv/check_affinity MCP tools via the gateway."""
from __future__ import annotations

import pytest
import fakeredis.aioredis

from fastapi.testclient import TestClient

from mcp_agent_factory.gateway.app import gateway_app, set_kv_store
from mcp_agent_factory.kv.store import RedisKVStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def inject_kv_store():
    """Fresh in-memory KV store per test with a set of known topics."""
    client = fakeredis.aioredis.FakeRedis()
    store = RedisKVStore(client, topics=["sports", "finance", "tech", "default"])
    set_kv_store(store)
    yield store


@pytest.fixture
def client(monkeypatch):
    import mcp_agent_factory.gateway.app as _app
    monkeypatch.setattr(_app, "DEV_MODE", True)
    return TestClient(gateway_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(client: TestClient, tool: str, **args) -> dict:
    resp = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
        "id": 1,
    })
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# kv/add_phrase tests
# ---------------------------------------------------------------------------

def test_add_phrase_returns_confirmation(client):
    body = _call(client, "kv/add_phrase", topic="sports", phrase="hat trick")
    assert "hat trick" in body["result"]["content"][0]["text"]
    assert "sports" in body["result"]["content"][0]["text"]


def test_add_phrase_missing_args_returns_error(client):
    body = _call(client, "kv/add_phrase", topic="sports")
    assert body["result"]["isError"] is True


# ---------------------------------------------------------------------------
# kv/check_affinity tests
# ---------------------------------------------------------------------------

def test_check_affinity_true_after_add(client):
    _call(client, "kv/add_phrase", topic="finance", phrase="hedge fund")
    body = _call(client, "kv/check_affinity", topic="finance", phrase="hedge fund")
    assert body["result"]["content"][0]["text"] == "true"


def test_check_affinity_false_for_unregistered(client):
    body = _call(client, "kv/check_affinity", topic="finance", phrase="goal kick")
    assert body["result"]["content"][0]["text"] == "false"


def test_check_affinity_topic_isolation(client):
    _call(client, "kv/add_phrase", topic="sports", phrase="penalty shootout")
    body = _call(client, "kv/check_affinity", topic="finance", phrase="penalty shootout")
    assert body["result"]["content"][0]["text"] == "false"


def test_check_affinity_unknown_topic_returns_error(client):
    body = _call(client, "kv/check_affinity", topic="nonexistent", phrase="anything")
    assert body["result"]["isError"] is True


def test_add_phrase_unknown_topic_returns_error(client):
    body = _call(client, "kv/add_phrase", topic="nonexistent", phrase="anything")
    assert body["result"]["isError"] is True


# ---------------------------------------------------------------------------
# tools/list includes kv tools
# ---------------------------------------------------------------------------

def test_tools_list_includes_kv_tools(client):
    resp = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 2,
    })
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "kv/add_phrase" in names
    assert "kv/check_affinity" in names
