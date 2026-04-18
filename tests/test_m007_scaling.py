"""
M007/S04 — Multi-instance StreamWorker integration tests (R016).

Proves that StreamWorker is truly stateless: two OS-level processes sharing
the same consumer group each claim distinct tasks with no double-execution.

Requires a live Redis on port 6379. Skip automatically when not available.
Start with: docker-compose up -d redis
"""
import multiprocessing
import time
import uuid

import pytest
import redis as redis_lib

from mcp_agent_factory.agents.models import AgentTask
from mcp_agent_factory.streams.worker import StreamWorker


# ---------------------------------------------------------------------------
# Worker subprocess function (must be module-level for multiprocessing pickling)
# ---------------------------------------------------------------------------

def _drain_worker(host: str, port: int, stream: str, group: str,
                  consumer: str, result_queue: multiprocessing.Queue,
                  timeout_s: float = 5.0) -> None:
	"""
	Claim all available tasks from the stream, ACK each, put task IDs in
	result_queue. Stops after timeout_s with no new messages.
	"""
	client = redis_lib.Redis(host=host, port=port, decode_responses=False)
	worker = StreamWorker(client, stream, group, consumer)
	worker.ensure_group()

	deadline = time.monotonic() + timeout_s
	while time.monotonic() < deadline:
		entry = worker.claim_one()
		if entry is None:
			time.sleep(0.05)
			continue
		msg_id, fields = entry
		task_id = fields[b"task_id"].decode() if isinstance(fields[b"task_id"], bytes) else fields[b"task_id"]
		result_queue.put(task_id)
		worker.ack(msg_id)
		deadline = time.monotonic() + timeout_s  # reset on activity


def _unique_stream(base: str) -> str:
	return f"{base}:{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_two_workers_no_double_execution(real_redis):
	"""
	10 tasks published; 2 worker processes share the consumer group.
	Combined claimed IDs == all 10; no task claimed by both workers.
	"""
	stream = _unique_stream("m007.tasks.scale")
	group = "workers"

	# Publish 10 tasks using one worker's publish helper
	publisher = StreamWorker(real_redis, stream, group, "publisher")
	publisher.ensure_group()

	all_ids = []
	for i in range(10):
		task = AgentTask(name=f"task-{i}", payload={"seq": i})
		publisher.publish(task)
		all_ids.append(task.id)

	# Spawn 2 worker processes
	result_q: multiprocessing.Queue = multiprocessing.Queue()
	host = real_redis.connection_pool.connection_kwargs["host"]
	port = real_redis.connection_pool.connection_kwargs["port"]

	p1 = multiprocessing.Process(
		target=_drain_worker,
		args=(host, port, stream, group, "worker-1", result_q, 3.0),
	)
	p2 = multiprocessing.Process(
		target=_drain_worker,
		args=(host, port, stream, group, "worker-2", result_q, 3.0),
	)
	p1.start()
	p2.start()
	p1.join(timeout=10)
	p2.join(timeout=10)

	# Collect results
	claimed: list[str] = []
	while not result_q.empty():
		claimed.append(result_q.get_nowait())

	claimed_set = set(claimed)
	all_set = set(all_ids)

	assert claimed_set == all_set, f"Missing tasks: {all_set - claimed_set}"
	assert len(claimed) == len(claimed_set), f"Duplicate tasks found: {len(claimed) - len(claimed_set)} duplicates"


@pytest.mark.integration
def test_pel_recovery_across_processes(real_redis):
	"""
	Worker A claims a task but exits without ACKing (simulates crash).
	After a brief delay, worker B recovers via recover() and ACKs.
	PEL is empty after recovery.
	"""
	stream = _unique_stream("m007.tasks.pelrecovery")
	group = "workers"

	# Publish 1 task
	worker_a = StreamWorker(real_redis, stream, group, "worker-a")
	worker_a.ensure_group()
	task = AgentTask(name="crash-task", payload={"critical": True})
	worker_a.publish(task)

	# Worker A claims but does NOT ack (simulate crash by just not calling ack)
	entry = worker_a.claim_one()
	assert entry is not None, "Worker A should claim the task"
	crashed_msg_id, crashed_fields = entry

	# Wait for the PEL entry to become "idle" enough for recovery
	time.sleep(0.15)

	# Worker B recovers
	worker_b = StreamWorker(real_redis, stream, group, "worker-b")
	recovered = worker_b.recover(min_idle_ms=100, new_consumer="worker-b")

	assert len(recovered) == 1, f"Expected 1 recovered message, got {len(recovered)}"
	recovered_id, recovered_fields = recovered[0]

	# Verify it's the same task
	recovered_task_id = (
		recovered_fields[b"task_id"].decode()
		if isinstance(recovered_fields[b"task_id"], bytes)
		else recovered_fields[b"task_id"]
	)
	assert recovered_task_id == task.id

	# Worker B ACKs — PEL should now be empty
	worker_b.ack(recovered_id)
	pending = real_redis.xpending_range(stream, group, min="-", max="+", count=10)
	assert pending == [], f"PEL should be empty after recovery+ack, got: {pending}"
