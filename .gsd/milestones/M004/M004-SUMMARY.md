---
id: M004
title: "Production-Ready Client Connectivity"
status: complete
completed_at: 2026-03-30T06:56:45.890Z
key_decisions:
  - FastAPI Mount /sse renamed to /sse/legacy to prevent prefix-match interception of /sse/v1 routes
  - SSE generator tested directly (not via ASGITransport streaming) to avoid EventSourceResponse blocking
  - OAuthMiddleware 60s refresh threshold confirmed and tested
  - mcp.json separates auth server (:8001) from gateway (:8000) matching real deployment topology
key_files:
  - src/mcp_agent_factory/messaging/sse_v1_router.py
  - src/mcp_agent_factory/gateway/app.py
  - src/mcp_agent_factory/bridge/gateway_client.py
  - src/mcp_agent_factory/bridge/__main__.py
  - src/mcp_agent_factory/gateway/run.py
  - mcp.json
  - tests/test_m004_sse.py
  - tests/test_m004_auth_pkce.py
  - tests/test_m004_client_bridge.py
lessons_learned:
  - FastAPI Mount paths are prefix-matched and intercept all sub-paths — always use distinct non-overlapping prefixes when mixing Mount and include_router
  - ASGITransport + EventSourceResponse infinite generators deadlock in sync test mode — test SSE via direct generator introspection and bus-level assertions
  - pytest-asyncio is not installed by default — add to dev dependencies explicitly
  - fakeredis must be installed separately from redis — add both to test dependencies
---

# M004: Production-Ready Client Connectivity

**Secured HTTP/SSE Gateway with PKCE auth, SSE streaming, Python client bridge, and mcp.json IDE config — 198 tests green.**

## What Happened

M004 transitioned the MCP ecosystem from local STDIO to a secured HTTP/SSE Gateway ready for external client connectivity. Four slices delivered: (1) SSE /v1 endpoints with 'connected' event on subscription and bus-integrated message streaming; (2) PKCE S256 hardening with 10 tests proving the full auth code flow and 401/403 enforcement; (3) MCPGatewayClient extended with stream_events(), token caching/refresh, debug logging, and a CLI entrypoint; (4) gateway/run.py uvicorn launch script and mcp.json config for Cursor/Claude Desktop. Total test count grew from 161 to 198 (+37 new tests, 0 regressions).

## Success Criteria Results

✅ GET /sse/v1/events streams 'connected' event — test_sse_events_first_event_is_connected passes\n✅ POST /mcp without Bearer → 401 — confirmed by 3 independent tests across test_gateway.py and test_m004_auth_pkce.py\n✅ MCPGatewayClient calls tools remotely — list_tools and call_tool tested via ASGITransport\n✅ mcp.json at project root — valid JSON with full tool schema and PKCE auth config\n✅ 198 tests passing, 0 failures

## Definition of Done Results

- ✅ All new test files pass: test_m004_sse.py (9), test_m004_auth_pkce.py (10), test_m004_client_bridge.py (18) — 37 new tests\n- ✅ Full suite green: 198 passed, 0 failed\n- ✅ gateway/run.py imports cleanly and starts uvicorn on port 8000\n- ✅ mcp.json valid JSON at project root\n- ✅ KNOWLEDGE.md updated with 4 M004 lessons\n- ✅ PROJECT.md updated to reflect M004 completion

## Requirement Outcomes

R001 (External Connectivity): advanced — mcp.json + gateway/run.py + MCPGatewayClient prove external client connectivity. R002 (MCP over HTTP/SSE): advanced — /sse/v1/events confirmed by tests. R005 (Auth Enforcement): validated — 10 PKCE+401 tests confirm schema validation and token enforcement at gateway boundary.

## Deviations

Legacy SSE mount renamed from /sse to /sse/legacy to prevent FastAPI Mount prefix-match interference with /sse/v1 routes. SSE streaming async tests use direct generator/bus testing instead of ASGITransport streaming (avoids EventSourceResponse blocking). pytest-asyncio + fakeredis installed as missing dependencies.

## Follow-ups

Gateway /mcp handler lists 'add' tool but doesn't implement it (returns isError). Future milestone should route 'add' to the server_http handler. Auth server and gateway currently share an in-memory JWT key — production deployment needs JWKS endpoint or explicit key distribution between processes on :8001 and :8000.
