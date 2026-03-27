"""
TaskScheduler — asyncio-native autonomous agent loop.

Architecture:
  - Inbox:        asyncio.Queue — producers push TaskItem objects directly.
  - Priority:     heapq max-heap (negated int priority — higher int runs first).
  - Dispatch:     async handler call with structured retry on exception.
  - Observability: one JSON log line per state transition to stderr.

Usage::

    async def my_handler(task: TaskItem) -> None:
        print(f"Handling {task.name}")

    scheduler = TaskScheduler()
    await scheduler._inbox.put(TaskItem(name="hello", priority=5))
    await asyncio.wait_for(scheduler.run(my_handler), timeout=1.0)
"""
from __future__ import annotations

import asyncio
import heapq
import json
import logging
import uuid
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class SchedulerState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    priority: int = 0
    args: dict[str, Any] = Field(default_factory=dict)
    state: SchedulerState = SchedulerState.PENDING
    retry_count: int = 0
    max_retries: int = 3


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class TaskScheduler:
    """
    Autonomous agent loop built on asyncio.

    Producers push TaskItem objects into ``_inbox``.  The run loop drains the
    inbox into an internal max-priority heap, then dispatches the highest-
    priority task to the supplied ``handler`` coroutine.

    Retry logic: on handler exception, retry_count is incremented and the task
    is re-enqueued (back through the inbox) until retry_count == max_retries,
    at which point the task is marked FAILED and dropped.
    """

    def __init__(self) -> None:
        self._inbox: asyncio.Queue[TaskItem] = asyncio.Queue()
        self._heap: list[tuple[int, int, TaskItem]] = []
        # Second element is a tie-breaker counter to keep heapq stable
        self._counter: int = 0
        self._running: bool = False

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def add_task(self, item: TaskItem) -> None:
        """Push a TaskItem onto the priority heap (higher priority = runs first)."""
        heapq.heappush(self._heap, (-item.priority, self._counter, item))
        self._counter += 1

    def get_next_task(self) -> TaskItem | None:
        """Pop the highest-priority task, or return None if heap is empty."""
        if not self._heap:
            return None
        _, _, item = heapq.heappop(self._heap)
        return item

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    async def run(
        self,
        handler: Callable[[TaskItem], Awaitable[Any]],
    ) -> None:
        """
        Drain the inbox into the heap, then dispatch tasks until stopped.

        Exits when ``stop()`` has been called AND both the inbox and heap
        are empty.
        """
        self._running = True
        while self._running:
            # Drain all currently available inbox items into the heap
            while not self._inbox.empty():
                item = self._inbox.get_nowait()
                self.add_task(item)

            task = self.get_next_task()
            if task is None:
                if not self._running:
                    break
                # Wait for the next inbox item before looping again
                try:
                    item = await asyncio.wait_for(self._inbox.get(), timeout=0.05)
                    self.add_task(item)
                except asyncio.TimeoutError:
                    continue
                continue

            await self._dispatch(task, handler)

    def stop(self) -> None:
        """Signal the run loop to exit after the current task completes."""
        self._running = False

    # ------------------------------------------------------------------
    # Dispatch + retry
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        item: TaskItem,
        handler: Callable[[TaskItem], Awaitable[Any]],
    ) -> None:
        item.state = SchedulerState.RUNNING
        self._log(item)
        try:
            await handler(item)
            item.state = SchedulerState.COMPLETED
            self._log(item)
        except Exception as exc:
            item.retry_count += 1
            if item.retry_count <= item.max_retries:
                item.state = SchedulerState.PENDING
                self._log(item, error=str(exc))
                # Re-enqueue through the inbox so it participates in priority ordering
                await self._inbox.put(item)
            else:
                item.state = SchedulerState.FAILED
                self._log(item, error=str(exc))

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def _log(self, item: TaskItem, error: str | None = None) -> None:
        """Emit one JSON log line per state transition."""
        payload: dict[str, Any] = {
            "event": "task_state",
            "task_id": item.id,
            "name": item.name,
            "state": item.state.value,
            "priority": item.priority,
            "retry_count": item.retry_count,
        }
        if error is not None:
            payload["error"] = error
        logger.debug(json.dumps(payload))
