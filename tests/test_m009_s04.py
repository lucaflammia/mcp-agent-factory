"""S04: AsyncIdempotencyGuard — async prompt cache and token.usage tracking."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp_agent_factory.streams.async_idempotency import AsyncIdempotencyGuard, _prompt_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeRedis:
	"""Minimal in-memory async Redis stub (no fakeredis dependency)."""

	def __init__(self) -> None:
		self._store: dict[str, str] = {}
		self.write_error: Exception | None = None

	async def get(self, key: str) -> bytes | None:
		val = self._store.get(key)
		return val.encode() if val is not None else None

	async def set(self, key: str, value: str, ex: int | None = None) -> None:
		if self.write_error:
			raise self.write_error
		self._store[key] = value


# ---------------------------------------------------------------------------
# _prompt_hash
# ---------------------------------------------------------------------------

def test_prompt_hash_stable():
	h1 = _prompt_hash("echo", {"text": "hello"})
	h2 = _prompt_hash("echo", {"text": "hello"})
	assert h1 == h2


def test_prompt_hash_different_args():
	h1 = _prompt_hash("echo", {"text": "hello"})
	h2 = _prompt_hash("echo", {"text": "world"})
	assert h1 != h2


def test_prompt_hash_different_tools():
	h1 = _prompt_hash("echo", {"text": "hi"})
	h2 = _prompt_hash("add", {"text": "hi"})
	assert h1 != h2


def test_prompt_hash_arg_order_invariant():
	h1 = _prompt_hash("t", {"a": 1, "b": 2})
	h2 = _prompt_hash("t", {"b": 2, "a": 1})
	assert h1 == h2


# ---------------------------------------------------------------------------
# AsyncIdempotencyGuard — get / set
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_miss_returns_none():
	guard = AsyncIdempotencyGuard(FakeRedis())
	result = await guard.get("nonexistent")
	assert result is None


@pytest.mark.asyncio
async def test_cache_set_then_get():
	guard = AsyncIdempotencyGuard(FakeRedis())
	key = guard.cache_key("echo", {"text": "hi"})
	await guard.set(key, "hello back")
	result = await guard.get(key)
	assert result == "hello back"


@pytest.mark.asyncio
async def test_cache_hit_is_fast():
	"""Cache hit must complete well under 1ms (in-memory stub)."""
	redis = FakeRedis()
	guard = AsyncIdempotencyGuard(redis)
	key = guard.cache_key("sampling_demo", {"prompt": "what is 2+2?"})
	await guard.set(key, "4")

	t0 = time.perf_counter()
	result = await guard.get(key)
	elapsed_ms = (time.perf_counter() - t0) * 1000

	assert result == "4"
	assert elapsed_ms < 50  # generous ceiling for CI; real Redis < 1ms


@pytest.mark.asyncio
async def test_cache_write_failure_does_not_raise():
	"""Write failure is swallowed — caller must not see the exception."""
	redis = FakeRedis()
	redis.write_error = RuntimeError("Redis connection refused")
	guard = AsyncIdempotencyGuard(redis)
	# Must not raise
	await guard.set("some_key", "some_value")


@pytest.mark.asyncio
async def test_cache_read_failure_returns_none():
	"""If Redis.get raises, guard returns None (cache miss semantics)."""

	class BrokenRedis:
		async def get(self, key: str) -> None:
			raise ConnectionError("down")
		async def set(self, key: str, value: str, ex: int | None = None) -> None:
			pass

	guard = AsyncIdempotencyGuard(BrokenRedis())
	result = await guard.get("any_key")
	assert result is None


# ---------------------------------------------------------------------------
# InternalServiceLayer — prompt cache integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_layer_cache_hit_skips_router():
	"""Second identical sampling_demo call returns from cache; router not called."""
	from mcp_agent_factory.gateway.service_layer import InternalServiceLayer
	from mcp_agent_factory.streams.eventlog import InProcessEventLog
	from unittest.mock import MagicMock, AsyncMock

	bus = MagicMock()
	bus.publish = MagicMock()
	session = MagicMock()
	sampling_handler = MagicMock()
	event_log = InProcessEventLog()

	router = MagicMock()
	router.route = AsyncMock(return_value={
		"content": "hello from LLM",
		"model": "test-model",
		"input_tokens": 5,
		"output_tokens": 3,
	})

	redis = FakeRedis()
	prompt_cache = AsyncIdempotencyGuard(redis)

	layer = InternalServiceLayer(
		bus=bus,
		session=session,
		sampling_handler=sampling_handler,
		vector_store=None,
		embedder=None,
		event_log=event_log,
		router=router,
		prompt_cache=prompt_cache,
	)

	args = {"prompt": "what is the capital of France?"}

	# First call — hits router
	result1 = await layer.handle("sampling_demo", args, claims=None)
	assert router.route.call_count == 1
	assert result1["content"][0]["text"] == "hello from LLM"

	# Second call with identical args — must hit cache, not router
	result2 = await layer.handle("sampling_demo", args, claims=None)
	assert router.route.call_count == 1  # not called again
	assert result2["content"][0]["text"] == "hello from LLM"


@pytest.mark.asyncio
async def test_token_usage_readable_per_sub():
	"""token.usage events written by UnifiedRouter are readable from EventLog."""
	from mcp_agent_factory.gateway.router import UnifiedRouter, LLMRequest, LLMHandler, ProviderError
	from mcp_agent_factory.streams.eventlog import InProcessEventLog

	class StubHandler(LLMHandler):
		@property
		def provider_name(self) -> str:
			return "stub"

		async def call(self, request: LLMRequest) -> dict[str, Any]:
			return {
				"content": "ok",
				"model": "stub-model",
				"input_tokens": 10,
				"output_tokens": 5,
			}

	event_log = InProcessEventLog()
	router = UnifiedRouter([StubHandler()], event_log=event_log)

	req = LLMRequest(
		tool_name="sampling_demo",
		args={"prompt": "hello"},
		claims={"sub": "user-42"},
	)
	await router.route(req)

	events = await event_log.read("token.usage")
	assert len(events) == 1
	_, ev = events[0]
	assert ev["type"] == "token.usage"
	assert ev["sub"] == "user-42"
	assert ev["model"] == "stub-model"
	assert ev["input_tokens"] == 10
	assert ev["output_tokens"] == 5
	assert isinstance(ev["cost_usd"], float)
