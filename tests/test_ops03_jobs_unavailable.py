"""
OPS-03 Component 6: async job endpoints return 503 when Redis is not configured.

The gateway enables async jobs only when REDIS_URL is set. Without it,
fleet._jobs_enabled is False and all /mcp/jobs/* routes return 503 within
2 seconds so the caller is never left hanging.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


@pytest.fixture()
def client_no_redis(monkeypatch):
    """Gateway with async jobs disabled (simulates cloud deploy without Redis)."""
    monkeypatch.setenv("MCP_DEV_MODE", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    monkeypatch.setenv("ASYNC_JOBS_ENABLED", "false")

    from mcp_agent_factory.gateway import fleet
    from mcp_agent_factory.gateway.app import gateway_app, set_sampling_client
    from mcp_agent_factory.gateway.sampling import StubSamplingClient
    from mcp_agent_factory.streams.eventlog import InProcessEventLog
    import mcp_agent_factory.gateway.app as _app_module

    set_sampling_client(StubSamplingClient())
    # Replace _event_log in case a KafkaEventLog was already created on a prior import
    _app_module._event_log = InProcessEventLog()

    with TestClient(gateway_app, raise_server_exceptions=False) as c:
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


@pytest.fixture()
def client_jobs_disabled_via_env(monkeypatch):
    """Gateway with ASYNC_JOBS_ENABLED=false (explicit env var, cloud demo path)."""
    monkeypatch.setenv("MCP_DEV_MODE", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    monkeypatch.setenv("ASYNC_JOBS_ENABLED", "false")

    # Force reload of fleet module so the env var is picked up at import time
    import importlib

    from mcp_agent_factory.gateway import app as gateway_app_module
    from mcp_agent_factory.gateway import fleet

    fleet._jobs_enabled = False

    from mcp_agent_factory.gateway.app import gateway_app, set_sampling_client
    from mcp_agent_factory.gateway.sampling import StubSamplingClient

    set_sampling_client(StubSamplingClient())

    with TestClient(gateway_app, raise_server_exceptions=False) as c:
        yield c


def test_submit_job_503_via_env_var(client_jobs_disabled_via_env):
    """ASYNC_JOBS_ENABLED=false disables async endpoints regardless of Redis."""
    resp = client_jobs_disabled_via_env.post(
        "/mcp/jobs", json={"method": "echo", "params": {}}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "async_jobs_unavailable"
