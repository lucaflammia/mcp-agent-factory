---
estimated_steps: 12
estimated_files: 1
skills_used: []
---

# T01: TaskItem model, SchedulerState enum, and TaskScheduler core

1. Create src/mcp_agent_factory/scheduler.py
2. Define SchedulerState enum: PENDING, RUNNING, COMPLETED, FAILED
3. Define TaskItem Pydantic v2 model: id (str, default uuid4), name (str), priority (int, default 0), args (dict, default {}), state (SchedulerState, default PENDING), retry_count (int, default 0), max_retries (int, default 3)
4. Implement TaskScheduler class:
   - __init__: self._inbox = asyncio.Queue(); self._heap: list[tuple[int, TaskItem]] = []; self._running = False
   - add_task(item: TaskItem): push (-priority, item) onto heap via heapq.heappush (negate for max-priority-first)
   - get_next_task() -> TaskItem | None: heappop if heap non-empty, else None
   - async run(handler: Callable[[TaskItem], Awaitable[Any]]): loop — await inbox, add_task, dispatch via _dispatch
   - async _dispatch(item, handler): set state RUNNING, log, call await handler(item), set COMPLETED on success; on exception set FAILED and retry if retry_count < max_retries (increment retry_count, re-enqueue)
   - stop(): set self._running = False
5. Structured logging: emit one JSON log line per state transition via logger.debug(json.dumps({...}))
6. Export TaskScheduler, TaskItem, SchedulerState from scheduler.py

## Inputs

- `src/mcp_agent_factory/models.py`
- `src/mcp_agent_factory/config/privacy.py`

## Expected Output

- `src/mcp_agent_factory/scheduler.py`

## Verification

python -c "from mcp_agent_factory.scheduler import TaskScheduler, TaskItem, SchedulerState; print('imports ok')"
