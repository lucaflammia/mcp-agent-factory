"""
Tests for StreamWorker (M006/R001, R002).

Uses fakeredis — no external Redis process required.
"""
from __future__ import annotations

import time

import fakeredis
import pytest

from mcp_agent_factory.agents.models import AgentTask
from mcp_agent_factory.streams.worker import StreamWorker


@pytest.fixture()
def redis_client():
	"""In-process fakeredis client with streams support."""
	return fakeredis.FakeRedis(version=(7, 0, 0))


@pytest.fixture()
def worker(redis_client):
	w = StreamWorker(redis_client, stream="tasks", group="workers", consumer="c1")
	w.ensure_group()
	return w


# ---------------------------------------------------------------------------
# R001 — claim + ack
# ---------------------------------------------------------------------------

def test_worker_claim_and_ack(worker, redis_client):
	"""Publish a task, claim it, ACK it — PEL must be empty afterwards."""
	task = AgentTask(name="test-job", payload={"x": 1})
	worker.publish(task)

	result = worker.claim_one()
	assert result is not None
	msg_id, fields = result

	# Fields are bytes in fakeredis
	assert fields[b"task_name"] == b"test-job"
	assert fields[b"task_id"] == task.id.encode()

	worker.ack(msg_id)

	pending = redis_client.xpending_range("tasks", "workers", min="-", max="+", count=10)
	assert pending == [], f"PEL should be empty after ACK, got {pending}"


# ---------------------------------------------------------------------------
# R002 — PEL crash recovery
# ---------------------------------------------------------------------------

def test_worker_pel_recovery(worker, redis_client):
	"""Claim without ACK — recover() must return the un-ACKed message."""
	task = AgentTask(name="crash-job", payload={"y": 2})
	worker.publish(task)

	# Claim but deliberately do NOT ack — simulates a crash
	result = worker.claim_one()
	assert result is not None
	msg_id, _ = result

	# Verify PEL is non-empty
	pending = redis_client.xpending_range("tasks", "workers", min="-", max="+", count=10)
	assert len(pending) == 1

	# Small sleep so idle-time is non-zero, then recover with 0 ms min_idle
	time.sleep(0.01)
	recovered = worker.recover(min_idle_ms=0, new_consumer="c2")

	assert len(recovered) == 1
	recovered_id, recovered_fields = recovered[0]
	assert recovered_fields[b"task_name"] == b"crash-job"


# ---------------------------------------------------------------------------
# Empty stream
# ---------------------------------------------------------------------------

def test_worker_no_messages(worker):
	"""claim_one on an empty stream returns None."""
	result = worker.claim_one()
	assert result is None
