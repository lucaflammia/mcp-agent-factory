"""
Integration tests: TaskScheduler → HTTP MCP Server → Auth layer.

These tests exercise the assembled stack end-to-end, proving the subsystems
wired together in M002 function as a coherent unit.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets

import pytest
from authlib.jose import OctKey
from fastapi.testclient import TestClient

import fakeredis as _fakeredis_mod

from mcp_agent_factory.auth.resource import set_jwt_key as resource_set_key
from mcp_agent_factory.auth.server import (
	_set_auth_redis,
	auth_app,
	set_jwt_key as auth_set_key,
)
from mcp_agent_factory.scheduler import SchedulerState, TaskItem, TaskScheduler
from mcp_agent_factory.server_http import app as http_app
from mcp_agent_factory.server_http_secured import secured_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
	verifier = secrets.token_urlsafe(32)
	digest = hashlib.sha256(verifier.encode()).digest()
	challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
	return verifier, challenge


@pytest.fixture(autouse=True)
def shared_key():
	key = OctKey.generate_key(256, is_private=True)
	auth_set_key(key)
	resource_set_key(key)
	fresh_redis = _fakeredis_mod.FakeRedis(decode_responses=True)
	_set_auth_redis(fresh_redis)
	yield key
	_set_auth_redis(_fakeredis_mod.FakeRedis(decode_responses=True))


@pytest.fixture
def auth_client(shared_key):
	client = TestClient(auth_app)
	client.post("/register", json={
		"client_id": "int-client",
		"client_secret": "int-secret",
		"redirect_uri": "http://localhost/cb",
		"scope": "tools:call",
	})
	return client


def _get_token(auth_client_fixture) -> str:
	verifier, challenge = _pkce_pair()
	code_resp = auth_client_fixture.get("/authorize", params={
		"client_id": "int-client",
		"code_challenge": challenge,
		"code_challenge_method": "S256",
		"scope": "tools:call",
		"user_id": "integration-user",
	})
	code = code_resp.json()["code"]
	token_resp = auth_client_fixture.post("/token", json={
		"code": code,
		"code_verifier": verifier,
		"client_id": "int-client",
		"client_secret": "int-secret",
		"grant_type": "authorization_code",
	})
	return token_resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestSchedulerHTTPIntegration:
	async def test_scheduler_dispatches_to_http_mcp_server(self):
		"""TaskScheduler handler calls the HTTP MCP server and completes successfully."""
		mcp_client = TestClient(http_app)
		results: list[str] = []

		async def echo_handler(item: TaskItem) -> None:
			resp = mcp_client.post("/mcp", json={
				"jsonrpc": "2.0",
				"id": 1,
				"method": "tools/call",
				"params": {"name": "echo", "arguments": {"message": item.args["message"]}},
			})
			results.append(resp.json()["result"]["content"][0]["text"])

		scheduler = TaskScheduler()
		item = TaskItem(name="echo-task", priority=5, args={"message": "hello-integration"})
		await scheduler._dispatch(item, echo_handler)

		assert item.state == SchedulerState.COMPLETED
		assert results == ["hello-integration"]

	async def test_scheduler_dispatches_to_secured_mcp_server(self, auth_client):
		"""TaskScheduler handler calls the auth-protected HTTP MCP server with a valid token."""
		secured_client = TestClient(secured_app)
		token = _get_token(auth_client)
		results: list[str] = []

		async def secured_echo_handler(item: TaskItem) -> None:
			resp = secured_client.post(
				"/mcp",
				json={
					"jsonrpc": "2.0",
					"id": 1,
					"method": "tools/call",
					"params": {"name": "echo", "arguments": {"message": item.args["message"]}},
				},
				headers={"Authorization": f"Bearer {token}"},
			)
			results.append(resp.json()["result"]["content"][0]["text"])

		scheduler = TaskScheduler()
		item = TaskItem(name="secured-echo", priority=10, args={"message": "secured-hello"})
		await scheduler._dispatch(item, secured_echo_handler)

		assert item.state == SchedulerState.COMPLETED
		assert results == ["secured-hello"]

	async def test_full_stack_pkce_session_id_in_claims(self, auth_client, shared_key):
		"""Full flow: PKCE → token → JWT contains session_id in user_id:token format."""
		from authlib.jose import jwt
		from mcp_agent_factory.auth.session import validate_session_id

		token = _get_token(auth_client)
		claims = jwt.decode(token.encode(), shared_key)

		assert "session_id" in claims
		assert validate_session_id(claims["session_id"])
		assert claims["session_id"].startswith("integration-user:")
		assert claims["aud"] == "mcp-server"
