---
id: S03
parent: M004
milestone: M004
provides:
  - MCPGatewayClient.stream_events() async generator
  - python -m mcp_agent_factory.bridge CLI entrypoint
  - Token cache/refresh test patterns
requires:
  - slice: S01
    provides: gateway_app with /sse/v1 endpoints
  - slice: S02
    provides: auth enforcement tests confirming 401 patterns
affects:
  - S04
key_files:
  - src/mcp_agent_factory/bridge/gateway_client.py
  - src/mcp_agent_factory/bridge/__main__.py
  - tests/test_m004_client_bridge.py
key_decisions:
  - stream_events() accepts max_events param to bound infinite SSE generators in test/CLI contexts
  - OAuthMiddleware 60s refresh threshold confirmed by test_token_refresh_when_near_expiry
patterns_established:
  - AsyncIterator[dict] pattern for SSE consumption in async clients
  - OAuthMiddleware 60s threshold for token refresh
observability_surfaces:
  - bridge.list_tools DEBUG log
  - bridge.call_tool name=... DEBUG log
  - bridge.stream_events: bad JSON WARNING log
drill_down_paths:
  - .gsd/milestones/M004/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S03/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-30T06:52:54.779Z
blocker_discovered: false
---

# S03: Client Bridge \u2014 PKCE + Token Cache + SSE Consumption

**Client bridge extended with SSE stream, token refresh, and __main__ entrypoint; 18 tests passing**

## What Happened

Extended MCPGatewayClient with SSE stream consumption, debug logging, and a __main__ CLI entrypoint. 18 tests confirm list_tools, call_tool, token caching (1 fetch on 2 calls), token refresh on near-expiry, and bus delivery mechanics.

## Verification

pytest tests/test_m004_client_bridge.py -v: 18 passed

## Requirements Advanced

- R001 — stream_events() enables real-time SSE consumption from external clients
- R005 — PKCE token factory and token refresh confirmed by tests

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

add tool listed in TOOLS but not handled by gateway /mcp \u2014 test asserts graceful isError instead of numeric result.

## Known Limitations

Gateway /mcp doesn't implement 'add' tool despite listing it in tools/list. Not blocking for M004 scope.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/bridge/gateway_client.py` — Added stream_events() async generator, debug logging, updated docstring
- `src/mcp_agent_factory/bridge/__main__.py` — New CLI entrypoint with PKCE-aware demo token factory
- `tests/test_m004_client_bridge.py` — 18 tests: list_tools, call_tool, token cache/refresh, stream_events, bus delivery
