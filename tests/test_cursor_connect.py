"""
Tests for Cursor / external-CLI connectivity:
  - Auth server RFC 8414 discovery endpoint
  - Gateway discovery proxy
  - Gateway 401 includes WWW-Authenticate header
"""
from __future__ import annotations

import base64
import hashlib
import time

import fakeredis
import pytest
from authlib.jose import OctKey, jwt
from httpx import AsyncClient, ASGITransport

from mcp_agent_factory.auth.server import auth_app, _set_auth_redis
from mcp_agent_factory.auth import resource as _resource
from mcp_agent_factory.gateway.app import gateway_app


def _make_wrong_aud_token() -> str:
    """Create a signed JWT with aud != 'mcp-server' to trigger 401."""
    key = OctKey.generate_key(256, is_private=True)
    _resource.set_jwt_key(key)
    payload = {
        "sub": "test-user",
        "aud": "some-other-service",
        "scope": "tools:call",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token_bytes = jwt.encode({"alg": "HS256"}, payload, key)
    return token_bytes.decode() if isinstance(token_bytes, bytes) else token_bytes


@pytest.fixture(autouse=True)
def _isolated_auth_redis():
    _set_auth_redis(fakeredis.FakeRedis(decode_responses=True))
    yield


# ---------------------------------------------------------------------------
# Auth server discovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_discovery_returns_required_fields():
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/oauth-authorization-server")

    assert resp.status_code == 200
    body = resp.json()
    assert "issuer" in body
    assert "authorization_endpoint" in body
    assert "token_endpoint" in body
    assert "registration_endpoint" in body
    assert "S256" in body.get("code_challenge_methods_supported", [])


@pytest.mark.asyncio
async def test_auth_discovery_scopes_listed():
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/oauth-authorization-server")

    body = resp.json()
    scopes = body.get("scopes_supported", [])
    assert "tools:call" in scopes


# ---------------------------------------------------------------------------
# Gateway 401 → WWW-Authenticate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gateway_401_includes_www_authenticate():
    """A token with wrong audience triggers HTTP 401 + WWW-Authenticate header."""
    token = _make_wrong_aud_token()
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "echo", "arguments": {"text": "hi"}}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers
    assert "Bearer" in resp.headers["WWW-Authenticate"]
    assert "resource_metadata" in resp.headers["WWW-Authenticate"]


# ---------------------------------------------------------------------------
# Gateway discovery proxy (fallback path — auth server not running in tests)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gateway_discovery_proxy_returns_endpoints():
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/oauth-authorization-server")

    assert resp.status_code == 200
    body = resp.json()
    assert "authorization_endpoint" in body
    assert "token_endpoint" in body
