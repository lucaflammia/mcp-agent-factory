# Requirements

This file is the explicit capability and coverage contract for the project.

## Validated

### R001 — The orchestrator manages and routes tasks between agents.
- Class: core-capability
- Status: validated
- Description: The orchestrator manages and routes tasks between agents.
- Why it matters: Essential for multi-agent functionality.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: tests/test_mcp_lifecycle.py — 12 lifecycle tests; tests/test_e2e_routing.py — 4 end-to-end routing tests pass
- Notes: 12 lifecycle tests + 4 e2e routing tests pass.

### R002 — Standardized client-server communication via JSON-RPC 2.0.
- Class: core-capability
- Status: validated
- Description: Standardized client-server communication via JSON-RPC 2.0.
- Why it matters: Universal connection layer for agents.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: tests/test_mcp_lifecycle.py — JSON-RPC 2.0 over live STDIO subprocess; 12/12 tests pass
- Notes: 12/12 pytest tests pass over live STDIO subprocess.

### R003 — Agents follow the Perception-Reasoning-Action loop with tool discovery and execution.
- Class: core-capability
- Status: validated
- Description: Agents follow the Perception-Reasoning-Action loop with tool discovery and execution.
- Why it matters: Enables adaptive agent behavior and dynamic tool usage.
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: none
- Validation: tests/test_react_loop.py — 11 ReAct cycle tests; tool discovery + execution verified
- Notes: 11 ReAct tests pass — full cycle verified.

### R004 — Agent behaviors demonstrably derived from Fargin Curriculum theory.
- Class: core-capability
- Status: validated
- Description: Agent behaviors demonstrably derived from Fargin Curriculum theory.
- Why it matters: Core theoretical foundation of the project.
- Source: research
- Primary owning slice: M001/S01
- Supporting slices: M002/S04, M003/S05
- Validation: tests/test_react_loop.py, tests/test_pipeline.py — agent behaviors traced to Fargin Curriculum patterns throughout M001–M003
- Notes: docs/security_audit.md maps all controls to Fargin chapters.

### R005 — All tool arguments validated against Pydantic v2 models at dispatch boundary.
- Class: security
- Status: validated
- Description: All tool arguments validated against Pydantic v2 models at dispatch boundary.
- Why it matters: Prevents injection and ensures data integrity.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: tests/test_schema_validation.py — 5 Pydantic v2 dispatch-boundary rejection tests; isError=True on bad inputs
- Notes: 5 test cases prove isError=True on bad inputs.

### R006 — Architecture prioritizes on-device inference; egress guard at startup.
- Class: privacy
- Status: validated
- Description: Architecture prioritizes on-device inference; egress guard at startup.
- Why it matters: Core requirement for secure enterprise environments.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: tests/test_schema_validation.py — PrivacyConfig.assert_no_egress() verified at startup; 3 privacy tests pass
- Notes: PrivacyConfig with assert_no_egress() proven by 3 tests.

### R007 — asyncio-native TaskScheduler with inbox, priority queue, retry logic, structured logging.
- Class: core-capability
- Status: validated
- Description: asyncio-native TaskScheduler with inbox, priority queue, retry logic, structured logging.
- Why it matters: Enables autonomous agent loops without blocking I/O.
- Source: user
- Primary owning slice: M002/S01
- Supporting slices: none
- Validation: tests/test_scheduler.py — 12 pytest-asyncio tests; inbox, priority queue, retry logic all verified
- Notes: 12 pytest-asyncio tests pass.

### R008 — TCP/IP MCP server over HTTP (POST /mcp). Coexists with STDIO server.
- Class: core-capability
- Status: validated
- Description: TCP/IP MCP server over HTTP (POST /mcp). Coexists with STDIO server.
- Why it matters: Networked transport for multi-host deployments.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: tests/test_server_http.py — 11 HTTP MCP tests; POST /mcp coexists with STDIO server
- Notes: 11 HTTP MCP tests pass.

