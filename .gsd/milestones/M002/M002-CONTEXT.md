# M002: Autonomous Orchestrator & Production Security

**Gathered:** 2026-03-27
**Status:** Ready for planning

## Project Description

An industrial-grade Multi-Agent Orchestrator using the Model Context Protocol (MCP) as its universal connection layer. M002 evolves M001's synchronous STDIO prototype into a production-grade async system with three major new subsystems: an asyncio-native TaskScheduler, a FastAPI HTTP MCP server with LLM adapters, and a full OAuth 2.1 + PKCE authorization stack.

## Why This Milestone

M001 proved the MCP protocol and ReAct loop work. M002 proves they can run autonomously at network scale, protected by production-grade security. This directly applies the Fargin Curriculum's async architecture chapter (asyncio as structural requirement, not optimization) and security chapter (OAuth 2.1, PKCE, confused deputy protection, session integrity).

## User-Visible Outcome

### When this milestone is complete, the user can:

- Start the async TaskScheduler, push tasks into its `asyncio.Queue` inbox, and observe them dispatched through the priority queue with retry logic and structured log output.
- Start the FastAPI MCP server over HTTP and exercise the full MCP lifecycle (initialize → tools/list → tools/call) via HTTP POST — not subprocess STDIO.
- Request an authorization code from `/authorize` with a PKCE code_challenge, exchange it at `/token` for a bearer token, and use that token to call a protected MCP endpoint.
- Attempt to use a token issued for one audience against a different resource and observe it rejected (confused deputy protection).

### Entry point / environment

- Entry point: `pytest tests/ -v` for all automated verification; `uvicorn` for manual HTTP exploration.
- Environment: Local development environment (Python 3.11).
- Live dependencies involved: None — authlib JWT verification is self-contained; no external IdP required.

## Completion Class

- Contract complete means: All pytest tests pass including scheduler unit tests, HTTP MCP lifecycle tests, LLM adapter fixture tests, OAuth PKCE flow tests, scope enforcement tests, confused deputy rejection tests.
- Integration complete means: TaskScheduler dispatches a task through the FastAPI HTTP MCP server (end-to-end async path). Auth layer protects FastAPI MCP endpoints — unauthenticated requests rejected, valid-scope tokens accepted.
- Operational complete means: N/A for this milestone — no daemon supervision or persistent service lifecycle required.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- `pytest tests/ -v` passes in full — M001's 31 tests continue passing (STDIO untouched); M002 adds scheduler, HTTP MCP, adapter, and auth tests.
- A task pushed into TaskScheduler's queue is dispatched to a tool handler and its result logged with structured state (pending → running → completed/failed).
- An HTTP client can complete the full OAuth PKCE flow (authorize → exchange → call protected endpoint) against the self-contained auth server.
- A token with wrong audience is rejected by the Resource Server middleware with HTTP 401.
- `docs/security_audit.md` exists and maps every implemented security control to the Fargin Curriculum benchmark section.

## Risks and Unknowns

