---
id: S01
parent: M006
milestone: M006
provides:
  - StreamWorker class at src/mcp_agent_factory/streams/worker.py with full XREADGROUP/ACK/PEL API
  - fakeredis test pattern for streams (tests/test_m006_streams.py)
  - R001 and R002 validated
requires:
  []
affects:
  - S02
  - S03
  - S04
  - S05
key_files:
  - src/mcp_agent_factory/streams/__init__.py
  - src/mcp_agent_factory/streams/worker.py
  - tests/test_m006_streams.py
key_decisions:
  - Pass streams as keyword dict in xreadgroup — fakeredis 2.34.1 raises TypeError on positional streams arg
patterns_established:
  - StreamWorker pattern: ensure_group() on init guard (BUSYGROUP ignored), publish returns str message_id, claim_one returns (bytes, dict) or None, recover uses xpending_range + xclaim
observability_surfaces:
  - None — this is a library component; observability surfaces deferred to S04/S05
drill_down_paths:
  - .gsd/milestones/M006/slices/S01/tasks/T01-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-04-01T14:21:43.117Z
blocker_discovered: false
---

# S01: Redis Streams Worker

**StreamWorker implemented with XREADGROUP claim/ACK and PEL crash recovery, fully tested via fakeredis with 3 passing tests.**

## What Happened

Single task T01 created the streams package (src/mcp_agent_factory/streams/__init__.py and worker.py) implementing StreamWorker with five methods: ensure_group (xgroup_create with BUSYGROUP guard), publish (xadd returning message_id), claim_one (xreadgroup with streams as keyword dict), ack (xack), and recover (xpending_range + xclaim). The critical implementation detail was passing streams as a keyword dict to xreadgroup — fakeredis 2.34.1 raises TypeError when streams is passed positionally. Three test cases in tests/test_m006_streams.py cover R001 (claim+ack clears PEL) and R002 (PEL crash recovery) and the empty-stream edge case. All tests pass in ~0.5s against fakeredis with no external processes.

## Verification

pytest tests/test_m006_streams.py -v — 3 passed in 0.50s. All slice success criteria met.

## Requirements Advanced

- R001 — StreamWorker.claim_one + ack implemented and tested — tasks claimed by exactly one consumer, PEL cleared on ACK
- R002 — StreamWorker.recover implemented and tested — un-ACKed message stays in PEL and is reclaimed via xclaim

## Requirements Validated

- R001 — test_worker_claim_and_ack: publish → claim_one returns (msg_id, fields) → ack → xpending_range returns [] — PASSED
- R002 — test_worker_pel_recovery: publish → claim_one without ack → xpending_range non-empty → recover() returns message — PASSED

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

StreamWorker is synchronous (uses redis-py, not redis.asyncio). Async variant deferred to when a real Redis deployment is needed (R016/R017).

## Follow-ups

S02 and S03 can build on StreamWorker independently. S04 will wrap StreamWorker with idempotency and circuit breaker logic.

## Files Created/Modified

- `src/mcp_agent_factory/streams/__init__.py` — New package init for streams module
- `src/mcp_agent_factory/streams/worker.py` — StreamWorker class with ensure_group, publish, claim_one, ack, recover
- `tests/test_m006_streams.py` — 3 tests covering R001, R002, and empty-stream edge case