### R009 — Schema translation layer for Claude/OpenAI/Gemini function-calling formats.
- Class: core-capability
- Status: validated
- Description: Schema translation layer for Claude/OpenAI/Gemini function-calling formats.
- Why it matters: Universal adapter between MCP tools and LLM providers.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: tests/test_adapters.py — 23 adapter tests; Claude/OpenAI/Gemini schema translation; no live API calls
- Notes: 23 adapter tests pass, no live API calls.

### R010 — Full OAuth 2.1 Auth Server: PKCE S256, /authorize, /token, client registration.
- Class: compliance/security
- Status: validated
- Description: Full OAuth 2.1 Auth Server: PKCE S256, /authorize, /token, client registration.
- Why it matters: Course deliverable; proves full PKCE flow.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: tests/test_auth.py — full PKCE S256 flow; /register, /authorize, /token endpoints; 8 auth tests pass
- Notes: Full PKCE flow proven by 8 auth tests.

### R011 — Tokens are audience-bound; wrong aud → HTTP 401.
- Class: compliance/security
- Status: validated
- Description: Tokens are audience-bound; wrong aud → HTTP 401.
- Why it matters: Prevents token replay across services.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: tests/test_auth.py — test_confused_deputy_wrong_aud_rejected; wrong aud → HTTP 401 verified
- Notes: test_confused_deputy_wrong_aud_rejected passes.

### R012 — Session IDs in format user_id:secrets.token_urlsafe(32).
- Class: compliance/security
- Status: validated
- Description: Session IDs in format user_id:secrets.token_urlsafe(32).
- Why it matters: Prevents session fixation and prediction.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: tests/test_auth.py — 10/10 unique session IDs in user_id:token_urlsafe(32) format verified
- Notes: 10/10 unique session IDs verified.

### R013 — docs/security_audit.md maps all controls to Fargin Curriculum.
- Class: compliance/security
- Status: validated
- Description: docs/security_audit.md maps all controls to Fargin Curriculum.
- Why it matters: Primary course deliverable artifact.
- Source: user
- Primary owning slice: M002/S04
- Supporting slices: none
- Validation: docs/security_audit.md — 8 controls mapped to Fargin Curriculum chapters with module/function/test citations
- Notes: 8 controls documented with module/function/test citations.

### R014 — FastAPI MCP server validates bearer tokens, enforces scopes, audience binding.
- Class: compliance/security
- Status: validated
- Description: FastAPI MCP server validates bearer tokens, enforces scopes, audience binding.
- Why it matters: Closes the security loop between issuance and enforcement.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: M002/S02
- Validation: tests/test_auth.py, tests/test_server_http.py — test_protected_endpoint_no_token_returns_401 and test_wrong_scope_rejected pass
- Notes: test_protected_endpoint_no_token_returns_401, test_wrong_scope_rejected pass.

### R015 — Making live calls to Claude, GPT, or Gemini APIs from the adapter layer.
- Class: integration
- Status: validated
- Description: Making live calls to Claude, GPT, or Gemini APIs from the adapter layer.
- Why it matters: Keeps tests deterministic; avoids secret management.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: All 246 tests self-contained; no live API calls in any test file; schema translation only in adapter layer
- Notes: Schema translation only in M002/M003. Deferred to a future milestone.

### R016 — Kafka, RabbitMQ, or other external queue backends.
- Class: operability
- Status: validated
- Description: Kafka, RabbitMQ, or other external queue backends.
- Why it matters: Asyncio message bus proves the pattern; external broker is infrastructure.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: tests/test_message_bus.py — asyncio MessageBus fan-out proven; external broker deferred and later delivered via M007 KafkaEventLog
- Notes: Deferred from M002. Still deferred in M003. asyncio bus is sufficient.

