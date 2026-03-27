---
id: M002
title: "Autonomous Orchestrator & Production Security"
status: complete
completed_at: 2026-03-27T08:14:03.820Z
key_decisions:
  - STDIO server coexists with FastAPI HTTP server — STDIO stays as M001 regression baseline
  - Full OAuth 2.1 Auth Server (two separate FastAPI apps: Auth Server + Resource Server) — clean boundary between token issuance and enforcement
  - Schema translation only for LLM adapters — no live API calls; tested with fixture snapshots
  - asyncio.Queue inbox for TaskScheduler — external queue infrastructure deferred
  - make_verify_token factory for per-endpoint scope requirements
  - Confused deputy: aud mismatch → HTTP 401 (identity problem, not authorization)
  - autouse shared_key fixture with per-test store cleanup for auth integration tests
  - One-time codes deleted before token issuance to prevent TOCTOU
key_files:
  - src/mcp_agent_factory/scheduler.py
  - src/mcp_agent_factory/server_http.py
  - src/mcp_agent_factory/server_http_secured.py
  - src/mcp_agent_factory/adapters.py
  - src/mcp_agent_factory/auth/__init__.py
  - src/mcp_agent_factory/auth/server.py
  - src/mcp_agent_factory/auth/resource.py
  - src/mcp_agent_factory/auth/session.py
  - tests/test_scheduler.py
  - tests/test_server_http.py
  - tests/test_adapters.py
  - tests/test_auth.py
  - tests/test_integration.py
  - docs/security_audit.md
lessons_learned:
  - Direct _dispatch loop is more reliable than asyncio.wait_for for retry testing — avoids timing sensitivity without sacrificing coverage
  - autouse fixtures that clear in-memory stores after each test are essential for stateful auth components — without cleanup, test ordering matters
  - make_verify_token factory pattern is cleaner than a single shared dependency when different endpoints need different required scopes
  - FastAPI lifespan is the right place for startup validation (PrivacyConfig.assert_no_egress, JWT key generation) — not per-request
  - Authlib OctKey + jwt.encode/decode works cleanly for symmetric JWT; switch to RS256 + JWKS before multi-service production deployment
  - Reusing _dispatch and lifespan from server_http.py in server_http_secured.py avoids duplication and ensures both servers stay in sync
---

# M002: Autonomous Orchestrator & Production Security

**Async TaskScheduler, FastAPI HTTP MCP server with LLM adapters, and full OAuth 2.1 + PKCE authorization stack — proven by 100 passing tests and mapped to Fargin Curriculum in docs/security_audit.md.**

## What Happened

M002 was executed across four slices, all clean and sequential.

S01 built the asyncio-native TaskScheduler: SchedulerState enum, TaskItem Pydantic v2 model, and TaskScheduler with a max-priority heapq (negated int + tie-breaker counter), async run loop, and structured JSON log per state transition. Retry logic re-enqueues failed tasks through the inbox so they participate in global priority ordering. 12 pytest-asyncio tests established the async fixture patterns for the rest of the milestone.

S02 delivered the FastAPI HTTP MCP server and LLM adapter layer. server_http.py mirrors M001's STDIO dispatch logic over HTTP with PrivacyConfig.assert_no_egress() wired at startup. adapters.py provides ClaudeAdapter, OpenAIAdapter, and GeminiAdapter — GeminiAdapter uses a recursive _convert_schema to uppercase all JSON Schema type strings. LLMAdapterFactory dispatches by provider name with case-insensitive lookup. 34 tests including cross-adapter parametrized invariants.

S03 built the full OAuth 2.1 security stack. auth/server.py implements PKCE S256 with _compute_s256, one-time authorization codes (deleted before token issuance), JWT issuance with aud=mcp-server and user-bound session_id claims. auth/resource.py provides the make_verify_token factory that enforces audience binding (confused deputy protection) and scope requirements per endpoint. auth/session.py generates user_id:token_urlsafe(32) session IDs. server_http_secured.py wraps the existing MCP endpoint with Depends(make_verify_token('tools:call')). The autouse shared_key fixture injects a fresh OctKey and clears in-memory stores per test. 20 tests prove every security property.

