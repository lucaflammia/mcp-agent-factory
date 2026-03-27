"""
Tests for the LangChain / MCP bridge: OAuthMiddleware and MCPGatewayClient.
"""
from __future__ import annotations

import time

import pytest
import httpx
from authlib.jose import OctKey, jwt

from mcp_agent_factory.auth.resource import set_jwt_key as resource_set_key
from mcp_agent_factory.gateway.app import gateway_app
from mcp_agent_factory.bridge.oauth_middleware import OAuthMiddleware
from mcp_agent_factory.bridge.gateway_client import MCPGatewayClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(key: OctKey, *, scope: str = "tools:call", exp_offset: int = 3600) -> str:
	now = int(time.time())
	claims = {
		"sub": "bridge-user",
		"aud": "mcp-server",
		"scope": scope,
		"iat": now,
		"exp": now + exp_offset,
		"session_id": "bridge-user:testsession",
	}
	return jwt.encode({"alg": "HS256"}, claims, key).decode("ascii")


def _factory(key: OctKey) -> tuple[str, int]:
	"""Token factory: returns (token_str, expires_at)."""
	now = int(time.time())
	token = _make_token(key)
	return token, now + 3600


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def shared_key():
	key = OctKey.generate_key(256, is_private=True)
	resource_set_key(key)
	yield key


@pytest.fixture
def middleware(shared_key):
	call_count = {"n": 0}

	def factory():
		call_count["n"] += 1
		return _factory(shared_key)

	m = OAuthMiddleware(factory)
	m._call_count = call_count  # expose for assertions
	return m


@pytest.fixture
def gw_client(middleware):
	transport = httpx.ASGITransport(app=gateway_app)
	return MCPGatewayClient(
		base_url="http://testserver",
		middleware=middleware,
		transport=transport,
	)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_oauth_middleware_gets_token(middleware):
	headers = await middleware.inject({})
	assert "Authorization" in headers
	assert headers["Authorization"].startswith("Bearer ")


@pytest.mark.anyio
async def test_mcp_gateway_client_list_tools(gw_client):
	tools = await gw_client.list_tools()
	assert isinstance(tools, list)
	assert any(t["name"] == "echo" for t in tools)


@pytest.mark.anyio
async def test_mcp_gateway_client_call_echo(gw_client):
	result = await gw_client.call_tool("echo", {"text": "hello bridge"})
	content = result["content"]
	assert content[0]["text"] == "hello bridge"


@pytest.mark.anyio
async def test_token_cached_between_calls(gw_client, middleware):
	await gw_client.list_tools()
	await gw_client.list_tools()
	# factory should have been called exactly once (cache hit on second call)
	assert middleware._call_count["n"] == 1
