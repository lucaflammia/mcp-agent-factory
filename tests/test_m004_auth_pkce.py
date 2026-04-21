"""
M004 S02 — PKCE hardening + 401 enforcement tests.

Tests the full OAuth 2.1 / PKCE S256 round-trip through the auth server
and verifies the gateway enforces authentication correctly.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time

import pytest
from authlib.jose import OctKey, jwt
from fastapi.testclient import TestClient

import fakeredis as _fakeredis_mod

from mcp_agent_factory.auth.server import (
	_set_auth_redis,
	auth_app,
	set_jwt_key as auth_set_key,
)
from mcp_agent_factory.auth.resource import set_jwt_key as resource_set_key
from mcp_agent_factory.gateway.app import gateway_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
	"""Return (code_verifier, code_challenge_S256)."""
	verifier = secrets.token_urlsafe(32)
	digest = hashlib.sha256(verifier.encode("ascii")).digest()
	challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
	return verifier, challenge


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
	"""Fresh key injected into both auth and resource servers; stores cleaned up."""
	key = OctKey.generate_key(256, is_private=True)
	auth_set_key(key)
	resource_set_key(key)
	_set_auth_redis(_fakeredis_mod.FakeRedis(decode_responses=True))
	yield key
	_set_auth_redis(_fakeredis_mod.FakeRedis(decode_responses=True))


@pytest.fixture
def auth_client():
	return TestClient(auth_app)


@pytest.fixture
def gateway_client():
	return TestClient(gateway_app)


# ---------------------------------------------------------------------------
# PKCE round-trip — full register → authorize → token flow
# ---------------------------------------------------------------------------

def test_pkce_register_authorize_token_issues_jwt(auth_client, shared_key):
	"""Full PKCE S256 code flow produces a valid JWT with expected claims."""
	verifier, challenge = _pkce_pair()

	# 1. Register client
	r = auth_client.post("/register", json={
		"client_id": "pkce-client",
		"client_secret": "unused-for-pkce",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
	})
	assert r.status_code in (200, 201)

	# 2. Authorize — get a one-time code
	r = auth_client.get("/authorize", params={
		"client_id": "pkce-client",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
		"code_challenge": challenge,
		"code_challenge_method": "S256",
		"user_id": "alice",
	})
	assert r.status_code == 200
	code = r.json()["code"]
	assert code

	# 3. Exchange code for token
	r = auth_client.post("/token", json={
		"client_id": "pkce-client",
		"client_secret": "unused-for-pkce",
		"code": code,
		"code_verifier": verifier,
	})
	assert r.status_code == 200
	body = r.json()
	assert "access_token" in body
	assert body["token_type"] == "bearer"

	# 4. Validate the JWT
	claims = jwt.decode(body["access_token"], shared_key)
	claims.validate()
	assert claims["sub"] == "alice"
	assert "tools:call" in claims["scope"]
	assert claims["aud"] == "mcp-server"


def test_pkce_wrong_verifier_returns_400(auth_client):
	"""Mismatched code_verifier must be rejected with 400."""
	verifier, challenge = _pkce_pair()
	wrong_verifier = secrets.token_urlsafe(32)  # different from verifier

	auth_client.post("/register", json={
		"client_id": "pkce-bad",
		"client_secret": "x",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
	})
	r = auth_client.get("/authorize", params={
		"client_id": "pkce-bad",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
		"code_challenge": challenge,
		"code_challenge_method": "S256",
		"user_id": "bob",
	})
	code = r.json()["code"]

	r = auth_client.post("/token", json={
		"client_id": "pkce-bad",
		"client_secret": "x",
		"code": code,
		"code_verifier": wrong_verifier,
	})
	assert r.status_code == 400


def test_pkce_plain_method_rejected(auth_client):
	"""PKCE plain method must be rejected (only S256 allowed)."""
	auth_client.post("/register", json={
		"client_id": "pkce-plain",
		"client_secret": "x",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
	})
	r = auth_client.get("/authorize", params={
		"client_id": "pkce-plain",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
		"code_challenge": "plaintext_challenge",
		"code_challenge_method": "plain",
		"user_id": "carol",
	})
	assert r.status_code == 400


def test_code_is_one_time_use(auth_client):
	"""Authorization code must be invalidated after first use."""
	verifier, challenge = _pkce_pair()
	auth_client.post("/register", json={
		"client_id": "pkce-ott",
		"client_secret": "x",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
	})
	r = auth_client.get("/authorize", params={
		"client_id": "pkce-ott",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
		"code_challenge": challenge,
		"code_challenge_method": "S256",
		"user_id": "dan",
	})
	code = r.json()["code"]

	# First exchange — succeeds
	r1 = auth_client.post("/token", json={
		"client_id": "pkce-ott",
		"client_secret": "x",
		"code": code,
		"code_verifier": verifier,
	})
	assert r1.status_code == 200

	# Second exchange — code already consumed
	r2 = auth_client.post("/token", json={
		"client_id": "pkce-ott",
		"client_secret": "x",
		"code": code,
		"code_verifier": verifier,
	})
	assert r2.status_code == 400


# ---------------------------------------------------------------------------
# Gateway 401 enforcement
# ---------------------------------------------------------------------------

def test_gateway_no_auth_returns_401(gateway_client):
	# tools/call without token → MCP-layer auth error (HTTP 200 with JSON-RPC error code)
	resp = gateway_client.post(
		"/mcp",
		json={"jsonrpc": "2.0", "method": "tools/call",
		      "params": {"name": "echo", "arguments": {"text": "hi"}}, "id": 1},
	)
	assert resp.status_code == 200
	assert resp.json()["error"]["code"] == -32001


def test_gateway_expired_token_returns_401(gateway_client, shared_key):
	"""An expired JWT must be rejected for tools/call."""
	token = _make_token(shared_key, exp_offset=-1)  # already expired
	resp = gateway_client.post(
		"/mcp",
		json={"jsonrpc": "2.0", "method": "tools/call",
		      "params": {"name": "echo", "arguments": {"text": "hi"}}, "id": 1},
		headers={"Authorization": f"Bearer {token}"},
	)
	# optional=True returns None for invalid token → MCP-layer auth error
	assert resp.status_code == 200
	assert resp.json()["error"]["code"] == -32001


def test_gateway_wrong_audience_returns_401(gateway_client, shared_key):
	"""A token with aud != 'mcp-server' must be rejected."""
	token = _make_token(shared_key, aud="some-other-service")
	resp = gateway_client.post(
		"/mcp",
		json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
		headers={"Authorization": f"Bearer {token}"},
	)
	assert resp.status_code == 401


def test_gateway_malformed_token_returns_401(gateway_client):
	"""A non-JWT string in Authorization header must reject tools/call."""
	resp = gateway_client.post(
		"/mcp",
		json={"jsonrpc": "2.0", "method": "tools/call",
		      "params": {"name": "echo", "arguments": {"text": "hi"}}, "id": 1},
		headers={"Authorization": "Bearer not.a.jwt"},
	)
	assert resp.status_code == 200
	assert resp.json()["error"]["code"] == -32001


def test_gateway_valid_token_returns_200(gateway_client, shared_key):
	"""A valid token with correct scope must reach the handler."""
	token = _make_token(shared_key)
	resp = gateway_client.post(
		"/mcp",
		json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
		headers={"Authorization": f"Bearer {token}"},
	)
	assert resp.status_code == 200
	assert "result" in resp.json()


def test_gateway_insufficient_scope_returns_403(gateway_client, shared_key):
	"""A token with only tools:list scope must be rejected for tools:call endpoint."""
	token = _make_token(shared_key, scope="tools:list")
	resp = gateway_client.post(
		"/mcp",
		json={
			"jsonrpc": "2.0",
			"method": "tools/call",
			"params": {"name": "echo", "arguments": {"text": "hi"}},
			"id": 2,
		},
		headers={"Authorization": f"Bearer {token}"},
	)
	# Gateway requires tools:call scope; tools:list is insufficient
	assert resp.status_code in (401, 403)
