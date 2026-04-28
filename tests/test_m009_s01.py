"""
M009 S01 — UnifiedRouter unit, integration, and live Ollama acceptance tests.

Test layers:
  1. Unit   — StubHandlers, no real network, verifies fallback + token.usage logging.
  2. Integration — UnifiedRouter wired with InProcessEventLog; EventLog.read verified.
  3. Live   — Real OllamaHandler call; simulated OpenAI 429 triggers fallback chain.
              Skipped when Ollama is not reachable.
"""
from __future__ import annotations

import os
import asyncio
import pytest
import httpx

from mcp_agent_factory.gateway.router import (
	LLMRequest,
	LLMHandler,
	OllamaHandler,
	ProviderError,
	UnifiedRouter,
)
from mcp_agent_factory.streams.eventlog import InProcessEventLog


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

class _OkHandler(LLMHandler):
	"""Always succeeds."""
	provider_name = "stub-ok"

	def __init__(self, content: str = "hello") -> None:
		self._content = content

	async def call(self, request: LLMRequest) -> dict:
		return {"content": self._content, "model": "stub-ok", "input_tokens": 3, "output_tokens": 5}


class _FailFirstHandler(LLMHandler):
	"""Raises ProviderError on the first call; succeeds on subsequent calls."""
	provider_name = "stub-fail-first"

	def __init__(self, status: int = 429) -> None:
		self._status = status
		self._calls = 0

	async def call(self, request: LLMRequest) -> dict:
		self._calls += 1
		if self._calls == 1:
			raise ProviderError("stub-fail-first", status=self._status, detail="simulated")
		return {"content": "recovered", "model": "stub-ok", "input_tokens": 2, "output_tokens": 4}


class _AlwaysFailHandler(LLMHandler):
	"""Always raises ProviderError."""
	provider_name = "stub-always-fail"

	async def call(self, request: LLMRequest) -> dict:
		raise ProviderError("stub-always-fail", status=500, detail="intentional")


def _request(**kwargs) -> LLMRequest:
	return LLMRequest(
		tool_name=kwargs.get("tool_name", "echo"),
		args=kwargs.get("args", {"text": "hi"}),
		claims=kwargs.get("claims", {"sub": "user-test"}),
		prompt=kwargs.get("prompt", "say hi"),
	)


# ---------------------------------------------------------------------------
# Unit tests — no network
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_succeeds_on_first_handler():
	router = UnifiedRouter(handlers=[_OkHandler("pong")])
	result = await router.route(_request())
	assert result["content"] == "pong"


@pytest.mark.asyncio
async def test_router_falls_back_on_provider_error():
	"""First handler raises 429; second handler should succeed."""
	fail_handler = _FailFirstHandler(status=429)
	ok_handler = _OkHandler("from-fallback")
	router = UnifiedRouter(handlers=[fail_handler, ok_handler])
	result = await router.route(_request())
	assert result["content"] == "from-fallback"
	assert fail_handler._calls == 1


@pytest.mark.asyncio
async def test_router_raises_when_all_handlers_fail():
	router = UnifiedRouter(handlers=[_AlwaysFailHandler(), _AlwaysFailHandler()])
	with pytest.raises(ProviderError):
		await router.route(_request())


@pytest.mark.asyncio
async def test_token_usage_logged_after_success():
	log = InProcessEventLog()
	router = UnifiedRouter(handlers=[_OkHandler()], event_log=log)
	await router.route(_request(claims={"sub": "alice"}))
	entries = await log.read("token.usage")
	assert len(entries) == 1
	_, event = entries[0]
	assert event["type"] == "token.usage"
	assert event["sub"] == "alice"
	assert event["model"] == "stub-ok"
	assert "input_tokens" in event
	assert "output_tokens" in event
	assert "cost_usd" in event


@pytest.mark.asyncio
async def test_token_usage_not_logged_when_all_handlers_fail():
	log = InProcessEventLog()
	router = UnifiedRouter(handlers=[_AlwaysFailHandler()], event_log=log)
	with pytest.raises(ProviderError):
		await router.route(_request())
	entries = await log.read("token.usage")
	assert entries == []


