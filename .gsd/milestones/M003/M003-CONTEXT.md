# M003: Multi-Agent Ecosystem & Distributed Context Management

**Gathered:** 2026-03-27
**Status:** Ready for planning

## Project Description

Evolve the MCP Agent Factory from a single-agent orchestrator (M001/M002) into a distributed multi-agent ecosystem. Three new capability pillars: (1) specialized role-based agent pipeline with economic task allocation, (2) async message bus with SSE transport and MCP API Gateway, (3) LangChain bridge with OAuth 2.1 security middleware.

## Why This Milestone

M001 proved the MCP protocol. M002 proved async execution and production security. M003 proves the system can coordinate *multiple specialized agents* economically, route messages asynchronously, expose itself to external clients, and integrate with the LangChain ecosystem — directly applying Fargin Curriculum chapters 4 (collaborative agents), 5 (external integrations), and 6 (optimization and deployment).

## User-Visible Outcome

### When this milestone is complete, the user can:

- Push a raw data task to the Orchestrator and observe it flow through AnalystAgent → WriterAgent, with Redis storing the structured handoff and MCP Context logging progress at each step.
- See agents bid for tasks using utility function scores and observe the Orchestrator's auction allocate the task to the highest bidder.
- Connect to the SSE endpoint and watch agent messages stream in real time.
- Send a `tools/call` to the MCP API Gateway from an external client (Cursor IDE or curl) and see it routed to the appropriate internal agent.
- Trigger a `sampling/createMessage` from a mid-task agent and observe the stub client return a simulated LLM completion.
- Load MCP gateway tools into a LangChain agent via `MultiServerMCPClient` with an OAuth 2.1 Bearer token injected by the security middleware.

### Entry point / environment

- Entry point: `pytest tests/ -v` for automated verification; `uvicorn` for manual HTTP/SSE exploration.
- Environment: Local development (Python 3.11). Redis required for integration tests (fakeredis for unit tests).
- Live dependencies involved: fakeredis (tests), sse_starlette, langchain-mcp-adapters (all already installed or available).

## Completion Class

- Contract complete means: All pytest tests pass — pipeline tests, economics tests, message bus tests, gateway tests, sampling tests, LangChain bridge tests.
- Integration complete means: Analyst→Writer pipeline produces structured output via Orchestrator with Redis handoff. API Gateway routes external tools/call. LangChain agent loads gateway tools with OAuth headers.
- Operational complete means: N/A — local dev only.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- `pytest tests/ -v` passes in full — M001+M002 100 tests unchanged; M003 tests added.
- Orchestrator coordinates Analyst→Writer pipeline end-to-end with Redis session handoff and MCP Context logging.
- Auction allocates tasks to the highest-utility agent deterministically.
- SSE endpoint streams at least one message to a test client.
- API Gateway routes an external `tools/call` to the correct internal handler.
- `sampling/createMessage` triggers a stub client LLM completion mid-task.
- LangChain `MultiServerMCPClient` loads gateway tools with OAuth Bearer token injected.

## Risks and Unknowns

