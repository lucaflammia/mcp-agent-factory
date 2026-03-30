---
id: S04
parent: M004
milestone: M004
provides:
  - python -m mcp_agent_factory.gateway.run production entrypoint
  - mcp.json for Cursor/Claude Desktop IDE integration
requires:
  - slice: S03
    provides: MCPGatewayClient and OAuthMiddleware
affects:
  []
key_files:
  - src/mcp_agent_factory/gateway/run.py
  - mcp.json
key_decisions:
  - Auth server on :8001, gateway on :8000 — separate process deployment model documented in mcp.json
patterns_established:
  - Separate auth server (:8001) and gateway (:8000) deployment model
  - mcp.json as the canonical external client config artifact
observability_surfaces:
  - 'MCP Gateway running on http://HOST:PORT' at INFO on startup
drill_down_paths:
  - .gsd/milestones/M004/slices/S04/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S04/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-30T06:55:52.426Z
blocker_discovered: false
---

# S04: Launch Script + mcp.json External Config

**Launch script, mcp.json, and docs finalized; full suite 198/198 green**

## What Happened

Created run.py (uvicorn entrypoint) and mcp.json (external client config). Full suite confirmed at 198 tests. KNOWLEDGE.md and PROJECT.md updated.

## Verification

pytest tests/ -q: 198 passed; import check + JSON validation pass

## Requirements Advanced

- R001 — mcp.json enables Cursor/Claude Desktop to connect to the gateway
- R002 — run.py provides production HTTP server entry point

## Requirements Validated

- R001 — mcp.json + gateway/run.py proven by import check; full 198-test suite green
- R002 — HTTP/SSE gateway with /sse/v1/events confirmed by test_m004_sse.py

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

mcp.json auth URLs point to localhost; production deployment requires real HTTPS endpoints and a deployed auth server.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/gateway/run.py` — uvicorn entrypoint, HOST/PORT/LOG_LEVEL/RELOAD from env
- `mcp.json` — External IDE config with full tool schema, PKCE auth config, endpoint map
- `.gsd/KNOWLEDGE.md` — 4 new M004 knowledge entries
- `.gsd/PROJECT.md` — Updated to reflect M004 completion, 198 tests
