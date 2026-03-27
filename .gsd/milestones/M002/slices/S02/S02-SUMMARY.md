---
id: S02
parent: M002
milestone: M002
provides:
  - FastAPI app (server_http.py) with POST /mcp + GET /health — full MCP JSON-RPC 2.0 over HTTP
  - MCPRequest/MCPResponse Pydantic models for HTTP transport
  - LLMAdapterFactory with ClaudeAdapter, OpenAIAdapter, GeminiAdapter
  - FastAPI TestClient fixture pattern for S03 auth tests
requires:
  - slice: S01
    provides: pytest-asyncio fixture patterns, TaskScheduler for optional S04 integration
affects:
  - S03
  - S04
key_files:
  - src/mcp_agent_factory/server_http.py
  - src/mcp_agent_factory/adapters.py
  - tests/test_server_http.py
  - tests/test_adapters.py
key_decisions:
  - PrivacyConfig.assert_no_egress() in lifespan startup (not per-request)
  - GeminiAdapter uses recursive _convert_schema to uppercase all type strings
  - FastAPI TestClient pattern established for S03 auth tests
patterns_established:
  - FastAPI TestClient (sync) for HTTP MCP dispatch tests — no uvicorn needed
  - Cross-adapter parametrized invariants for shared contract verification
  - Recursive schema conversion pattern (GeminiAdapter._convert_schema)
observability_surfaces:
  - JSON log line per HTTP request/response via logger.debug (direction, payload)
  - Adapter output count logged at DEBUG (event, provider, count)
drill_down_paths:
  - .gsd/milestones/M002/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S02/tasks/T02-SUMMARY.md
  - .gsd/milestones/M002/slices/S02/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-27T08:05:05.112Z
blocker_discovered: false
---

# S02: FastAPI HTTP MCP Server + LLM Adapters

**FastAPI HTTP MCP server with full JSON-RPC 2.0 lifecycle and Claude/OpenAI/Gemini adapter layer — proven by 34 passing tests.**

## What Happened

S02 delivered the FastAPI HTTP MCP server and LLM adapter layer in three tasks. T01 built server_http.py mirroring M001's STDIO dispatch logic over HTTP. T02 built adapters.py with recursive Gemini type conversion and a clean factory. T03 wrote 34 tests including cross-adapter parametrized invariants. FastAPI TestClient proved simpler than httpx.AsyncClient for these sync dispatch tests. All 34 pass in 2.33s.

## Verification

python -m pytest tests/test_server_http.py tests/test_adapters.py -v → 34 passed in 2.33s.

## Requirements Advanced

- R008 — FastAPI POST /mcp exposes MCP protocol over TCP/IP HTTP transport
- R009 — LLMAdapterFactory translates MCP tools to Claude/OpenAI/Gemini function-calling schemas

## Requirements Validated

- R008 — 11 HTTP MCP tests pass — initialize, tools/list, tools/call, error handling all verified over HTTP
- R009 — 23 adapter tests pass — Claude/OpenAI/Gemini schema shapes, required fields, name/description preservation, no mutation all verified

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

FastAPI TestClient (sync) used instead of httpx.AsyncClient — simpler for sync dispatch, no event loop management needed. initialized notification returns empty MCPResponse rather than 204 to satisfy TestClient JSON parsing.

## Known Limitations

LLM adapters produce schema-shaped payloads only — no live API calls. Auth middleware not yet wired (S03).

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/server_http.py` — FastAPI HTTP MCP server — POST /mcp (full JSON-RPC 2.0 lifecycle), GET /health, PrivacyConfig at startup
- `src/mcp_agent_factory/adapters.py` — LLMAdapterFactory with ClaudeAdapter, OpenAIAdapter, GeminiAdapter — schema translation only
- `tests/test_server_http.py` — 11 HTTP MCP server tests
- `tests/test_adapters.py` — 23 adapter tests including cross-adapter parametrized invariants
