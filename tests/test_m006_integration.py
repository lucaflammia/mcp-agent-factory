"""End-to-end integration test for M006: all streams components wired together."""
import asyncio

import fakeredis
import pytest

from mcp_agent_factory.agents.models import AgentTask
from mcp_agent_factory.streams import (
	CircuitBreaker,
	DistributedLock,
	IdempotencyGuard,
	InProcessEventLog,
	OutboxRelay,
	StreamWorker,
)
from mcp_agent_factory.streams.circuit_breaker import State


STREAM = "tasks.integration"
GROUP = "workers"
CONSUMER = "worker-0"


def test_m006_full_pipeline():
	"""Wire StreamWorker → IdempotencyGuard → DistributedLock → CircuitBreaker
	→ OutboxRelay → InProcessEventLog in a single scenario."""
	r = fakeredis.FakeRedis()

	worker = StreamWorker(r, STREAM, GROUP, CONSUMER)
	worker.ensure_group()

	guard = IdempotencyGuard(r, ttl=60)
	lock = DistributedLock(r, ttl=10)
	cb = CircuitBreaker(threshold=3)
	relay = OutboxRelay()
	log = InProcessEventLog()

	task = AgentTask(name="search", payload={"query": "climate"}, required_capability="search")
	task_id = task.id

	# Publish a task
	msg_id = worker.publish(task)
	assert msg_id

	# Claim it
	result = worker.claim_one()
	assert result is not None
	claimed_id, fields = result

	# Pre-check: not yet seen
	assert guard.already_seen(task_id) is False

	# Acquire distributed lock (use a lock-namespaced key)
	lock_key = f"lock:{task_id}"
	assert lock.acquire(lock_key) is True
	assert lock.acquire(lock_key) is False  # second attempt fails

	# Execute via circuit breaker
	executed = []
	cb_result = cb.call(lambda: executed.append("done") or "result-value")
	assert cb_result == "result-value"
	assert cb.state == State.CLOSED
	assert executed == ["done"]

	# Append to event log
	asyncio.run(log.append(f"tasks.{task_id}", {"event": "completed", "task_id": task_id}))
	events = asyncio.run(log.read(f"tasks.{task_id}", offset=0))
	assert len(events) == 1
	assert events[0][1]["event"] == "completed"

	# Cache result and outbox relay
	guard.cache_result(task_id, cb_result)

	state_called = []
	dispatch_called = []
	relay.add(lambda: state_called.append(1), lambda: dispatch_called.append(1))
	relay.flush()
	assert state_called == [1]
	assert dispatch_called == [1]

	# ACK the message
	worker.ack(claimed_id)
	pending = r.xpending_range(STREAM, GROUP, "-", "+", count=10)
	assert pending == []

	# Post-check: now seen (key set by already_seen call above)
	assert guard.already_seen(task_id) is True

	# Cached result retrievable
	assert guard.get_cached(task_id) == "result-value"

	# Release lock
	lock.release(lock_key)
	assert r.get(lock_key) is None