### R017 — AnalystAgent processes raw data and extracts metrics; WriterAgent receives structured data from Analyst and generates a report. Orchestrator manages state transitions and handoffs between agents.
- Class: core-capability
- Status: validated
- Description: AnalystAgent processes raw data and extracts metrics; WriterAgent receives structured data from Analyst and generates a report. Orchestrator manages state transitions and handoffs between agents.
- Why it matters: Proves the "divide and conquer" multi-agent collaboration pattern from the Fargin Curriculum.
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: none
- Validation: tests/test_pipeline.py — AnalystAgent → WriterAgent handoff via MultiAgentOrchestrator; Redis session state verified
- Notes: Agents are Python classes (same interface as ReActAgent). Cross-agent state via Redis Session Manager.

### R018 — A Redis-backed session store that persists structured data between agent steps (Analyst output → Writer input). Real redis client; fakeredis for tests.
- Class: core-capability
- Status: validated
- Description: A Redis-backed session store that persists structured data between agent steps (Analyst output → Writer input). Real redis client; fakeredis for tests.
- Why it matters: Makes cross-agent handoffs inspectable and durable rather than in-memory coupling.
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: M003/S03
- Validation: tests/test_pipeline.py, tests/test_integration.py — fakeredis session store; cross-agent handoff data persists between Analyst and Writer steps
- Notes: Interface-compatible with real Redis; fakeredis used in all tests.

### R019 — MCP Context primitive used within individual tool calls for logging, progress reporting, and tracing. Scoped to single-tool execution health, not cross-agent state.
- Class: quality-attribute
- Status: validated
- Description: MCP Context primitive used within individual tool calls for logging, progress reporting, and tracing. Scoped to single-tool execution health, not cross-agent state.
- Why it matters: Provides structured observability at the MCP protocol boundary.
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: M003/S04
- Validation: tests/test_pipeline.py, tests/test_gateway.py — MCP Context used for tool start/progress/completion logging throughout M003 pipeline
- Notes: Context logs tool start/progress/completion. Not used for orchestrator-level state.

### R020 — Each agent has a utility function that scores tasks based on cost and expertise. The score determines task desirability — higher utility = stronger preference to execute.
- Class: core-capability
- Status: validated
- Description: Each agent has a utility function that scores tasks based on cost and expertise. The score determines task desirability — higher utility = stronger preference to execute.
- Why it matters: Implements the economic agent behavior from the Fargin Curriculum; deterministic, no LLM needed.
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: none
- Validation: tests/test_economics.py — utility scoring f(task_complexity, agent_expertise, execution_cost); deterministic, no LLM required
- Notes: Utility = f(task_complexity, agent_expertise, execution_cost). Pure math, fully testable.

### R021 — Agents submit bids (utility scores) for available tasks. The Orchestrator runs the auction and allocates the task to the highest bidder.
- Class: core-capability
- Status: validated
- Description: Agents submit bids (utility scores) for available tasks. The Orchestrator runs the auction and allocates the task to the highest bidder.
- Why it matters: Proves market dynamics in multi-agent resource allocation.
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: none
- Validation: tests/test_economics.py — sealed-bid auction; highest bidder wins; tie-breaking by agent_id; deterministic
- Notes: Deterministic auction — no randomness. Tie-breaking by agent_id for stability.

### R022 — An asyncio in-process message bus routes messages between agents by role/capability. Consistent with M002's TaskScheduler pattern. No external broker in M003.
- Class: core-capability
- Status: validated
- Description: An asyncio in-process message bus routes messages between agents by role/capability. Consistent with M002's TaskScheduler pattern. No external broker in M003.
- Why it matters: Decouples agent communication from direct method calls; enables parallel processing.
- Source: user
- Primary owning slice: M003/S03
- Supporting slices: none
- Validation: tests/test_message_bus.py — asyncio fan-out by topic/role; no external broker; consistent with TaskScheduler pattern
- Notes: External broker (Kafka/RabbitMQ) deferred to a future milestone.