- **Redis in tests:** fakeredis must faithfully simulate the real Redis interface for all session manager operations. Any gap between fakeredis and real Redis behavior produces false-passing tests. — *Why it matters:* Silent test failures would mean the Session Manager works in tests but not in production.
- **sampling/createMessage stub design:** The MCP sampling protocol requires the client to implement the handler. In tests we stub this — the stub must faithfully represent the protocol shape or the implementation will be wrong. — *Why it matters:* A poorly-shaped stub means the real Cursor integration fails at first use.
- **langchain-mcp-adapters + OAuth middleware interaction:** MultiServerMCPClient accepts custom headers but the exact injection point for Bearer tokens needs verification against 1.2.7 API. — *Why it matters:* Wrong injection point means OAuth is bypassed silently.
- **SSE + pytest:** Testing SSE streams with FastAPI TestClient requires specific patterns (httpx streaming). — *Why it matters:* Flawed SSE test means the endpoint works but the test never exercises real streaming.

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/react_loop.py` — ReActAgent: the interface pattern for AnalystAgent and WriterAgent (run(task) → result).
- `src/mcp_agent_factory/scheduler.py` — TaskScheduler: asyncio patterns, priority queue, structured logging. Message bus should follow same observability conventions.
- `src/mcp_agent_factory/server_http.py` — FastAPI MCP server pattern. API Gateway is a new app (not extending this) but uses same MCPRequest/MCPResponse models.
- `src/mcp_agent_factory/server_http_secured.py` — Auth middleware wiring pattern (Depends(make_verify_token(...))).
- `src/mcp_agent_factory/auth/server.py` — Token issuance. LangChain middleware gets tokens from here.
- `src/mcp_agent_factory/auth/resource.py` — make_verify_token factory. Reuse in API Gateway.
- `tests/test_auth.py` — autouse shared_key fixture + store cleanup pattern. Reuse for any auth-touching M003 tests.
- `langchain-mcp-adapters` 1.2.7 — MultiServerMCPClient with `streamable_http` transport and custom headers support.
- `sse_starlette` — already installed, used for SSE endpoint.
- `fakeredis` — needs to be installed for tests (`pip install fakeredis`).

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R017 — Specialized Agent Pipeline (Analyst→Writer)
- R018 — Redis Session Manager for Cross-Agent State
- R019 — MCP Context Primitive for Per-Tool Observability
- R020 — Utility Function Economic Task Allocation
- R021 — Agent Auction / Bidding Mechanism
- R022 — Asyncio Message Bus for Agent Routing
- R023 — SSE Transport for Async Message Delivery
- R024 — MCP API Gateway
- R025 — sampling/createMessage Protocol Implementation
- R026 — LangChain Bridge with OAuth Middleware

## Scope

### In Scope

- `src/mcp_agent_factory/agents/` — AnalystAgent, WriterAgent, MultiAgentOrchestrator
- `src/mcp_agent_factory/session/` — RedisSessionManager with fakeredis test support
- `src/mcp_agent_factory/economics/` — UtilityFunction, Auction, bidding logic
- `src/mcp_agent_factory/messaging/` — asyncio MessageBus, SSE router
- `src/mcp_agent_factory/gateway/` — MCP API Gateway FastAPI app, sampling handler
- `src/mcp_agent_factory/langchain_bridge/` — OAuth middleware, MultiServerMCPClient wrapper

### Out of Scope / Non-Goals

- External message brokers (Kafka, RabbitMQ) — asyncio bus only in M003
- Live LLM API calls — stub-based testing only
- Production Redis deployment — local/fakeredis only
- Modifying M001/M002 modules (server.py, orchestrator.py, react_loop.py, auth/)

## Technical Constraints

- Python 3.11 throughout.
- `fakeredis` must be installed for tests (`pip install fakeredis`).
- `langchain-mcp-adapters` 1.2.7 already installed — use `MultiServerMCPClient` with `streamable_http` transport.
- `sse_starlette` already installed — use `EventSourceResponse` for SSE.
- M001/M002 modules must not be modified — 100 existing tests are the regression baseline.
- MCP Context primitive: use the context object passed to tool handlers for logging/progress. Do not use it for cross-agent state.

## Integration Points

- Redis / fakeredis — Session Manager for cross-agent state handoffs
- M002 auth stack (`auth/server.py`, `auth/resource.py`) — token issuance + validation for API Gateway and LangChain middleware
- `langchain-mcp-adapters` MultiServerMCPClient — LangChain bridge
- `sse_starlette` EventSourceResponse — SSE transport
- MCP sampling protocol — `sampling/createMessage` in API Gateway

## Open Questions

- fakeredis async interface (`fakeredis.aioredis`) vs sync: verify which is needed for async session manager before S01 implementation.
- MultiServerMCPClient custom headers injection point in 1.2.7: verify `headers` param in server config dict before S05 implementation.
