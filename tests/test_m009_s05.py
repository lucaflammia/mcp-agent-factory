"""
M009 S05 — TLS + Caddy + Live Ollama Integration acceptance tests.

Tests at two levels:
  1. Gateway integration — full stack via TestClient; simulated OpenAI 429 triggers
     OllamaHandler fallback; token.usage event readable from EventLog.
  2. Docker-compose smoke — optional; verifies https://localhost/health via Caddy
     when DOCKER_STACK_UP=1 is set (not run in standard CI).

The live Ollama tests are skipped when Ollama is not reachable.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from mcp_agent_factory.gateway.app import gateway_app
from mcp_agent_factory.gateway.router import (
    LLMHandler,
    LLMRequest,
    OllamaHandler,
    ProviderError,
    UnifiedRouter,
)
from mcp_agent_factory.streams.eventlog import InProcessEventLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ollama_available() -> bool:
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def _docker_stack_up() -> bool:
    return os.getenv("DOCKER_STACK_UP", "0") == "1"


class _AlwaysFailHandler(LLMHandler):
    """Simulates a provider responding with a given HTTP status code."""
    provider_name = "stub-fail"

    def __init__(self, status: int = 429) -> None:
        self._status = status

    async def call(self, request: LLMRequest) -> dict[str, Any]:
        raise ProviderError(self.provider_name, status=self._status, detail="simulated")


# ---------------------------------------------------------------------------
# Gateway health endpoint
# ---------------------------------------------------------------------------

def test_health_endpoint_returns_ok():
    """GET /health is publicly accessible and returns 200 with status ok."""
    with TestClient(gateway_app, raise_server_exceptions=False) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "mcp-gateway"


# ---------------------------------------------------------------------------
# UnifiedRouter fallback chain integration (no network required)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unified_router_openai_429_falls_back_to_stub():
    """
    Simulated OpenAI 429 → stub Ollama handler succeeds.
    Verifies fallback order and token.usage emission.
    """
    log = InProcessEventLog()

    class _StubOllama(LLMHandler):
        provider_name = "ollama-stub"

        async def call(self, request: LLMRequest) -> dict[str, Any]:
            return {
                "content": "pong",
                "model": "ollama-stub",
                "input_tokens": 4,
                "output_tokens": 2,
            }

    router = UnifiedRouter(
        handlers=[_AlwaysFailHandler(429), _StubOllama()],
        event_log=log,
    )
    result = await router.route(LLMRequest(
        tool_name="ping",
        args={"text": "ping"},
        claims={"sub": "test-user"},
        prompt="ping",
    ))

    assert result["content"] == "pong"
    assert result["model"] == "ollama-stub"

    entries = await log.read("token.usage")
    assert len(entries) == 1
    _, event = entries[0]
    assert event["type"] == "token.usage"
    assert event["sub"] == "test-user"
    assert event["model"] == "ollama-stub"
    assert event["input_tokens"] == 4
    assert event["output_tokens"] == 2


@pytest.mark.asyncio
async def test_unified_router_all_handlers_fail_raises():
    """If all handlers raise ProviderError, UnifiedRouter re-raises the last one."""
    router = UnifiedRouter(
        handlers=[_AlwaysFailHandler(429), _AlwaysFailHandler(503)],
    )
    with pytest.raises(ProviderError) as exc_info:
        await router.route(LLMRequest(tool_name="x", args={}, prompt="x"))
    assert exc_info.value.status == 503


# ---------------------------------------------------------------------------
# Live Ollama + gateway integration
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _ollama_available(), reason="Ollama not running locally")
@pytest.mark.asyncio
async def test_live_openai_429_to_ollama_fallback_with_eventlog():
    """
    Full fallback chain:
      1. OpenAI handler raises ProviderError(status=429)
      2. OllamaHandler calls real local Ollama
      3. token.usage event written to EventLog
      4. event has model != 'unknown', output_tokens > 0, cost_usd == 0.0
    """
    log = InProcessEventLog()
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:0.6b-q4_K_M")
    os.environ["OLLAMA_MODEL"] = ollama_model

    router = UnifiedRouter(
        handlers=[_AlwaysFailHandler(429), OllamaHandler()],
        event_log=log,
    )

    result = await router.route(LLMRequest(
        tool_name="sampling_demo",
        args={"text": "Reply with one word: yes"},
        claims={"sub": "s05-acceptance"},
        prompt="Reply with one word: yes",
    ))

    assert isinstance(result["content"], str)
    assert len(result["content"]) > 0

    entries = await log.read("token.usage")
    assert len(entries) == 1
    _, event = entries[0]
    assert event["type"] == "token.usage"
    assert event["sub"] == "s05-acceptance"
    assert event["model"] != "unknown"
    assert event["output_tokens"] > 0
    assert event["cost_usd"] == 0.0


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not running locally")
@pytest.mark.asyncio
async def test_live_multiple_sequential_calls_emit_separate_usage_events():
    """Each router.route() call appends a distinct token.usage event."""
    log = InProcessEventLog()
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:0.6b-q4_K_M")
    os.environ["OLLAMA_MODEL"] = ollama_model

    router = UnifiedRouter(handlers=[OllamaHandler()], event_log=log)

    for i in range(2):
        await router.route(LLMRequest(
            tool_name="echo",
            args={"text": f"call {i}"},
            claims={"sub": f"user-{i}"},
            prompt=f"call {i}",
        ))

    entries = await log.read("token.usage")
    assert len(entries) == 2
    subs = [e["sub"] for _, e in entries]
    assert "user-0" in subs
    assert "user-1" in subs


# ---------------------------------------------------------------------------
# Docker-compose / Caddy smoke test (optional, DOCKER_STACK_UP=1)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _docker_stack_up(),
    reason="Set DOCKER_STACK_UP=1 to run docker-compose stack verification",
)
def test_caddy_https_health():
    """
    Verifies that the full docker-compose stack is reachable at https://localhost.
    Caddy self-signed cert — verify=False is intentional for development.
    """
    resp = httpx.get("https://localhost/health", verify=False, timeout=10.0)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.skipif(
    not _docker_stack_up(),
    reason="Set DOCKER_STACK_UP=1 to run docker-compose stack verification",
)
def test_caddy_https_tools_list():
    """Tools list is accessible through the Caddy TLS proxy."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    resp = httpx.post(
        "https://localhost/mcp",
        json=payload,
        verify=False,
        timeout=10.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body
    assert "tools" in body["result"]
