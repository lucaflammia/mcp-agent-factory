---
id: T01
parent: S03
milestone: M003
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/messaging/bus.py", "src/mcp_agent_factory/messaging/sse_router.py"]
key_decisions: ["MessageBus uses put_nowait (not await put) since publish is sync — callers don’t await it", "create_sse_router factory pattern for injectable bus in tests"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "imports ok."
completed_at: 2026-03-27T10:57:16.518Z
blocker_discovered: false
---

# T01: MessageBus asyncio pub/sub and SSE EventSourceResponse router — factory-injectable for tests.

> MessageBus asyncio pub/sub and SSE EventSourceResponse router — factory-injectable for tests.

## What Happened
---
id: T01
parent: S03
milestone: M003
key_files:
  - src/mcp_agent_factory/messaging/bus.py
  - src/mcp_agent_factory/messaging/sse_router.py
key_decisions:
  - MessageBus uses put_nowait (not await put) since publish is sync — callers don’t await it
  - create_sse_router factory pattern for injectable bus in tests
duration: ""
verification_result: passed
completed_at: 2026-03-27T10:57:16.582Z
blocker_discovered: false
---

# T01: MessageBus asyncio pub/sub and SSE EventSourceResponse router — factory-injectable for tests.

**MessageBus asyncio pub/sub and SSE EventSourceResponse router — factory-injectable for tests.**

## What Happened

MessageBus fan-out pub/sub with per-topic subscriber queues. SSE router wraps queue in EventSourceResponse with 30s keepalive. Factory pattern keeps bus injectable.

## Verification

imports ok.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -c "from mcp_agent_factory.messaging.bus import MessageBus; from mcp_agent_factory.messaging.sse_router import create_sse_router; print('ok')"` | 0 | ✅ pass | 200ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/messaging/bus.py`
- `src/mcp_agent_factory/messaging/sse_router.py`


## Deviations
None.

## Known Issues
None.
