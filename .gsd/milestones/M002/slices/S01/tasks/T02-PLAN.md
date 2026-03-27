---
estimated_steps: 12
estimated_files: 1
skills_used: []
---

# T02: pytest-asyncio tests for TaskScheduler

1. Create tests/test_scheduler.py
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

## Inputs

- `src/mcp_agent_factory/scheduler.py`

## Expected Output

- `tests/test_scheduler.py`

## Verification

python -m pytest tests/test_scheduler.py -v
