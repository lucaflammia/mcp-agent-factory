---
id: T02
parent: S04
milestone: M005
provides:
  - tests/test_s04.py with 7 passing test cases covering full S04 surface
key_files:
  - tests/test_s04.py
key_decisions:
  - _populated_store() uses store.upsert() directly — IngestionWorker requires a bus arg so bypassing it is cleaner for unit tests
  - test_gateway_query_knowledge_base_dev_mode populates under 'dev' owner_id since DEV_MODE resolves claims to 'dev'
  - bus.subscribe returns asyncio.Queue; use q.empty() + q.get_nowait() for sync test assertions (matches existing test_gateway.py pattern)
patterns_established:
  - subscribe before action + assert queue non-empty pattern for SSE/bus event tests
observability_surfaces:
  - none added (tests exercise existing surfaces)
duration: ~10m
verification_result: passed
completed_at: 2026-03-31
blocker_discovered: false
---

# T02: Write and verify tests/test_s04.py — 7 cases covering all new surface

**Created tests/test_s04.py with 7 passing tests covering query_knowledge_base, LibrarianAgent, gateway wiring, SSE event emission, and cross-tenant isolation.**

## What Happened

Wrote `tests/test_s04.py`. Three adaptations from the plan were needed:
1. `IngestionWorker.__init__` takes `(bus, store, embedder)` — used `store.upsert()` directly in `_populated_store()` helper instead.
2. `MessageBus.subscribe(topic)` takes only one argument and returns an `asyncio.Queue` — fixed the SSE event test to call `bus.subscribe("knowledge.retrieved")` and use `q.empty()` / `q.get_nowait()`.
3. DEV_MODE resolves owner_id to `'dev'` — the `test_gateway_query_knowledge_base_dev_mode` test needed its data stored under `'dev'` to return non-empty results (separate from the isolation test which validates 'alice' data is inaccessible under 'dev').

## Verification

```
PYTHONPATH=src pytest tests/test_s04.py -v   # 7/7 passed
PYTHONPATH=src pytest tests/test_s04.py tests/test_ingest.py tests/test_vector_store.py tests/test_gateway.py tests/test_pipeline.py tests/test_schema_validation.py -q   # 60/60 passed
```

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `PYTHONPATH=src pytest tests/test_s04.py -v` | 0 | ✅ pass | 2.81s |
| 2 | `PYTHONPATH=src pytest tests/test_s04.py tests/test_ingest.py tests/test_vector_store.py tests/test_gateway.py tests/test_pipeline.py tests/test_schema_validation.py -q` | 0 | ✅ pass | 9.19s |

## Diagnostics

Run `PYTHONPATH=src pytest tests/test_s04.py -v` for the S04 surface. All 7 cases are independent and fast (<3s total).

## Deviations

- `_populated_store()` uses `store.upsert()` directly instead of `IngestionWorker` (which requires a bus argument not needed here).
- `bus.subscribe` takes only a topic argument and returns `asyncio.Queue` — test adapted from plan's `queue.Queue` approach.
- `test_gateway_query_knowledge_base_dev_mode` seeds data under `'dev'` owner_id (not `'alice'`) since DEV_MODE passes `None` claims → owner_id `'dev'`.

## Known Issues

None.

## Files Created/Modified

- `tests/test_s04.py` — new: 7 S04 test cases