- **asyncio + pytest integration:** `pytest-asyncio` is already in dev deps, but async fixture scoping with `asyncio_mode = "auto"` can produce subtle ordering bugs in scheduler tests. — *Why it matters:* Flaky async tests are worse than no tests — they erode trust in the suite.
- **authlib PKCE implementation details:** authlib's OAuth 2.1 server components are well-documented but have specific patterns for PKCE verifier storage between `/authorize` and `/token` requests. Needs careful reading before S03 planning. — *Why it matters:* Getting PKCE wrong silently (e.g. accepting plain method when S256 required) defeats the security guarantee.
- **Two-app architecture boundary:** Auth Server and MCP Resource Server are separate FastAPI apps. Test setup requires both to be running (or appropriately stubbed). Need a clean fixture strategy before S03. — *Why it matters:* If tests require two live servers, test startup time grows and fixture complexity increases.
- **LLM adapter schema accuracy:** Claude, GPT, and Gemini function-calling schemas differ in field names and nesting. Getting them wrong means adapters produce malformed payloads. — *Why it matters:* Adapters are only useful if they produce payloads that the real LLM APIs would accept.

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/server.py` — STDIO MCP server. **Do not modify** — M001 tests depend on it.
- `src/mcp_agent_factory/orchestrator.py` — MCPOrchestrator (sync). The async HTTP client for M002 is a new module, not a replacement.
- `src/mcp_agent_factory/react_loop.py` — ReActAgent (sync). TaskScheduler is a new module that can optionally wrap ReActAgent.
- `src/mcp_agent_factory/models.py` — EchoInput/EchoOutput/AddInput/AddOutput. Reuse in FastAPI server.
- `src/mcp_agent_factory/config/privacy.py` — PrivacyConfig + assert_no_egress(). Wire into OAuth egress path.
- `pyproject.toml` — FastAPI 0.135.2 and uvicorn 0.40.0 already installed. authlib 1.6.6 already installed with Starlette integration. python-jose NOT installed — use authlib.jose for JWT.
- `tests/conftest.py` — mcp_server fixture pattern. Follow same daemon-thread + queue approach for any subprocess fixtures in M002.

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R007 — Async Task Scheduler
- R008 — FastAPI HTTP MCP Server
- R009 — LLM Function-Calling Adapter
- R010 — OAuth 2.1 Authorization Server with PKCE
- R011 — Confused Deputy Protection
- R012 — User-Bound Non-Deterministic Session IDs
- R013 — Security Audit Document
- R014 — Resource Server Token Validation

## Scope

### In Scope

- `src/mcp_agent_factory/scheduler.py` — async TaskScheduler with asyncio.Queue inbox, priority queue, retry logic, structured state logging.
- `src/mcp_agent_factory/server_http.py` — FastAPI HTTP MCP server (separate from STDIO server).
- `src/mcp_agent_factory/adapters.py` — LLM function-calling adapters (Claude, GPT, Gemini) — schema translation only.
- `src/mcp_agent_factory/auth/` — OAuth 2.1 Auth Server (authlib-based) with PKCE, scopes, client registration.
- `src/mcp_agent_factory/auth/resource.py` — Resource Server middleware: bearer token validation, scope enforcement, audience binding.
- `docs/security_audit.md` — Fargin Curriculum security benchmark mapping.

### Out of Scope / Non-Goals

- Live LLM API calls (Claude/GPT/Gemini) — adapters produce schemas only.
- External queue backends (Redis, HTTP polling) for the scheduler.
- Modifying the STDIO server or any M001 module.
- Production deployment (TLS termination, systemd, Docker) — local dev only.

## Technical Constraints

- Python 3.11 throughout.
- authlib for all OAuth/JWT work — python-jose is not installed.
- `pytest-asyncio` with `asyncio_mode = "auto"` already configured in pyproject.toml.
- STDIO server (`server.py`) must not be modified — it is the M001 regression baseline.
- Two separate FastAPI apps: one Auth Server, one MCP Resource Server. Clean separation of token issuance and enforcement.

## Integration Points

- authlib 1.6.6 (Starlette integration confirmed) — OAuth 2.1 server and JWT validation.
- FastAPI 0.135.2 + uvicorn 0.40.0 — already installed, no new deps needed for HTTP server.
- PrivacyConfig.assert_no_egress() — wire into any outbound call path in the HTTP server.
- M001 ReActAgent — TaskScheduler can optionally wrap it; keep the interface clean.

## Open Questions

- Authlib PKCE verifier storage: in-memory dict (acceptable for tests) vs. a proper server-side store. — *Current thinking:* In-memory for M002; flag as "replace with Redis in production" in the security audit.
- Scheduler priority: simple integer priority (higher = runs first) vs. deadline-based scheduling. — *Current thinking:* Integer priority — simpler, fully testable, sufficient for the course deliverable.
