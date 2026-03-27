"""
pytest-asyncio tests for TaskScheduler.

All tests use asyncio_mode = "auto" (configured in pyproject.toml) so no
@pytest.mark.asyncio decorator is needed.

Pattern for bounding test execution: asyncio.wait_for(scheduler.run(...), timeout=N)
raises asyncio.TimeoutError when the scheduler hasn't stopped in time — we
call scheduler.stop() from within the handler or after the expected work is done.
"""
from __future__ import annotations

import asyncio
import json
import logging

import pytest

from mcp_agent_factory.scheduler import SchedulerState, TaskItem, TaskScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_until_empty(scheduler: TaskScheduler, handler, *, timeout: float = 1.0) -> None:
	"""Run the scheduler until the inbox and heap are empty, then stop."""
	async def _stopping_handler(item: TaskItem):
		await handler(item)
		# After each completion, check if there's no more work
		if scheduler._inbox.empty() and not scheduler._heap:
			scheduler.stop()

	try:
		await asyncio.wait_for(scheduler.run(_stopping_handler), timeout=timeout)
	except asyncio.TimeoutError:
		scheduler.stop()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestTaskItemDefaults:
	def test_task_item_defaults(self):
		item = TaskItem(name="test")
		assert item.state == SchedulerState.PENDING
		assert item.retry_count == 0
		assert item.max_retries == 3
		assert item.priority == 0
		assert item.args == {}
		assert item.id  # non-empty string

	def test_task_item_id_is_unique(self):
		a = TaskItem(name="a")
		b = TaskItem(name="b")
		assert a.id != b.id


class TestPriorityQueue:
	def test_add_and_get_priority(self):
		scheduler = TaskScheduler()
		low = TaskItem(name="low", priority=1)
		high = TaskItem(name="high", priority=10)
		mid = TaskItem(name="mid", priority=5)
		scheduler.add_task(low)
		scheduler.add_task(high)
		scheduler.add_task(mid)
		assert scheduler.get_next_task().name == "high"
		assert scheduler.get_next_task().name == "mid"
		assert scheduler.get_next_task().name == "low"

	def test_get_next_task_empty_returns_none(self):
		scheduler = TaskScheduler()
		assert scheduler.get_next_task() is None

	def test_priority_queue_ordering_five_tasks(self):
		scheduler = TaskScheduler()
		priorities = [3, 1, 5, 2, 4]
		for p in priorities:
			scheduler.add_task(TaskItem(name=f"task-{p}", priority=p))
		result = []
		while (t := scheduler.get_next_task()) is not None:
			result.append(t.priority)
		assert result == sorted(priorities, reverse=True)


class TestDispatch:
	async def test_dispatch_success(self):
		scheduler = TaskScheduler()
		completed: list[str] = []

		async def handler(item: TaskItem) -> None:
			completed.append(item.name)

		item = TaskItem(name="work", priority=1)
		await scheduler._inbox.put(item)
		await _run_until_empty(scheduler, handler)

		assert "work" in completed
		assert item.state == SchedulerState.COMPLETED

	async def test_dispatch_failure_retries(self):
		"""After max_retries+1 dispatch attempts, task reaches FAILED state."""
		scheduler = TaskScheduler()
		attempts = 0

		async def always_fails(t: TaskItem) -> None:
			nonlocal attempts
			attempts += 1
			raise RuntimeError("always fails")

		item = TaskItem(name="retry-direct", priority=1, max_retries=2)

		# Drive dispatch manually: initial attempt + 2 retries = 3 total
		for _ in range(item.max_retries + 1):
			if item.state != SchedulerState.FAILED:
				await scheduler._dispatch(item, always_fails)

		assert item.state == SchedulerState.FAILED
		assert attempts == item.max_retries + 1  # 3 total attempts
		assert item.retry_count == item.max_retries + 1

	async def test_dispatch_no_retry_when_max_retries_zero(self):
		scheduler = TaskScheduler()
		item = TaskItem(name="no-retry", priority=1, max_retries=0)

		async def failing_handler(t: TaskItem) -> None:
			raise RuntimeError("instant fail")

		await scheduler._dispatch(item, failing_handler)
		assert item.state == SchedulerState.FAILED
		assert item.retry_count == 1

	async def test_dispatch_sets_running_then_completed(self):
		scheduler = TaskScheduler()
		observed_states: list[SchedulerState] = []

		async def observing_handler(item: TaskItem) -> None:
			observed_states.append(item.state)

		item = TaskItem(name="observe", priority=0)
		await scheduler._dispatch(item, observing_handler)

		assert observed_states == [SchedulerState.RUNNING]
		assert item.state == SchedulerState.COMPLETED


class TestStructuredLogging:
	async def test_structured_log_on_transition(self, caplog):
		scheduler = TaskScheduler()
		item = TaskItem(name="log-test", priority=3)

		async def noop(t: TaskItem) -> None:
			pass

		with caplog.at_level(logging.DEBUG, logger="mcp_agent_factory.scheduler"):
			await scheduler._dispatch(item, noop)

		log_messages = [r.message for r in caplog.records]
		# Should have at least RUNNING and COMPLETED transitions
		parsed = [json.loads(m) for m in log_messages if m.startswith("{")]
		states_logged = [p["state"] for p in parsed if "state" in p]
		assert "running" in states_logged
		assert "completed" in states_logged

	async def test_log_contains_task_id_and_name(self, caplog):
		scheduler = TaskScheduler()
		item = TaskItem(name="named-task", priority=0)

		async def noop(t: TaskItem) -> None:
			pass

		with caplog.at_level(logging.DEBUG, logger="mcp_agent_factory.scheduler"):
			await scheduler._dispatch(item, noop)

		log_messages = [r.message for r in caplog.records]
		parsed = [json.loads(m) for m in log_messages if m.startswith("{")]
		running_log = next(p for p in parsed if p.get("state") == "running")
		assert running_log["task_id"] == item.id
		assert running_log["name"] == "named-task"

	async def test_log_contains_error_on_failure(self, caplog):
		scheduler = TaskScheduler()
		item = TaskItem(name="fail-task", priority=0, max_retries=0)

		async def boom(t: TaskItem) -> None:
			raise ValueError("test error")

		with caplog.at_level(logging.DEBUG, logger="mcp_agent_factory.scheduler"):
			await scheduler._dispatch(item, boom)

		log_messages = [r.message for r in caplog.records]
		parsed = [json.loads(m) for m in log_messages if m.startswith("{")]
		failed_log = next(p for p in parsed if p.get("state") == "failed")
		assert "error" in failed_log
		assert "test error" in failed_log["error"]