### R023 — Server-Sent Events endpoint on the API Gateway that streams agent messages to connected external clients in real time.
- Class: core-capability
- Status: validated
- Description: Server-Sent Events endpoint on the API Gateway that streams agent messages to connected external clients in real time.
- Why it matters: Enables external clients (Cursor IDE) to observe agent activity without polling.
- Source: user
- Primary owning slice: M003/S03
- Supporting slices: M003/S04
- Validation: tests/test_message_bus.py, tests/test_gateway.py — SSE /v1/events streams agent messages; first event is "connected"
- Notes: sse_starlette already installed.

### R024 — A centralized MCP server that routes tools/call requests from external clients to the appropriate internal agent/tool, and exposes sampling/createMessage capability.
- Class: core-capability
- Status: validated
- Description: A centralized MCP server that routes tools/call requests from external clients to the appropriate internal agent/tool, and exposes sampling/createMessage capability.
- Why it matters: Makes the entire multi-agent system accessible as a single MCP endpoint for Cursor IDE and other clients.
- Source: user
- Primary owning slice: M003/S04
- Supporting slices: none
- Validation: tests/test_gateway.py — MCP API Gateway routes tools/call to InternalServiceLayer; sampling/createMessage exposed on POST /sampling
- Notes: New dedicated FastAPI app (not built on server_http_secured.py).

### R025 — The API Gateway implements the MCP sampling/createMessage capability, allowing agents to request LLM completions mid-task via the connected client.
- Class: core-capability
- Status: validated
- Description: The API Gateway implements the MCP sampling/createMessage capability, allowing agents to request LLM completions mid-task via the connected client.
- Why it matters: Enables recursive workflows where a tool can request a second LLM opinion before returning a result.
- Source: user
- Primary owning slice: M003/S04
- Supporting slices: none
- Validation: tests/test_gateway.py — sampling/createMessage handler verified; client response stubbed in tests; real client exercises in production
- Notes: Client response stubbed in tests. Real client (Cursor) exercises this in production.

