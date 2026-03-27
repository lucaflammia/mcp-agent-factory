"""
Tests for the MCP API Gateway: tool routing, auth, sampling, SSE, and bus events.
"""
from __future__ import annotations

import time

import pytest
from authlib.jose import OctKey, jwt
from fastapi.testclient import TestClient

from mcp_agent_factory.auth.resource import set_jwt_key as resource_set_key
from mcp_agent_factory.gateway.app import gateway_app, bus, set_sampling_client
from mcp_agent_factory.gateway.sampling import SamplingClient, SamplingResult, StubSamplingClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(
    key: OctKey,
    *,
    sub: str = "user1",
    aud: str = "mcp-server",
    scope: str = "tools:call",
    exp_offset: int = 3600,
) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "aud": aud,
        "scope": scope,
        "iat": now,
        "exp": now + exp_offset,
        "session_id": f"{sub}:testsession",
    }
    return jwt.encode({"alg": "HS256"}, claims, key).decode("ascii")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def shared_key():
    """Fresh key per test; inject into resource server and reset sampling client."""
    key = OctKey.generate_key(256, is_private=True)
    resource_set_key(key)
    set_sampling_client(StubSamplingClient())
    yield key


@pytest.fixture
def client():
    return TestClient(gateway_app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_unauthenticated(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_mcp_no_auth_returns_401(client):
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
    assert resp.status_code == 401


def test_tools_list_authenticated(client, shared_key):
    token = _make_token(shared_key)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body
    tools = body["result"]["tools"]
    assert any(t["name"] == "echo" for t in tools)


def test_call_echo_authenticated(client, shared_key):
    token = _make_token(shared_key)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hello gateway"}},
            "id": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    content = resp.json()["result"]["content"]
    assert content[0]["text"] == "hello gateway"


def test_call_unknown_tool_returns_is_error(client, shared_key):
    token = _make_token(shared_key)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
            "id": 3,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result.get("isError") is True


def test_sampling_endpoint(client):
    resp = client.post("/sampling", json={"prompt": "tell me about AI"})
    assert resp.status_code == 200
    body = resp.json()
    assert "completion" in body
    assert "prompt" in body


def test_sampling_stub_returns_prompt_prefix(client):
    resp = client.post("/sampling", json={"prompt": "hello world"})
    assert resp.status_code == 200
    assert resp.json()["completion"].startswith("[stub]")


def test_sse_route_registered(client):
    # The SSE sub-app is mounted; verify the mount point exists by checking routes
    routes = [r.path for r in gateway_app.routes]
    # The SSE app is mounted at /sse so it appears as a Mount
    mounts = [str(getattr(r, 'path', '')) for r in gateway_app.routes]
    assert any("/sse" in m for m in mounts)


def test_gateway_publishes_message_on_tool_call(client, shared_key):
    # Subscribe to the gateway topic before making the call
    q = bus.subscribe("gateway.tool_calls")

    token = _make_token(shared_key)
    client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "bus test"}},
            "id": 4,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert not q.empty()
    msg = q.get_nowait()
    assert msg.sender == "gateway"
    assert msg.content["tool"] == "echo"
