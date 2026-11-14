"""
INT-01 A–D: Gateway–Hermes integration invariant tests.

Covers the four acceptance criteria areas validated manually during INT-01:
  A — Connectivity (dev mode)
  B — Auth modes (token rejection)
  C — Tool scoping (scope-filtered tool lists, out-of-scope denial)
  D — Destructive tools (orchestrate blocked without approval)

No live Hermes, Redis, or Postgres required.  Uses FastAPI TestClient with
MCP_DEV_MODE toggled per fixture and JWTs minted against an in-process key.
"""
from __future__ import annotations

import time

import pytest
from authlib.jose import OctKey, jwt
from fastapi.testclient import TestClient

from mcp_agent_factory.auth.resource import set_jwt_key as resource_set_key
from mcp_agent_factory.gateway.app import gateway_app, set_sampling_client
from mcp_agent_factory.gateway.sampling import StubSamplingClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mint(
    key: OctKey,
    *,
    sub: str = "hermes-test",
    aud: str = "mcp-server",
    scope: str = "tools:call",
    exp_offset: int = 3600,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {"alg": "HS256"},
        {"sub": sub, "aud": aud, "scope": scope, "iat": now, "exp": now + exp_offset,
         "session_id": f"{sub}:test"},
        key,
    ).decode("ascii")


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    body: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def key():
    k = OctKey.generate_key(256, is_private=True)
    resource_set_key(k)
    set_sampling_client(StubSamplingClient())
    return k


@pytest.fixture()
def dev_client(monkeypatch):
    import mcp_agent_factory.gateway.app as _app
    monkeypatch.setattr(_app, "DEV_MODE", True)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    with TestClient(gateway_app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def auth_client(monkeypatch):
    import mcp_agent_factory.gateway.app as _app
    monkeypatch.setattr(_app, "DEV_MODE", False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    with TestClient(gateway_app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Component A — Connectivity
# ---------------------------------------------------------------------------

def test_tools_list_dev_mode_returns_tools(dev_client, key):
    """DEV_MODE: tools/list returns at least the public tools (echo, add)."""
    r = dev_client.post("/mcp", json=_rpc("tools/list"))
    assert r.status_code == 200
    tools = r.json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "echo" in names
    assert "add" in names


def test_echo_call_dev_mode(dev_client, key):
    """DEV_MODE: tools/call echo returns the input text unchanged."""
    r = dev_client.post("/mcp", json=_rpc("tools/call", {"name": "echo", "arguments": {"text": "hello-hermes"}}))
    assert r.status_code == 200
    body = r.json()
    assert "error" not in body
    result = body["result"]
    # echo returns content list or direct text field
    text = ""
    if isinstance(result, dict):
        content = result.get("content", [])
        if content:
            text = content[0].get("text", "")
        elif "text" in result:
            text = result["text"]
    assert "hello-hermes" in text


# ---------------------------------------------------------------------------
# Component B — Auth modes (token rejection)
# ---------------------------------------------------------------------------

def test_missing_token_rejected(auth_client, key):
    """No Authorization header → auth error on tools/call."""
    r = auth_client.post("/mcp", json=_rpc("tools/call", {"name": "echo", "arguments": {"text": "x"}}))
    assert r.status_code == 200
    body = r.json()
    assert body.get("error") is not None
    assert body["error"]["code"] == -32001


def test_expired_token_rejected(auth_client, key):
    """Expired JWT: make_verify_token optional=True returns None → handler returns -32001."""
    token = _mint(key, exp_offset=-10)
    r = auth_client.post("/mcp", json=_rpc("tools/call", {"name": "echo", "arguments": {"text": "x"}}),
                         headers={"Authorization": f"Bearer {token}"})
    # optional=True means invalid token is treated as unauthenticated → JSON-RPC -32001
    assert r.status_code == 200
    assert r.json().get("error", {}).get("code") == -32001


def test_wrong_audience_rejected(auth_client, key):
    """JWT with aud ≠ mcp-server → 401."""
    token = _mint(key, aud="wrong-audience")
    r = auth_client.post("/mcp", json=_rpc("tools/call", {"name": "echo", "arguments": {"text": "x"}}),
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Component C — Tool scoping
# ---------------------------------------------------------------------------

def test_tools_call_scope_shows_expected_tools(auth_client, key):
    """Token with tools:call scope sees at least query_knowledge_base."""
    token = _mint(key, scope="tools:call")
    r = auth_client.post("/mcp", json=_rpc("tools/list"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert "query_knowledge_base" in names
    # orchestrate requires tools:orchestrate — must NOT appear
    assert "orchestrate" not in names


def test_tools_read_scope_rejected_at_middleware(auth_client, key):
    """Token with only tools:read scope → 403 from middleware (POST /mcp requires tools:call)."""
    token = _mint(key, scope="tools:read")
    r = auth_client.post("/mcp", json=_rpc("tools/list"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_no_scope_rejected_at_middleware(auth_client, key):
    """Token with empty scope → 403 from middleware (minimum tools:call required)."""
    token = _mint(key, scope="")
    r = auth_client.post("/mcp", json=_rpc("tools/list"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_out_of_scope_call_denied(auth_client, key):
    """tools:call token calling orchestrate (needs tools:orchestrate) → -32003 from handler.

    Use tools:call scope so the middleware passes, then the per-tool scope check fires.
    """
    token = _mint(key, scope="tools:call")
    r = auth_client.post("/mcp", json=_rpc("tools/call", {"name": "orchestrate", "arguments": {}}),
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    # Either blocked by destructive-tool guard or by scope check — both return -32003
    assert body.get("error") is not None
    assert body["error"]["code"] == -32003


# ---------------------------------------------------------------------------
# Component D — Destructive tools blocked
# ---------------------------------------------------------------------------

def test_orchestrate_blocked_without_approval(auth_client, key):
    """Direct tools/call orchestrate → -32003 destructive-tool error, never executed.

    Token carries both tools:call (to pass middleware) and tools:orchestrate (to pass
    scope check), so the destructive-tool guard in the handler is the decisive control.
    """
    token = _mint(key, scope="tools:call tools:orchestrate")
    r = auth_client.post("/mcp", json=_rpc("tools/call", {"name": "orchestrate", "arguments": {}}),
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("error") is not None
    assert body["error"]["code"] == -32003
    assert "graph-level" in body["error"]["message"] or "approval" in body["error"]["message"]


def test_orchestrate_not_in_tools_list_for_call_scope(auth_client, key):
    """orchestrate requires tools:orchestrate scope; tools:call token must not see it."""
    token = _mint(key, scope="tools:call")
    r = auth_client.post("/mcp", json=_rpc("tools/list"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert "orchestrate" not in names
