# S05: Integration & Regression

**Goal:** Write an end-to-end integration test exercising all M006 components together (StreamWorker → IdempotencyGuard → CircuitBreaker → EventLog), confirm the full pytest tests/ suite is green, and close out M006.
**Demo:** After this: pytest tests/ -v passes — all M001–M006 tests green, zero regressions

## Tasks
- [x] **T01: M006 integration test written and full suite confirmed green — 231/231 passed.** — Write `tests/test_m006_integration.py` with an end-to-end test that wires StreamWorker, IdempotencyGuard, DistributedLock, OutboxRelay, CircuitBreaker, and InProcessEventLog together using fakeredis. Then run the full suite and confirm 0 regressions.

### Integration scenario to implement

1. Set up a fakeredis client and a shared stream.
2. Create a `StreamWorker`, `IdempotencyGuard`, `DistributedLock`, `OutboxRelay`, and `CircuitBreaker` all sharing the same fakeredis client.
3. Create an `InProcessEventLog`.
4. Publish one task message to the stream via `StreamWorker.publish`.
5. `claim_one` the message.
6. Check `guard.already_seen(task_id)` → False (first time).
7. Acquire `lock.acquire(task_id)` → True.
8. Use `CircuitBreaker.call(fn)` where `fn` appends to a result list — confirm CLOSED state and result received.
9. Append a `task.completed` event to the event log via `InProcessEventLog.append`.
10. `OutboxRelay.add(state_fn, dispatch_fn)` then `flush()` — confirm both called.
11. `worker.ack(stream, group, msg_id)` — confirm PEL is empty via `xpending_range`.
12. Check `guard.already_seen(task_id)` → True (second call, key now set).
13. `lock.release(task_id)` — confirm key deleted.

This single test proves all components compose correctly end-to-end.

Also run full suite and assert 0 failures.
  - Estimate: 30m
  - Files: tests/test_m006_integration.py
  - Verify: PYTHONPATH=src pytest tests/ -v 2>&1 | tail -5
