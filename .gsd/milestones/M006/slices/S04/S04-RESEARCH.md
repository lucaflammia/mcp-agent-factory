# S04 Research: Idempotency + Circuit Breakers

## Summary

S04 is targeted work: two new modules (`streams/idempotency.py`, `streams/circuit_breaker.py`) plus one test file (`tests/test_m006_reliability.py`). All patterns are already validated in the codebase (fakeredis SET NX EX confirmed working; StreamWorker/EventLog patterns established). No new libraries. No risky integrations.

## Requirements Coverage

| Req | Description | What S04 must deliver |
|-----|-------------|----------------------|
| R008 | Redis pre-check idempotency (SET NX) | `IdempotencyGuard.check(task_id)` → True if already seen |
| R009 | Distributed lock (SET NX EX single-node) | `DistributedLock.acquire(key, ttl)` / `.release(key)` |
| R010 | Transactional Outbox Pattern | `OutboxRelay` — accumulate state+message pairs, flush atomically |
| R011 | Circuit breaker on LLM calls | `CircuitBreaker` CLOSED→OPEN→HALF_OPEN; N failures → open |
| R012 | Circuit breaker on vector store | Same `CircuitBreaker` class, independent instance |
| R013 | Fallback to Internal Knowledge on open | `LibrarianAgent` path returned when circuit open |
| R014 | No duplicate LLM calls on retry | Post-execution cache: `get(task_id)` before calling; `set` after |

## Implementation Landscape

### New files to create

**`src/mcp_agent_factory/streams/idempotency.py`**

Three classes:

1. `IdempotencyGuard` — wraps a sync fakeredis client (same type as `StreamWorker`):
   - `already_seen(task_id: str) -> bool`: `SET NX EX ttl` returns `None` if already set → True
   - `cache_result(task_id: str, result: str) -> None`: `SET task_id:result result EX ttl`
   - `get_cached(task_id: str) -> str | None`: `GET task_id:result`

2. `DistributedLock` — context manager using SET NX EX:
   - `acquire(key, ttl_seconds) -> bool`
   - `release(key) -> None` — DELETE only if still owner (use GETDEL or check value)
   - Simple: store a random token on acquire, only delete if value matches

3. `OutboxRelay` — in-memory list of `(state_write_fn, dispatch_fn)` pairs:
   - `add(state_fn, dispatch_fn)` — queue a pair
   - `flush()` — call all state_fns then all dispatch_fns in order; clear the list

**`src/mcp_agent_factory/streams/circuit_breaker.py`**

`CircuitBreaker` class:
- State enum: `CLOSED`, `OPEN`, `HALF_OPEN`
- Constructor: `CircuitBreaker(threshold: int = 3, recovery_timeout: float = 1.0)`
- `call(fn, *args, fallback=None, **kwargs)` — the main entry point:
  - CLOSED: call fn; on success reset failures; on failure increment → open if threshold hit
  - OPEN: check if recovery_timeout elapsed → if yes go HALF_OPEN; else return fallback immediately
  - HALF_OPEN: call fn; on success → CLOSED; on failure → OPEN again
- Use `time.monotonic()` for timeout tracking (no external deps)
- `state` property for test assertions

### Test file: `tests/test_m006_reliability.py`

Seven tests to cover all 7 requirements:

```
test_r008_idempotency_precheck          — already_seen False first time, True second time
test_r009_distributed_lock_acquire      — acquire returns True; second acquire returns False
test_r014_result_cache_hit              — cache_result then get_cached returns same value
test_r010_outbox_relay                  — flush calls state_fn and dispatch_fn in order
test_r011_circuit_opens_after_n_failures — N failures → state == OPEN
test_r013_fallback_on_open_circuit      — call() on OPEN returns fallback without calling fn
test_r012_half_open_recovery            — after recovery_timeout, probe succeeds → CLOSED
```

All tests are synchronous (IdempotencyGuard uses sync fakeredis; CircuitBreaker has no async).

### Export updates

`src/mcp_agent_factory/streams/__init__.py` — add:
```python
from .idempotency import IdempotencyGuard, DistributedLock, OutboxRelay
from .circuit_breaker import CircuitBreaker
```

## Key Implementation Details

### IdempotencyGuard — SET NX EX pattern

Confirmed working with fakeredis:
```python
r.set("k", "v", nx=True, ex=5)  # → True (acquired)
r.set("k", "v", nx=True, ex=5)  # → None (already exists)
```
`already_seen` logic: attempt SET NX; if result is `None` → key already existed → already seen. Note: the semantics are inverted — SET NX EX returns `True` on **first** call, `None` on subsequent. So `already_seen` returns `not bool(r.set(key, "1", nx=True, ex=ttl))`.

### DistributedLock — token-based ownership

Store a UUID token as the value so `release` only deletes the key if the stored value still matches (prevents releasing another holder's lock after TTL expiry). Use `GET` + conditional `DELETE` (two commands; safe for single-node).

### OutboxRelay — simplest possible

In-memory list. No Redis needed. Flush: iterate pairs, call state_fn then dispatch_fn. The "atomic" guarantee is in-process (same thread), which is the correct scope for this milestone.

### CircuitBreaker — state machine

```
CLOSED → failure_count reaches threshold → OPEN
OPEN   → recovery_timeout elapsed       → HALF_OPEN
HALF_OPEN → success                     → CLOSED
HALF_OPEN → failure                     → OPEN
```

Use `time.monotonic()` snapshot stored as `_opened_at`. In `call()`, if OPEN and `now - _opened_at >= recovery_timeout` → transition to HALF_OPEN before the call.

For R013 (Internal Knowledge fallback), the `fallback` parameter to `call()` is a string like `"[Internal Knowledge] No LLM available"`. Tests just check the return value equals the fallback.

## Verification Command

```bash
PYTHONPATH=src pytest tests/test_m006_reliability.py -v
```

All 7 tests must pass. No external processes required.

## Recommendation

**Single task T01** — implement both modules and the test file together. They are tightly coupled (tests exercise both modules) and neither is independently deployable. Total code ~120 lines across two modules + ~80 lines of tests. No risk of task ordering issues.