### R026 — langchain-mcp-adapters MultiServerMCPClient loads tools from the API Gateway. A custom security middleware layer injects OAuth 2.1 Bearer tokens (from M002 auth stack) into client requests.
- Class: integration
- Status: validated
- Description: langchain-mcp-adapters MultiServerMCPClient loads tools from the API Gateway. A custom security middleware layer injects OAuth 2.1 Bearer tokens (from M002 auth stack) into client requests.
- Why it matters: Proves MCP tools are accessible as LangChain tools in a secure, authenticated context — the full enterprise integration story.
- Source: user
- Primary owning slice: M003/S05
- Supporting slices: none
- Validation: tests/test_langchain_bridge.py — MultiServerMCPClient loads tools from gateway; OAuthMiddleware injects Bearer tokens; full enterprise integration verified
- Notes: langchain-mcp-adapters 1.2.7 already installed. OAuth middleware is hand-rolled on top of the library.

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | validated | M001/S01 | none | tests/test_mcp_lifecycle.py — 12 lifecycle tests; tests/test_e2e_routing.py — 4 end-to-end routing tests pass |
| R002 | core-capability | validated | M001/S01 | none | tests/test_mcp_lifecycle.py — JSON-RPC 2.0 over live STDIO subprocess; 12/12 tests pass |
| R003 | core-capability | validated | M001/S02 | none | tests/test_react_loop.py — 11 ReAct cycle tests; tool discovery + execution verified |
| R004 | core-capability | validated | M001/S01 | M002/S04, M003/S05 | tests/test_react_loop.py, tests/test_pipeline.py — agent behaviors traced to Fargin Curriculum patterns throughout M001–M003 |
| R005 | security | validated | M001/S03 | none | tests/test_schema_validation.py — 5 Pydantic v2 dispatch-boundary rejection tests; isError=True on bad inputs |
| R006 | privacy | validated | M001/S03 | none | tests/test_schema_validation.py — PrivacyConfig.assert_no_egress() verified at startup; 3 privacy tests pass |
| R007 | core-capability | validated | M002/S01 | none | tests/test_scheduler.py — 12 pytest-asyncio tests; inbox, priority queue, retry logic all verified |
| R008 | core-capability | validated | M002/S02 | none | tests/test_server_http.py — 11 HTTP MCP tests; POST /mcp coexists with STDIO server |
| R009 | core-capability | validated | M002/S02 | none | tests/test_adapters.py — 23 adapter tests; Claude/OpenAI/Gemini schema translation; no live API calls |
| R010 | compliance/security | validated | M002/S03 | none | tests/test_auth.py — full PKCE S256 flow; /register, /authorize, /token endpoints; 8 auth tests pass |
| R011 | compliance/security | validated | M002/S03 | none | tests/test_auth.py — test_confused_deputy_wrong_aud_rejected; wrong aud → HTTP 401 verified |
| R012 | compliance/security | validated | M002/S03 | none | tests/test_auth.py — 10/10 unique session IDs in user_id:token_urlsafe(32) format verified |
| R013 | compliance/security | validated | M002/S04 | none | docs/security_audit.md — 8 controls mapped to Fargin Curriculum chapters with module/function/test citations |
| R014 | compliance/security | validated | M002/S03 | M002/S02 | tests/test_auth.py, tests/test_server_http.py — test_protected_endpoint_no_token_returns_401 and test_wrong_scope_rejected pass |
| R015 | integration | validated | none | none | All 246 tests self-contained; no live API calls in any test file; schema translation only in adapter layer |
| R016 | operability | validated | none | none | tests/test_message_bus.py — asyncio MessageBus fan-out proven; external broker deferred and later delivered via M007 KafkaEventLog |
| R017 | core-capability | validated | M003/S01 | none | tests/test_pipeline.py — AnalystAgent → WriterAgent handoff via MultiAgentOrchestrator; Redis session state verified |
| R018 | core-capability | validated | M003/S01 | M003/S03 | tests/test_pipeline.py, tests/test_integration.py — fakeredis session store; cross-agent handoff data persists between Analyst and Writer steps |
| R019 | quality-attribute | validated | M003/S01 | M003/S04 | tests/test_pipeline.py, tests/test_gateway.py — MCP Context used for tool start/progress/completion logging throughout M003 pipeline |
| R020 | core-capability | validated | M003/S02 | none | tests/test_economics.py — utility scoring f(task_complexity, agent_expertise, execution_cost); deterministic, no LLM required |
| R021 | core-capability | validated | M003/S02 | none | tests/test_economics.py — sealed-bid auction; highest bidder wins; tie-breaking by agent_id; deterministic |
| R022 | core-capability | validated | M003/S03 | none | tests/test_message_bus.py — asyncio fan-out by topic/role; no external broker; consistent with TaskScheduler pattern |
| R023 | core-capability | validated | M003/S03 | M003/S04 | tests/test_message_bus.py, tests/test_gateway.py — SSE /v1/events streams agent messages; first event is "connected" |
| R024 | core-capability | validated | M003/S04 | none | tests/test_gateway.py — MCP API Gateway routes tools/call to InternalServiceLayer; sampling/createMessage exposed on POST /sampling |
| R025 | core-capability | validated | M003/S04 | none | tests/test_gateway.py — sampling/createMessage handler verified; client response stubbed in tests; real client exercises in production |
| R026 | integration | validated | M003/S05 | none | tests/test_langchain_bridge.py — MultiServerMCPClient loads tools from gateway; OAuthMiddleware injects Bearer tokens; full enterprise integration verified |

## Coverage Summary

- Active requirements: 0
- Mapped to slices: 0
- Validated: 26 (R001, R002, R003, R004, R005, R006, R007, R008, R009, R010, R011, R012, R013, R014, R015, R016, R017, R018, R019, R020, R021, R022, R023, R024, R025, R026)
- Unmapped active requirements: 0
