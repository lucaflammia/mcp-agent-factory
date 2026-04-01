"""Tests for idempotency and circuit breaker (R008–R014)."""
import time

import fakeredis
import pytest

from mcp_agent_factory.streams import (
	CircuitBreaker,
	DistributedLock,
	IdempotencyGuard,
	OutboxRelay,
)
from mcp_agent_factory.streams.circuit_breaker import State


# ---------------------------------------------------------------------------
# R008 — pre-check idempotency
# ---------------------------------------------------------------------------

def test_r008_idempotency_precheck():
	r = fakeredis.FakeRedis()
	guard = IdempotencyGuard(r, ttl=60)
	assert guard.already_seen("task-1") is False  # first time
	assert guard.already_seen("task-1") is True   # already set


# ---------------------------------------------------------------------------
# R009 — distributed lock acquire / second acquire fails
# ---------------------------------------------------------------------------

def test_r009_distributed_lock_acquire():
	r = fakeredis.FakeRedis()
	lock = DistributedLock(r, ttl=10)
	assert lock.acquire("lock:task-1") is True
	assert lock.acquire("lock:task-1") is False  # key still held


# ---------------------------------------------------------------------------
# R014 — result cache hit
# ---------------------------------------------------------------------------

def test_r014_result_cache_hit():
	r = fakeredis.FakeRedis()
	guard = IdempotencyGuard(r, ttl=60)
	guard.cache_result("task-2", "the answer")
	assert guard.get_cached("task-2") == "the answer"
	assert guard.get_cached("task-missing") is None


# ---------------------------------------------------------------------------
# R010 — transactional outbox relay
# ---------------------------------------------------------------------------

def test_r010_outbox_relay():
	relay = OutboxRelay()
	call_order: list[str] = []

	relay.add(lambda: call_order.append("state"), lambda: call_order.append("dispatch"))
	relay.flush()

	assert call_order == ["state", "dispatch"]
	# queue cleared — second flush is a no-op
	relay.flush()
	assert call_order == ["state", "dispatch"]


# ---------------------------------------------------------------------------
# R011 — circuit opens after N failures
# ---------------------------------------------------------------------------

def test_r011_circuit_opens_after_n_failures():
	cb = CircuitBreaker(threshold=3, recovery_timeout=60.0)

	def bad():
		raise ValueError("boom")

	for _ in range(3):
		with pytest.raises(ValueError):
			cb.call(bad)

	assert cb.state == State.OPEN


# ---------------------------------------------------------------------------
# R013 — fallback returned when circuit is open
# ---------------------------------------------------------------------------

def test_r013_fallback_on_open_circuit():
	cb = CircuitBreaker(threshold=1, recovery_timeout=60.0)

	def bad():
		raise RuntimeError("llm down")

	with pytest.raises(RuntimeError):
		cb.call(bad)

	assert cb.state == State.OPEN

	called = []
	result = cb.call(lambda: called.append(1), fallback="[Internal Knowledge]")
	assert result == "[Internal Knowledge]"
	assert called == []  # fn was never called


# ---------------------------------------------------------------------------
# R012 — half-open probe succeeds → CLOSED
# ---------------------------------------------------------------------------

def test_r012_half_open_recovery():
	cb = CircuitBreaker(threshold=1, recovery_timeout=0.0)  # instant recovery

	def bad():
		raise RuntimeError("fail")

	with pytest.raises(RuntimeError):
		cb.call(bad)

	assert cb.state == State.OPEN

	# With recovery_timeout=0.0 the next call transitions to HALF_OPEN
	result = cb.call(lambda: "ok")
	assert result == "ok"
	assert cb.state == State.CLOSED
