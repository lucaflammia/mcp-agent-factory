"""
Tests for OAuth 2.1 Auth Server, Resource Server middleware, and session module.
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
	get_jwt_key,
	set_jwt_key as auth_set_key,
)
from mcp_agent_factory.auth.resource import set_jwt_key as resource_set_key
from mcp_agent_factory.auth.session import (
	generate_session_id,
	parse_session_id,
	validate_session_id,
)
from mcp_agent_factory.server_http_secured import secured_app


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
# Shared key fixture — inject into both auth server and resource server
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def shared_key():
	"""Generate a fresh key per test and inject into both server modules."""
	key = OctKey.generate_key(256, is_private=True)
	auth_set_key(key)
	resource_set_key(key)
	# Fresh FakeRedis per test isolates all auth state
	fresh_redis = _fakeredis_mod.FakeRedis(decode_responses=True)
	_set_auth_redis(fresh_redis)
	yield key
	_set_auth_redis(_fakeredis_mod.FakeRedis(decode_responses=True))


@pytest.fixture
def auth_client(shared_key):
	client = TestClient(auth_app)
	# Register a default test client
	client.post("/register", json={
		"client_id": "test-client",
		"client_secret": "test-secret",
		"redirect_uri": "http://localhost/callback",
		"scope": "tools:call",
	})
	return client


@pytest.fixture
def secured_client(shared_key):
	return TestClient(secured_app)


# ---------------------------------------------------------------------------
# Auth Server tests
# ---------------------------------------------------------------------------

class TestClientRegistration:
	def test_register_client(self, auth_client):
		resp = auth_client.post("/register", json={
			"client_id": "new-client",
			"client_secret": "secret",
			"redirect_uri": "http://example.com/cb",
			"scope": "tools:list",
		})
		assert resp.status_code == 200
		body = resp.json()
		assert body["client_id"] == "new-client"
		assert body["registered"] is True


class TestAuthorize:
	def test_authorize_returns_code(self, auth_client):
		verifier, challenge = _pkce_pair()
		resp = auth_client.get("/authorize", params={
			"client_id": "test-client",
			"code_challenge": challenge,
			"code_challenge_method": "S256",
			"scope": "tools:call",
			"user_id": "user1",
		})
		assert resp.status_code == 200
		body = resp.json()
		assert "code" in body
		assert len(body["code"]) > 10

	def test_authorize_rejects_plain_method(self, auth_client):
		resp = auth_client.get("/authorize", params={
			"client_id": "test-client",
			"code_challenge": "somechallenge",
			"code_challenge_method": "plain",
			"scope": "tools:call",
		})
		assert resp.status_code == 400
		assert "S256" in resp.json()["detail"]

	def test_authorize_rejects_unknown_client(self, auth_client):
		verifier, challenge = _pkce_pair()
		resp = auth_client.get("/authorize", params={
			"client_id": "no-such-client",
			"code_challenge": challenge,
			"code_challenge_method": "S256",
		})
		assert resp.status_code == 400


class TestTokenExchange:
	def _get_code(self, auth_client) -> tuple[str, str]:
		verifier, challenge = _pkce_pair()
		resp = auth_client.get("/authorize", params={
			"client_id": "test-client",
			"code_challenge": challenge,
			"code_challenge_method": "S256",
			"scope": "tools:call",
			"user_id": "user1",
		})
		code = resp.json()["code"]
		return code, verifier

	def test_token_exchange_returns_access_token(self, auth_client):
		code, verifier = self._get_code(auth_client)
		resp = auth_client.post("/token", json={
			"code": code,
			"code_verifier": verifier,
			"client_id": "test-client",
			"client_secret": "test-secret",
			"grant_type": "authorization_code",
		})
		assert resp.status_code == 200
		body = resp.json()
		assert "access_token" in body
		assert body["token_type"] == "bearer"
		assert body["expires_in"] == 3600

	def test_token_exchange_wrong_verifier_rejected(self, auth_client):
		code, _ = self._get_code(auth_client)
		resp = auth_client.post("/token", json={
			"code": code,
			"code_verifier": "wrong-verifier-value",
			"client_id": "test-client",
			"client_secret": "test-secret",
			"grant_type": "authorization_code",
		})
		assert resp.status_code == 400
		assert "PKCE" in resp.json()["detail"]

	def test_token_code_one_time_use(self, auth_client):
		code, verifier = self._get_code(auth_client)
		# First exchange succeeds
		resp1 = auth_client.post("/token", json={
			"code": code,
			"code_verifier": verifier,
			"client_id": "test-client",
			"client_secret": "test-secret",
			"grant_type": "authorization_code",
		})
		assert resp1.status_code == 200
		# Second exchange with same code fails
		resp2 = auth_client.post("/token", json={
			"code": code,
			"code_verifier": verifier,
			"client_id": "test-client",
			"client_secret": "test-secret",
			"grant_type": "authorization_code",
		})
		assert resp2.status_code == 400

	def test_jwt_contains_correct_claims(self, auth_client, shared_key):
		code, verifier = self._get_code(auth_client)
		resp = auth_client.post("/token", json={
			"code": code,
			"code_verifier": verifier,
			"client_id": "test-client",
			"client_secret": "test-secret",
			"grant_type": "authorization_code",
		})
		assert resp.status_code == 200
		token = resp.json()["access_token"]
		claims = jwt.decode(token.encode(), shared_key)
		assert claims["sub"] == "user1"
		assert claims["aud"] == "mcp-server"
		assert "tools:call" in claims["scope"]
		assert "session_id" in claims
		assert claims["session_id"].startswith("user1:")


# ---------------------------------------------------------------------------
# Resource Server tests
# ---------------------------------------------------------------------------

class TestResourceServer:
	def test_protected_endpoint_no_token_returns_401(self, secured_client):
		resp = secured_client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 1,
			"method": "tools/list",
			"params": {},
		})
		assert resp.status_code == 401

	def test_protected_endpoint_valid_token_accepted(self, secured_client, shared_key):
		token = _make_token(shared_key, scope="tools:call")
		resp = secured_client.post(
			"/mcp",
			json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
			headers={"Authorization": f"Bearer {token}"},
		)
		assert resp.status_code == 200
		assert "tools" in resp.json()["result"]

	def test_confused_deputy_wrong_aud_rejected(self, secured_client, shared_key):
		token = _make_token(shared_key, aud="other-service")
		resp = secured_client.post(
			"/mcp",
			json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
			headers={"Authorization": f"Bearer {token}"},
		)
		assert resp.status_code == 401
		assert "audience" in resp.json()["detail"].lower()

	def test_wrong_scope_rejected(self, secured_client, shared_key):
		# token only has tools:list — tools:call is required by /mcp
		token = _make_token(shared_key, scope="tools:list")
		resp = secured_client.post(
			"/mcp",
			json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
				  "params": {"name": "echo", "arguments": {"message": "hi"}}},
			headers={"Authorization": f"Bearer {token}"},
		)
		assert resp.status_code == 403

	def test_health_endpoint_unauthenticated(self, secured_client):
		resp = secured_client.get("/health")
		assert resp.status_code == 200

	def test_malformed_bearer_returns_401(self, secured_client):
		resp = secured_client.post(
			"/mcp",
			json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
			headers={"Authorization": "NotBearer token"},
		)
		assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Session module tests
# ---------------------------------------------------------------------------

class TestSessionModule:
	def test_session_id_format(self):
		sid = generate_session_id("user1")
		assert sid.startswith("user1:")
		parts = sid.split(":", 1)
		assert len(parts) == 2
		assert len(parts[1]) > 10

	def test_parse_session_id(self):
		sid = generate_session_id("alice")
		user_id, token_part = parse_session_id(sid)
		assert user_id == "alice"
		assert len(token_part) > 10

	def test_validate_session_id_valid(self):
		sid = generate_session_id("bob")
		assert validate_session_id(sid) is True

	def test_validate_session_id_invalid(self):
		assert validate_session_id("nocolon") is False
		assert validate_session_id(":nouser") is False
		assert validate_session_id("notoken:") is False

	def test_session_ids_are_unique(self):
		ids = {generate_session_id("user1") for _ in range(10)}
		assert len(ids) == 10  # all unique

	def test_user_id_with_colon_rejected(self):
		with pytest.raises(ValueError):
			generate_session_id("user:bad")


# ---------------------------------------------------------------------------
# Redis fallback tests
# ---------------------------------------------------------------------------

class TestRedisFallback:
	def test_make_auth_redis_falls_back_to_fakeredis_on_connection_error(
		self, monkeypatch
	):
		"""_make_auth_redis() must return a FakeRedis when the configured Redis
		host is unreachable, so the auth server stays operational."""
		import fakeredis as _fr
		import redis as _redis
		import mcp_agent_factory.auth.server as auth_server_mod

		monkeypatch.setenv("AUTH_REDIS_URL", "redis://127.0.0.1:19999")  # nothing there

		client = auth_server_mod._make_auth_redis()
		# Must be usable (FakeRedis or connected Redis — either is fine as long
		# as basic set/get works without raising).
		client.set("probe", "ok")
		assert client.get("probe") == "ok"

	def test_register_succeeds_without_redis(self, monkeypatch):
		"""POST /register must return 200 even when AUTH_REDIS_URL points at an
		unreachable host (regression for ConnectionError 111 crash)."""
		import fakeredis as _fr
		import mcp_agent_factory.auth.server as auth_server_mod

		# Inject a fresh FakeRedis so the test is isolated
		monkeypatch.setattr(
			auth_server_mod, "_auth_redis", _fr.FakeRedis(decode_responses=True)
		)

		client = TestClient(auth_server_mod.auth_app)
		resp = client.post("/register", json={
			"client_id": "fallback-client",
			"client_secret": "s3cr3t",
			"redirect_uri": "http://localhost",
			"scope": "tools:call",
		})
		assert resp.status_code == 200
		assert resp.json()["registered"] is True
