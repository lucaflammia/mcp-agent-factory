"""
M009 S02 — PIIGate unit and integration tests.

Test layers:
  1. Unit   — PIIGate.scrub() with direct calls; all regex patterns exercised.
  2. Integration — InternalServiceLayer blocks PII; MCP_ALLOWED_FIELDS env var override.
  3. Gateway — POST /mcp tools/call with email in args returns isError response.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_agent_factory.gateway.validation import PIIGate, PIIViolation


# ---------------------------------------------------------------------------
# T01: PIIGate unit tests
# ---------------------------------------------------------------------------

class TestPIIGateEmail:
    def test_email_blocked(self):
        gate = PIIGate()
        with pytest.raises(PIIViolation, match="email"):
            gate.scrub({"email": "user@example.com"})

    def test_email_in_text_field_blocked(self):
        gate = PIIGate()
        with pytest.raises(PIIViolation):
            gate.scrub({"query": "contact me at alice@corp.io for details"})

    def test_clean_query_passes(self):
        gate = PIIGate()
        result = gate.scrub({"query": "what is the weather today"})
        assert result == {"query": "what is the weather today"}


class TestPIIGateApiKey:
    def test_openai_key_blocked(self):
        gate = PIIGate()
        with pytest.raises(PIIViolation):
            gate.scrub({"key": "sk-abc123DEF456ghi789JKL012mno345pqr"})

    def test_short_sk_prefix_not_blocked(self):
        # Too short to match (< 20 chars after sk-)
        gate = PIIGate()
        result = gate.scrub({"code": "sk-short"})
        assert "code" in result


class TestPIIGateJWT:
    def test_jwt_blocked(self):
        gate = PIIGate()
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIiwiaWF0IjoxNjE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        with pytest.raises(PIIViolation):
            gate.scrub({"token": jwt})


class TestPIIGatePrivateIP:
    @pytest.mark.parametrize("ip", [
        "10.0.0.1",
        "172.16.5.100",
        "172.31.255.255",
        "192.168.1.1",
    ])
    def test_private_ip_blocked(self, ip):
        gate = PIIGate()
        with pytest.raises(PIIViolation):
            gate.scrub({"target": ip})

    def test_public_ip_passes(self):
        gate = PIIGate()
        result = gate.scrub({"target": "8.8.8.8"})
        assert result["target"] == "8.8.8.8"


class TestPIIGateAllowList:
    def test_allow_list_bypasses_block(self):
        gate = PIIGate()
        # email field is explicitly allow-listed — should not raise
        result = gate.scrub(
            {"email": "user@example.com"},
            allow_list=frozenset({"email"}),
        )
        assert result["email"] == "user@example.com"

    def test_env_allow_list_bypasses_block(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_FIELDS", "contact_email,phone")
        gate = PIIGate()
        result = gate.scrub({"contact_email": "ops@internal.io"})
        assert result["contact_email"] == "ops@internal.io"

    def test_env_allow_list_does_not_bypass_other_fields(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_FIELDS", "contact_email")
        gate = PIIGate()
        with pytest.raises(PIIViolation):
            gate.scrub({"other_field": "user@example.com"})

    def test_empty_env_var_no_effect(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_FIELDS", "")
        gate = PIIGate()
        with pytest.raises(PIIViolation):
            gate.scrub({"email": "x@y.com"})


# ---------------------------------------------------------------------------
# T02: InternalServiceLayer integration — PIIGate wired in handle()
# ---------------------------------------------------------------------------

@pytest.fixture
def service_layer():
    from mcp_agent_factory.gateway.service_layer import InternalServiceLayer
    from mcp_agent_factory.messaging.bus import MessageBus

    bus = MagicMock(spec=MessageBus)
    bus.publish = MagicMock()
    session = MagicMock()
    sampling = MagicMock()
    vector_store = MagicMock()
    embedder = MagicMock()

    return InternalServiceLayer(
        bus=bus,
        session=session,
        sampling_handler=sampling,
        vector_store=vector_store,
        embedder=embedder,
        event_log=None,
        router=None,
    )


@pytest.mark.asyncio
async def test_service_layer_blocks_email(service_layer):
    with pytest.raises(Exception) as exc_info:
        await service_layer.handle("echo", {"text": "hello user@example.com"}, None)
    assert "sensitive" in str(exc_info.value).lower() or "pii" in str(exc_info.value).lower() or "allow" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_service_layer_passes_clean_echo(service_layer):
    result = await service_layer.handle("echo", {"text": "hello world"}, None)
    assert result["content"][0]["text"] == "hello world"


@pytest.mark.asyncio
async def test_service_layer_allowed_fields_bypass(service_layer, monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_FIELDS", "text")
    # With 'text' allow-listed, email in that field should pass through
    result = await service_layer.handle("echo", {"text": "user@example.com"}, None)
    assert "user@example.com" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# T03: Gateway-level integration via TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    import mcp_agent_factory.gateway.app as _app
    monkeypatch.setattr(_app, "DEV_MODE", True)
    from fastapi.testclient import TestClient
    return TestClient(_app.gateway_app)


def test_gateway_blocks_email_in_args(client):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "contact@example.com"}},
    }
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # Should return an isError result, not a successful echo
    assert body["result"]["isError"] is True


def test_gateway_passes_clean_echo(client):
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "hello world"}},
    }
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "isError" not in body.get("result", {})
    assert body["result"]["content"][0]["text"] == "hello world"


def test_gateway_allowed_fields_override(client, monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_FIELDS", "text")
    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "user@example.com"}},
    }
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "isError" not in body.get("result", {})
    assert body["result"]["content"][0]["text"] == "user@example.com"