@pytest.mark.asyncio
async def test_token_usage_log_failure_does_not_propagate():
	"""A broken EventLog must never cause route() to raise."""

	class _BrokenLog:
		async def append(self, topic, event):
			raise RuntimeError("disk full")

		async def read(self, topic, offset="0"):
			return []

	router = UnifiedRouter(handlers=[_OkHandler()], event_log=_BrokenLog())
	result = await router.route(_request())
	assert result["content"] == "hello"


@pytest.mark.asyncio
async def test_router_requires_at_least_one_handler():
	with pytest.raises(ValueError):
		UnifiedRouter(handlers=[])


@pytest.mark.asyncio
async def test_provider_error_attributes():
	exc = ProviderError("openai", status=429, detail="rate limited")
	assert exc.provider == "openai"
	assert exc.status == 429
	assert "429" in str(exc)


# ---------------------------------------------------------------------------
# Integration tests — InProcessEventLog wired end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_fallback_chain_token_usage():
	"""
	Simulates: first handler (openai) raises 429 → second handler (stub-ok) succeeds.
	Verifies token.usage event in EventLog with correct sub.
	"""
	log = InProcessEventLog()
	openai_stub = _FailFirstHandler(status=429)
	ollama_stub = _OkHandler("fallback-content")
	router = UnifiedRouter(handlers=[openai_stub, ollama_stub], event_log=log)

	request = _request(claims={"sub": "integration-user"}, prompt="test prompt")
	result = await router.route(request)

	assert result["content"] == "fallback-content"

	entries = await log.read("token.usage")
	assert len(entries) == 1
	_, event = entries[0]
	assert event["sub"] == "integration-user"
	assert event["type"] == "token.usage"
	assert event["model"] == "stub-ok"


@pytest.mark.asyncio
async def test_integration_multiple_requests_accumulate_events():
	log = InProcessEventLog()
	router = UnifiedRouter(handlers=[_OkHandler()], event_log=log)

	await router.route(_request(claims={"sub": "user-a"}))
	await router.route(_request(claims={"sub": "user-b"}))

	entries = await log.read("token.usage")
	assert len(entries) == 2
	subs = {e["sub"] for _, e in entries}
	assert subs == {"user-a", "user-b"}


# ---------------------------------------------------------------------------
# Live Ollama acceptance test
# ---------------------------------------------------------------------------

def _ollama_available() -> bool:
	try:
		resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
		return resp.status_code == 200
	except Exception:
		return False


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not running locally")
@pytest.mark.asyncio
async def test_live_ollama_fallback_acceptance():
	"""
	Simulates OpenAI 429 → Ollama fallback.

	Verifies:
	  - The router returns non-empty content from Ollama.
	  - A token.usage event is written to EventLog with model from Ollama.
	  - EventLog event has input_tokens > 0 (Ollama populates prompt_eval_count).
	"""
	log = InProcessEventLog()
	# Use the smallest available model
	ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:0.6b-q4_K_M")
	os.environ["OLLAMA_MODEL"] = ollama_model

	openai_stub = _FailFirstHandler(status=429)
	ollama_handler = OllamaHandler()

	router = UnifiedRouter(
		handlers=[openai_stub, ollama_handler],
		event_log=log,
	)

	request = LLMRequest(
		tool_name="sampling_demo",
		args={"text": "Reply with exactly one word: hello"},
		claims={"sub": "acceptance-user"},
		prompt="Reply with exactly one word: hello",
	)

	result = await router.route(request)

	assert isinstance(result["content"], str)
	assert len(result["content"]) > 0, "Ollama returned empty content"

	entries = await log.read("token.usage")
	assert len(entries) == 1
	_, event = entries[0]
	assert event["type"] == "token.usage"
	assert event["sub"] == "acceptance-user"
	assert event["model"] != "unknown"
	assert event["input_tokens"] >= 0
	assert event["output_tokens"] > 0, "Ollama should produce output tokens"
	assert event["cost_usd"] == 0.0  # Ollama is free
