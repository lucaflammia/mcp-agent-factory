"""
Contract test for the agents/analyze JSON-RPC method.

Verifies:
- Happy path: correct response shape from DocumentAnalysisResult
- -32602: provider explicitly requested but API key is missing
- -32603: pipeline failure (analyze_document raises)
"""
from __future__ import annotations

import time

import pytest
from authlib.jose import OctKey, jwt
from fastapi.testclient import TestClient

from mcp_agent_factory.agents.analyst import DocumentAnalysisResult
from mcp_agent_factory.auth.resource import set_jwt_key as resource_set_key
from mcp_agent_factory.gateway.app import gateway_app


def _make_token(key: OctKey) -> str:
    now = int(time.time())
    claims = {"sub": "user1", "aud": "mcp-server", "scope": "tools:call", "iat": now, "exp": now + 3600}
    return jwt.encode({"alg": "HS256"}, claims, key).decode("ascii")


@pytest.fixture
def client(monkeypatch):
    import mcp_agent_factory.gateway.app as _app
    monkeypatch.setattr(_app, "DEV_MODE", True)
    return TestClient(gateway_app)


def _post(client: TestClient, method: str, params: dict) -> dict:
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    assert resp.status_code == 200
    return resp.json()


def test_agents_analyze_happy_path(client, monkeypatch):
    """agents/analyze returns a result with all DocumentAnalysisResult fields."""
    stub = DocumentAnalysisResult(
        summary="Q3 revenue up 12%.",
        provider="stub",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
        pages_read=3,
        total_pages=10,
        chunks_before_pruning=5,
        chunks_after_pruning=3,
    )

    async def _stub_analyze(self, task, ctx=None):
        return stub

    from mcp_agent_factory.agents import analyst as _analyst_mod
    monkeypatch.setattr(_analyst_mod.AnalystAgent, "analyze_document", _stub_analyze)

    body = _post(client, "agents/analyze", {"pdf_path": "/data/samples/report.pdf", "query": "KPIs"})

    assert "result" in body, f"Expected result, got: {body}"
    result = body["result"]
    assert result["summary"] == "Q3 revenue up 12%."
    assert result["provider"] == "stub"
    assert isinstance(result["input_tokens"], int)
    assert isinstance(result["output_tokens"], int)
    assert "cost_usd" in result
    assert "pages_read" in result
    assert "chunks_before_pruning" in result
    assert "chunks_after_pruning" in result


def test_agents_analyze_missing_provider_key(monkeypatch):
    """agents/analyze returns -32602 when LLM_PROVIDER is set but its API key is absent (non-dev mode)."""
    import mcp_agent_factory.gateway.app as _app
    monkeypatch.setattr(_app, "DEV_MODE", False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    key = OctKey.generate_key(256, is_private=True)
    resource_set_key(key)
    token = _make_token(key)
    client = TestClient(gateway_app, headers={"Authorization": f"Bearer {token}"})

    body = _post(client, "agents/analyze", {"pdf_path": "/data/samples/report.pdf"})

    assert "error" in body, f"Expected error, got: {body}"
    assert body["error"]["code"] == -32602
    assert "OPENAI_API_KEY" in body["error"]["message"]
    assert "openai" in body["error"]["message"]


def test_agents_analyze_pipeline_failure(client, monkeypatch):
    """agents/analyze returns -32603 when the analysis pipeline raises an exception."""
    async def _raise(self, task, ctx=None):
        raise RuntimeError("PDF not found")

    from mcp_agent_factory.agents import analyst as _analyst_mod
    monkeypatch.setattr(_analyst_mod.AnalystAgent, "analyze_document", _raise)

    body = _post(client, "agents/analyze", {"pdf_path": "/nonexistent.pdf"})

    assert "error" in body, f"Expected error, got: {body}"
    assert body["error"]["code"] == -32603
    assert "PDF not found" in body["error"]["message"]
