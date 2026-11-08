"""
OPS-03 Component 6: async job endpoints return 503 when Redis is not configured.

The gateway enables async jobs only when REDIS_URL is set. Without it,
fleet._jobs_enabled is False and all /mcp/jobs/* routes return 503 within
2 seconds so the caller is never left hanging.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client_no_redis(monkeypatch):
    """Gateway with async jobs disabled (simulates cloud deploy without Redis)."""
    monkeypatch.setenv("MCP_DEV_MODE", "1")

    from mcp_agent_factory.gateway import fleet
    from mcp_agent_factory.gateway.app import gateway_app, set_sampling_client
    from mcp_agent_factory.gateway.sampling import StubSamplingClient

    set_sampling_client(StubSamplingClient())

    with TestClient(gateway_app, raise_server_exceptions=False) as c:
        # Disable jobs after lifespan runs — simulates missing REDIS_URL in prod
        original = fleet._jobs_enabled
        fleet._jobs_enabled = False
        yield c
        fleet._jobs_enabled = original


def test_submit_job_503_without_redis(client_no_redis):
    resp = client_no_redis.post("/mcp/jobs", json={"method": "echo", "params": {}})
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"] == "async_jobs_unavailable"


def test_submit_batch_503_without_redis(client_no_redis):
    resp = client_no_redis.post(
        "/mcp/jobs/batch",
        json={"tasks": [{"method": "echo", "params": {}}]},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"] == "async_jobs_unavailable"


def test_get_job_503_without_redis(client_no_redis):
    resp = client_no_redis.get("/mcp/jobs/nonexistent-id")
    assert resp.status_code == 503


def test_get_batch_503_without_redis(client_no_redis):
    resp = client_no_redis.get("/mcp/jobs/batch/nonexistent-batch")
    assert resp.status_code == 503


def test_tools_call_unaffected_without_redis(client_no_redis):
    """Synchronous /mcp endpoint must still work when Redis is absent."""
    resp = client_no_redis.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 200
