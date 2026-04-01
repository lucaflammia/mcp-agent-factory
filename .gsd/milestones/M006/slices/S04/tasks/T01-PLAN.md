---
estimated_steps: 38
estimated_files: 4
skills_used: []
---

# T01: Implement idempotency and circuit breaker modules with full test coverage

Create `src/mcp_agent_factory/streams/idempotency.py` with three classes and `src/mcp_agent_factory/streams/circuit_breaker.py` with one class, export them from `streams/__init__.py`, and write `tests/test_m006_reliability.py` with 7 tests covering all requirements R008–R014.

### idempotency.py

**IdempotencyGuard(redis_client, ttl=300)**
- `already_seen(task_id: str) -> bool`: `r.set(task_id, "1", nx=True, ex=ttl)` returns `True` on first call, `None` on repeat. Return `not bool(result)` so True means already seen.
- `cache_result(task_id: str, result: str) -> None`: `r.set(f"{task_id}:result", result, ex=ttl)`
- `get_cached(task_id: str) -> str | None`: `r.get(f"{task_id}:result")` — decode bytes if needed

**DistributedLock(redis_client, ttl=10)**
- `acquire(key: str) -> bool`: generate a UUID token, `r.set(key, token, nx=True, ex=ttl)` — return bool(result); store token in `self._tokens[key]`
- `release(key: str) -> None`: `GET` key; if value matches stored token, `DELETE` key; remove from `_tokens`

**OutboxRelay**
- `add(state_fn, dispatch_fn)`: append `(state_fn, dispatch_fn)` to internal list
- `flush()`: iterate pairs, call `state_fn()` then `dispatch_fn()` for each; clear the list

### circuit_breaker.py

**CircuitBreaker(threshold=3, recovery_timeout=1.0)**
- State enum: `CLOSED`, `OPEN`, `HALF_OPEN`
- `call(fn, *args, fallback=None, **kwargs)`: 
  - CLOSED: call fn; success → reset failures; exception → increment failures; if failures >= threshold → OPEN, record `_opened_at = time.monotonic()`
  - OPEN: if `time.monotonic() - _opened_at >= recovery_timeout` → go HALF_OPEN and attempt call; else return fallback immediately
  - HALF_OPEN: call fn; success → CLOSED, reset failures; exception → OPEN, record new `_opened_at`
- `state` property returns current State enum value

### test file: tests/test_m006_reliability.py

All tests synchronous. Use `fakeredis.FakeRedis()` for IdempotencyGuard and DistributedLock.

```
test_r008_idempotency_precheck       — already_seen returns False first call, True second call
test_r009_distributed_lock_acquire   — acquire returns True first time; second acquire with same key returns False (key held)
test_r014_result_cache_hit           — cache_result then get_cached returns same string value
test_r010_outbox_relay               — flush calls both state_fn and dispatch_fn; call_order list proves order
test_r011_circuit_opens_after_n_failures — call failing fn threshold times → state == OPEN
test_r013_fallback_on_open_circuit   — when state is OPEN and timeout not elapsed, call() returns fallback without calling fn
test_r012_half_open_recovery         — set recovery_timeout=0.0 so OPEN→HALF_OPEN immediately; successful probe → state == CLOSED
```

### __init__.py exports

Add to `src/mcp_agent_factory/streams/__init__.py`:
```python
from .idempotency import IdempotencyGuard, DistributedLock, OutboxRelay
from .circuit_breaker import CircuitBreaker
```
And extend `__all__`.

## Inputs

- ``src/mcp_agent_factory/streams/__init__.py` — existing exports to extend`
- ``src/mcp_agent_factory/streams/worker.py` — fakeredis usage pattern to follow`

## Expected Output

- ``src/mcp_agent_factory/streams/idempotency.py` — new file with IdempotencyGuard, DistributedLock, OutboxRelay`
- ``src/mcp_agent_factory/streams/circuit_breaker.py` — new file with CircuitBreaker`
- ``src/mcp_agent_factory/streams/__init__.py` — updated exports`
- ``tests/test_m006_reliability.py` — 7 tests covering R008–R014`

## Verification

PYTHONPATH=src pytest tests/test_m006_reliability.py -v
