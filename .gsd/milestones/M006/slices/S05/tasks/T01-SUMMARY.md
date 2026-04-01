---
id: T01
parent: S05
milestone: M006
provides: []
requires: []
affects: []
key_files: ["tests/test_m006_integration.py"]
key_decisions: ["Use lock: prefix for DistributedLock keys to avoid collision with IdempotencyGuard's task_id key in integration tests"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "PYTHONPATH=src pytest tests/ -v — 231 passed in 67.49s"
completed_at: 2026-04-01T20:16:23.488Z
blocker_discovered: false
---

# T01: M006 integration test written and full suite confirmed green — 231/231 passed.

> M006 integration test written and full suite confirmed green — 231/231 passed.

## What Happened
---
id: T01
parent: S05
milestone: M006
key_files:
  - tests/test_m006_integration.py
key_decisions:
  - Use lock: prefix for DistributedLock keys to avoid collision with IdempotencyGuard's task_id key in integration tests
duration: ""
verification_result: passed
completed_at: 2026-04-01T20:16:23.493Z
blocker_discovered: false
---

# T01: M006 integration test written and full suite confirmed green — 231/231 passed.

**M006 integration test written and full suite confirmed green — 231/231 passed.**

## What Happened

Wrote test_m006_integration.py exercising the full M006 component stack in one synchronous test using a shared fakeredis client. Fixed three API mismatches discovered during writing (lock key collision, EventLog read return type, StreamWorker.ack signature). Full suite 231/231 green.

## Verification

PYTHONPATH=src pytest tests/ -v — 231 passed in 67.49s

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `PYTHONPATH=src pytest tests/ -v` | 0 | ✅ pass | 67490ms |


## Deviations

Three small test fixes during development: (1) lock key must be namespaced separately from the idempotency key since both use SET NX on the same Redis; (2) InProcessEventLog.read returns (msg_id, event) tuples, not dicts; (3) StreamWorker.ack takes only msg_id, not (stream, group, msg_id).

## Known Issues

None.

## Files Created/Modified

- `tests/test_m006_integration.py`


## Deviations
Three small test fixes during development: (1) lock key must be namespaced separately from the idempotency key since both use SET NX on the same Redis; (2) InProcessEventLog.read returns (msg_id, event) tuples, not dicts; (3) StreamWorker.ack takes only msg_id, not (stream, group, msg_id).

## Known Issues
None.
