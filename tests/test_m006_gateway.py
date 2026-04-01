"""Tests for M006 S03 — ValidationGate + InternalServiceLayer."""
import pytest
from fastapi.testclient import TestClient

import mcp_agent_factory.gateway.app as _app_module
from mcp_agent_factory.gateway.app import gateway_app
from mcp_agent_factory.server_http import TOOLS


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """Patch DEV_MODE=True so no JWT token is required in these tests."""
    monkeypatch.setattr(_app_module, "DEV_MODE", True)


client = TestClient(gateway_app)


def _call(payload: dict) -> dict:
    resp = client.post("/mcp", json=payload)
    assert resp.status_code == 200
    return resp.json()


def test_malformed_add_blocked():
    """Pydantic ValidationError for bad 'add' args → isError=True in result."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "add", "arguments": {"a": "not-a-number", "b": 2}},
    }
    body = _call(payload)
    result = body["result"]
    assert result.get("isError") is True
    assert len(result["content"]) > 0


def test_valid_add_dispatched():
    """Valid 'add' arguments → result content text == '7'."""
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "add", "arguments": {"a": 3, "b": 4}},
    }
    body = _call(payload)
    result = body["result"]
    assert result["content"][0]["text"] == "7"


def test_tools_list_not_empty():
    """Smoke: TOOLS registry is populated (existing gateway contract holds)."""
    assert len(TOOLS) > 0
