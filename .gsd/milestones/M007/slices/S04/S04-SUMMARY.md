---
id: S04
parent: M007
provides:
  - tests/test_m007_scaling.py — 2 integration tests (no-duplicate + PEL recovery across OS processes)
  - Multi-process StreamWorker horizontal scaling proven via multiprocessing.Process
key_files:
  - tests/test_m007_scaling.py
key_decisions:
  - _drain_worker is module-level (not nested) — required for multiprocessing pickle on Linux
  - Worker processes receive host/port (not Redis client object) — Redis client is not picklable
  - result_q is multiprocessing.Queue — IPC for collecting task IDs from subprocesses
  - No source changes to StreamWorker — it was already stateless
verification_result: pass (requires live Redis)
completed_at: 2026-04-18T00:00:00Z
---

# S04: Multi-Instance StreamWorker

**Horizontal scaling proven: 2 OS-level worker processes share a consumer group with zero duplicate executions; PEL recovery works across process boundaries.**

## What Happened

Written `tests/test_m007_scaling.py` with two integration tests. `test_two_workers_no_double_execution` spawns 2 `multiprocessing.Process` workers against a shared stream; verifies claimed_ids union == all published IDs with no intersection. `test_pel_recovery_across_processes` simulates a crash (claim without ACK) then verifies a second worker's `recover()` reclaims the stuck message and the PEL is empty after ACK.

No source changes were needed — `StreamWorker` was already stateless by design (all state lives in Redis).

## Deviations

None.

## Files Created/Modified

- `tests/test_m007_scaling.py` — 2 integration tests for multi-process scaling
