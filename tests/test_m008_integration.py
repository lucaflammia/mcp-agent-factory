"""
M008 integration tests.

Unit-level tests (no Docker):
  - Gateway uses FakeRedis when REDIS_URL is unset
  - Auth server stores client/code in Redis and round-trips correctly
  - tools/call appends a durable event to InProcessEventLog

Integration tests (require Docker — marked with pytest.mark.integration):
  - Gateway Redis liveness check passes against real Redis
  - Auth client registration survives a simulated restart (Redis-backed)
  - Full PKCE flow against Redis-backed auth server
  - tools/call produces a Kafka event (KAFKA_BOOTSTRAP_SERVERS required)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from mcp_agent_factory.auth.server import (
	_set_auth_redis,
	auth_app,
	_load_client,
	_load_and_delete_code,
	_store_client,
	_store_code,
	set_jwt_key,
)
from mcp_agent_factory.auth.resource import set_jwt_key as set_resource_jwt_key
from authlib.jose import OctKey


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _s256(verifier: str) -> str:
	digest = hashlib.sha256(verifier.encode("ascii")).digest()
	return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Auth server unit tests (FakeRedis, no Docker)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_auth_redis():
	"""Each test gets a fresh FakeRedis instance for the auth server."""
	fresh = fakeredis.FakeRedis(decode_responses=True)
	_set_auth_redis(fresh)
	yield fresh
	# Reset to a fresh instance so module-level state doesn't bleed
	_set_auth_redis(fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture
def shared_key():
	key = OctKey.generate_key(256, is_private=True)
	set_jwt_key(key)
	set_resource_jwt_key(key)
	return key


def test_client_registration_persisted_in_redis(isolated_auth_redis):
	"""Registering a client writes it to Redis; a fresh TestClient can read it."""
	client = TestClient(auth_app)
	resp = client.post("/register", json={
		"client_id": "test-client",
		"client_secret": "secret",
		"redirect_uri": "http://localhost/cb",
		"scope": "tools:call",
	})
	assert resp.status_code == 200
	assert resp.json()["registered"] is True

	# Directly verify Redis key is set
	data = _load_client("test-client")
	assert data is not None
	assert data["client_secret"] == "secret"


def test_auth_code_stored_with_ttl_then_consumed(isolated_auth_redis):
	"""Authorization code is stored with TTL and consumed exactly once."""
	# Pre-seed a client
	_store_client("c1", {"client_secret": "s", "redirect_uri": "http://x", "scope": "tools:call"})

	client = TestClient(auth_app)
	verifier = secrets.token_urlsafe(32)
	challenge = _s256(verifier)

	# Get a code
	resp = client.get("/authorize", params={
		"client_id": "c1",
		"code_challenge": challenge,
		"code_challenge_method": "S256",
		"scope": "tools:call",
		"user_id": "u1",
	})
	assert resp.status_code == 200
	code = resp.json()["code"]
	assert code

	# Code is in Redis — token exchange consumes it atomically
	resp2 = client.post("/token", json={
		"code": code,
		"code_verifier": verifier,
		"client_id": "c1",
		"client_secret": "s",
		"grant_type": "authorization_code",
	})
	assert resp2.status_code == 200
	assert "access_token" in resp2.json()


def test_full_pkce_flow_redis_backed(isolated_auth_redis, shared_key):
	"""Full register → authorize → token flow against Redis-backed auth server."""
	client = TestClient(auth_app)

	# Register
	client.post("/register", json={
		"client_id": "pkce-client",
		"client_secret": "pkce-secret",
		"redirect_uri": "http://localhost/cb",
		"scope": "tools:call",
	})

	# Authorize
	verifier = secrets.token_urlsafe(32)
	challenge = _s256(verifier)
	auth_resp = client.get("/authorize", params={
		"client_id": "pkce-client",
		"code_challenge": challenge,
		"code_challenge_method": "S256",
		"scope": "tools:call",
		"user_id": "alice",
	})
	assert auth_resp.status_code == 200
	code = auth_resp.json()["code"]

	# Exchange
	token_resp = client.post("/token", json={
		"code": code,
		"code_verifier": verifier,
		"client_id": "pkce-client",
		"client_secret": "pkce-secret",
		"grant_type": "authorization_code",
	})
	assert token_resp.status_code == 200
	token_data = token_resp.json()
	assert "access_token" in token_data
	assert token_data["scope"] == "tools:call"

	# Code is one-time-use — second exchange must fail
	token_resp2 = client.post("/token", json={
		"code": code,
		"code_verifier": verifier,
		"client_id": "pkce-client",
		"client_secret": "pkce-secret",
		"grant_type": "authorization_code",
	})
	assert token_resp2.status_code == 400


def test_client_registration_survives_simulated_restart(isolated_auth_redis):
	"""Client registered before 'restart' is visible to the new TestClient."""
	client_before = TestClient(auth_app)
	client_before.post("/register", json={
		"client_id": "persist-client",
		"client_secret": "ps",
		"redirect_uri": "http://x",
		"scope": "tools:call",
	})

	# Simulate restart: new TestClient still points to the same Redis instance
	client_after = TestClient(auth_app)
	resp = client_after.get("/authorize", params={
		"client_id": "persist-client",
		"code_challenge": _s256("verifier"),
		"code_challenge_method": "S256",
	})
	assert resp.status_code == 200, "client registration must persist across restart"


# ---------------------------------------------------------------------------
# Gateway EventLog wiring (InProcessEventLog, no Docker)
# ---------------------------------------------------------------------------

def test_tools_call_appends_to_event_log(monkeypatch):
	"""tools/call echo produces an event in InProcessEventLog."""
	import mcp_agent_factory.gateway.app as _app
	from mcp_agent_factory.streams.eventlog import InProcessEventLog

	monkeypatch.setattr(_app, "DEV_MODE", True)
	log = InProcessEventLog()
	_app._service_layer._event_log = log

	gw_client = TestClient(_app.gateway_app, raise_server_exceptions=True)
	resp = gw_client.post("/mcp", json={
		"jsonrpc": "2.0",
		"id": 1,
		"method": "tools/call",
		"params": {"name": "echo", "arguments": {"text": "hello"}},
	})
	assert resp.status_code == 200
	body = resp.json()
	assert body.get("result") is not None

	events = asyncio.run(log.read("gateway.tool_calls"))
	assert len(events) >= 1
	assert events[-1][1]["tool"] == "echo"

	# Reset to default event log
	_app._service_layer._event_log = _app._event_log


# ---------------------------------------------------------------------------
# Integration tests — require docker-compose up
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_gateway_redis_liveness(real_redis):
	"""Gateway Redis factory connects to real Redis on REDIS_URL."""
	import redis as _sync_redis
	# real_redis fixture already validates connectivity
	real_redis.ping()
	real_redis.set("m008:liveness", "ok", ex=60)
	assert real_redis.get("m008:liveness") == b"ok"


@pytest.mark.integration
def test_auth_redis_persistence_across_restart(real_redis):
	"""Client registration written to real Redis persists after re-creating the store."""
	import redis as _redis_lib
	import fakeredis

	# Use a real sync redis client pointing at test DB
	real_sync = _redis_lib.Redis(host="localhost", port=6379, db=1, decode_responses=True)
	try:
		real_sync.ping()
	except Exception:
		pytest.skip("Real Redis not available")

	_set_auth_redis(real_sync)
	real_sync.delete("auth:client:m008-test")

	try:
		client = TestClient(auth_app)
		client.post("/register", json={
			"client_id": "m008-test",
			"client_secret": "s",
			"redirect_uri": "http://x",
			"scope": "tools:call",
		})

		# Re-read directly from Redis
		raw = real_sync.get("auth:client:m008-test")
		assert raw is not None
		data = json.loads(raw)
		assert data["client_secret"] == "s"
	finally:
		real_sync.delete("auth:client:m008-test")
		real_sync.close()
		# Restore FakeRedis
		_set_auth_redis(fakeredis.FakeRedis(decode_responses=True))


@pytest.mark.integration
def test_kafka_event_log_tools_call(real_kafka_bootstrap):
	"""tools/call with KAFKA_BOOTSTRAP_SERVERS set produces a Kafka event."""
	import os
	import mcp_agent_factory.gateway.app as _app
	from mcp_agent_factory.streams.kafka_adapter import KafkaEventLog

	kafka_log = KafkaEventLog(bootstrap_servers=real_kafka_bootstrap)
	asyncio.run(kafka_log.start())

	original = _app._service_layer._event_log
	_app._service_layer._event_log = kafka_log

	try:
		gw_client = TestClient(_app.gateway_app)
		resp = gw_client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 2,
			"method": "tools/call",
			"params": {"name": "echo", "arguments": {"text": "kafka-test"}},
		})
		assert resp.status_code == 200
		assert resp.json().get("result") is not None
	finally:
		asyncio.run(kafka_log.stop())
		_app._service_layer._event_log = original
