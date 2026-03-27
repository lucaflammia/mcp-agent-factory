# S01: Async TaskScheduler

**Goal:** Implement an asyncio-native stateful TaskScheduler with asyncio.Queue inbox, integer-priority queue, async run loop, fail_task retry logic, and structured state logging. Establish pytest-asyncio fixture patterns for the rest of the milestone.
**Demo:** After this: pytest tests/test_scheduler.py -v passes — asyncio task loop with priority queue, retry logic, and state transitions proven by async tests.

## Tasks
- [x] **T01: TaskItem/SchedulerState models and TaskScheduler with priority heap, async run loop, and structured retry implemented.** — 1. Create src/mcp_agent_factory/scheduler.py
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
  - Estimate: 30min
  - Files: src/mcp_agent_factory/scheduler.py
  - Verify: python -c "from mcp_agent_factory.scheduler import TaskScheduler, TaskItem, SchedulerState; print('imports ok')"
- [x] **T02: 12 pytest-asyncio tests covering TaskScheduler state transitions, priority ordering, retry logic, and structured JSON logging — all passing.** — 1. Create tests/test_scheduler.py
2. Write async fixtures using pytest-asyncio (asyncio_mode=auto already configured)
3. Test cases:
   - test_task_item_defaults: TaskItem() has correct defaults (PENDING state, retry_count=0)
   - test_add_and_get_priority: add 3 tasks with different priorities, get_next_task() returns highest priority first
   - test_dispatch_success: scheduler dispatches task to handler, state transitions PENDING→RUNNING→COMPLETED
   - test_dispatch_failure_retries: handler raises exception; task is re-enqueued retry_count times, then FAILED
   - test_dispatch_no_retry_when_max_reached: max_retries=0 means immediate FAILED on first exception
   - test_structured_log_on_transition: caplog captures JSON log lines with task_id and state fields
   - test_priority_queue_ordering: 5 tasks at different priorities dispatched in priority order
4. Use asyncio.Queue as inbox: push tasks via scheduler._inbox.put_nowait(item) in tests
5. Run scheduler with asyncio.wait_for to bound test execution time
  - Estimate: 25min
  - Files: tests/test_scheduler.py
  - Verify: python -m pytest tests/test_scheduler.py -v
