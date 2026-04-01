---
id: S05
parent: M006
milestone: M006
provides:
  - Full M006 regression confirmation — 231 tests green
  - End-to-end integration test at tests/test_m006_integration.py
requires:
  - slice: S04
    provides: R008-R014 validated
  - slice: S03
    provides: ValidationGate + InternalServiceLayer
  - slice: S02
    provides: EventLog + topic helpers
  - slice: S01
    provides: StreamWorker
affects:
  []
key_files:
  - tests/test_m006_integration.py
key_decisions:
  - DistributedLock keys should use a namespace prefix (lock:) to avoid collision with IdempotencyGuard keys in shared Redis
patterns_established:
  - Use lock: key prefix in integration tests to avoid SET NX collision between IdempotencyGuard and DistributedLock
observability_surfaces:
  - none
drill_down_paths:
  - .gsd/milestones/M006/slices/S05/tasks/T01-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-04-01T20:16:40.501Z
blocker_discovered: false
---

# S05: Integration &amp; Regression

**Integration test written, pre-existing regression fixed, full suite 231/231 green.**

## What Happened

Wrote the M006 integration test and fixed the pre-existing test_s04.py regression (set_vector_store not propagating to _service_layer singleton). Full suite 231/231 green.

## Verification

PYTHONPATH=src pytest tests/ -v — 231 passed in 67.49s

## Requirements Advanced

- R015 — Full suite 231/231 green — no regressions from M001–M005

## Requirements Validated

- R015 — PYTHONPATH=src pytest tests/ -v — 231 passed, 0 failed

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `tests/test_m006_integration.py` — New: end-to-end integration test wiring all M006 components
- `src/mcp_agent_factory/gateway/app.py` — Fix: set_vector_store/set_embedder now also update _service_layer attributes