S04 wired the assembled stack and documented the security posture. 3 integration tests prove TaskScheduler dispatches through the auth-protected HTTP MCP server. docs/security_audit.md maps 8 controls to Fargin Curriculum chapters with module/function references and test citations. Full suite: 100/100 tests pass.

## Success Criteria Results

## Success Criteria Results

- **pytest tests/ -v passes in full** ✅ — 100 passed in 27.95s. M001's 31 tests unchanged.
- **Task pushed into asyncio.Queue dispatched with state transitions** ✅ — test_dispatch_success, test_scheduler_dispatches_to_http_mcp_server prove pending → running → completed.
- **OAuth PKCE flow end-to-end** ✅ — /authorize with code_challenge → /token with code_verifier → JWT with correct claims all proven.
- **Token with wrong audience rejected with HTTP 401** ✅ — test_confused_deputy_wrong_aud_rejected.
- **docs/security_audit.md maps controls to Fargin Curriculum** ✅ — 8 controls, Capitolo references, module/function, test evidence for each.

## Definition of Done Results

## Definition of Done Results

- **All 4 slices complete with summaries** ✅ — S01 (Scheduler), S02 (FastAPI + Adapters), S03 (OAuth + Resource Server), S04 (Audit + Integration) all complete with summaries and UAT scripts.
- **pytest tests/ -v passes in full** ✅ — 100/100 tests pass in 27.95s. M001's 31 tests continue passing alongside 69 new M002 tests.
- **TaskScheduler → FastAPI HTTP MCP server integration exercised** ✅ — test_scheduler_dispatches_to_http_mcp_server and test_scheduler_dispatches_to_secured_mcp_server in test_integration.py.
- **OAuth PKCE flow end-to-end** ✅ — test_token_exchange_returns_access_token + test_jwt_contains_correct_claims prove full /authorize → /token → JWT flow.
- **Confused deputy rejection verified** ✅ — test_confused_deputy_wrong_aud_rejected: aud='other-service' → HTTP 401.
- **docs/security_audit.md exists** ✅ — 8 controls mapped to Fargin Curriculum chapters with module/function references and test citations.
- **pyproject.toml unchanged** ✅ — FastAPI 0.135.2, uvicorn 0.40.0, authlib 1.6.6 were already installed; no new dependencies needed.

## Requirement Outcomes

## Requirement Outcomes

- **R007 (Async Task Scheduler)** — Active → Validated. TaskScheduler with asyncio.Queue, priority heap, retry logic; 12 tests pass.
- **R008 (FastAPI HTTP MCP Server)** — Active → Validated. Full MCP lifecycle over HTTP; 11 server tests pass.
- **R009 (LLM Function-Calling Adapter)** — Active → Validated. Claude/OpenAI/Gemini adapters with fixture tests; 23 tests pass.
- **R010 (OAuth 2.1 Auth Server with PKCE)** — Active → Validated. Full PKCE S256 flow, one-time codes, JWT issuance; test_token_exchange_returns_access_token, test_jwt_contains_correct_claims.
- **R011 (Confused Deputy Protection)** — Active → Validated. test_confused_deputy_wrong_aud_rejected: aud='other-service' → HTTP 401.
- **R012 (User-Bound Session IDs)** — Active → Validated. test_session_id_format, test_session_ids_are_unique (10/10 unique).
- **R013 (Security Audit Document)** — Active → Validated. docs/security_audit.md: 8 controls mapped to Fargin Curriculum with module/function references.
- **R014 (Resource Server Token Validation)** — Active → Validated. test_protected_endpoint_no_token_returns_401, test_wrong_scope_rejected, test_confused_deputy_wrong_aud_rejected.

## Deviations

FastAPI TestClient (sync) used instead of httpx.AsyncClient for HTTP MCP tests — simpler, no event loop overhead. make_verify_token factory pattern instead of single verify_token — cleaner per-endpoint scope requirements. test_dispatch_failure_retries simplified to direct _dispatch invocations to avoid asyncio.wait_for timing sensitivity.

## Follow-ups

Production hardening (see docs/security_audit.md): replace in-memory _clients/_codes stores with Redis; add HTTPS termination; switch to RS256 + JWKS endpoint for multi-service deployments; add token revocation; rate-limit /authorize and /token. Live LLM API calls (R015) deferred to a future milestone.
