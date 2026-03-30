---
id: S01
parent: M004
milestone: M004
provides:
  - GET /sse/v1/events with connected event and bus streaming
  - POST /sse/v1/messages for bus injection
  - sse_v1_router factory for reuse
requires:
  []
affects:
  - S02
  - S03
  - S04
key_files:
  - src/mcp_agent_factory/messaging/sse_v1_router.py
  - src/mcp_agent_factory/gateway/app.py
  - tests/test_m004_sse.py
key_decisions:
  - Rename legacy /sse mount to /sse/legacy to prevent prefix-match interference with /sse/v1
  - Test SSE generator logic directly rather than via ASGITransport to avoid blocking in test mode
patterns_established:
  - Test SSE generators directly (not via ASGITransport) to avoid blocking in test mode
  - FastAPI Mount paths must not be prefixes of include_router paths — rename mounts or use distinct prefixes
observability_surfaces:
  - sse.connected topic=... logged at INFO on each connection
  - sse.disconnected topic=... logged at INFO on disconnect
  - sse_v1.publish topic=... sender=... logged at DEBUG on each message post
drill_down_paths:
  - .gsd/milestones/M004/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S01/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-30T06:47:28.552Z
blocker_discovered: false
---

# S01: SSE /v1 Endpoints + Connected Event

**SSE /v1/events and /v1/messages endpoints live, tested, and integrated with gateway bus"**

## What Happened

Added /sse/v1/events and /sse/v1/messages to the gateway. The events endpoint emits a 'connected' SSE event immediately on subscription, then streams bus AgentMessage events. The messages endpoint accepts JSON and publishes to the bus. All 9 tests pass; full suite still green.

## Verification

pytest tests/test_m004_sse.py -v: 9 passed; pytest tests/test_gateway.py -v: 9 passed

## Requirements Advanced

- R002 — SSE /v1 endpoints enable real-time streaming to external clients

## Requirements Validated

None.

## New Requirements Surfaced

- SSE generator testing pattern requires direct unit testing, not ASGI transport streaming

## Requirements Invalidated or Re-scoped

None.

## Deviations

Legacy SSE mount renamed from /sse to /sse/legacy. SSE async tests use direct generator testing instead of ASGITransport streaming.

## Known Limitations

ASGITransport + EventSourceResponse infinite generators cannot be streamed in tests without real async concurrency. Tests use generator-level and bus-level assertions instead.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/messaging/sse_v1_router.py` — New SSE v1 router with /events (connected event + bus streaming) and /messages (publish to bus)
- `src/mcp_agent_factory/gateway/app.py` — Mount sse_v1_router at /sse/v1; renamed legacy mount to /sse/legacy
- `tests/test_m004_sse.py` — 9 tests covering SSE v1 endpoints, bus delivery, and gateway tool-call events
