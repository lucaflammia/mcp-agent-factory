# Requirements

This file is the explicit capability and coverage contract for the project.

## Validated

### R001 — Core Orchestration Engine
- Class: core-capability
- Status: validated
- Description: The orchestrator manages and routes tasks between agents.
- Why it matters: Essential for multi-agent functionality.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: validated
- Notes: 12 lifecycle tests + 4 e2e routing tests pass.

### R002 — MCP Communication Protocol
- Class: core-capability
- Status: validated
- Description: Standardized client-server communication via JSON-RPC 2.0.
- Why it matters: Universal connection layer for agents.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: validated
- Notes: 12/12 pytest tests pass over live STDIO subprocess.

### R003 — ReAct Pattern Implementation
- Class: core-capability
- Status: validated
- Description: Agents follow the Perception-Reasoning-Action loop with tool discovery and execution.
- Why it matters: Enables adaptive agent behavior and dynamic tool usage.
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: none
- Validation: validated
- Notes: 11 ReAct tests pass — full cycle verified.

### R004 — Fargin Curriculum Integration
- Class: core-capability
- Status: validated
- Description: Agent behaviors demonstrably derived from Fargin Curriculum theory.
- Why it matters: Core theoretical foundation of the project.
- Source: research
- Primary owning slice: M001/S01
- Supporting slices: M002/S04, M003/S05
- Validation: validated
- Notes: docs/security_audit.md maps all controls to Fargin chapters.

### R005 — Schema Validation for Security
- Class: security
- Status: validated
- Description: All tool arguments validated against Pydantic v2 models at dispatch boundary.
- Why it matters: Prevents injection and ensures data integrity.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: validated
- Notes: 5 test cases prove isError=True on bad inputs.

### R006 — Privacy-First Design
- Class: privacy
- Status: validated
- Description: Architecture prioritizes on-device inference; egress guard at startup.
- Why it matters: Core requirement for secure enterprise environments.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: validated
- Notes: PrivacyConfig with assert_no_egress() proven by 3 tests.

### R007 — Async Task Scheduler
- Class: core-capability
- Status: validated
- Description: asyncio-native TaskScheduler with inbox, priority queue, retry logic, structured logging.
- Why it matters: Enables autonomous agent loops without blocking I/O.
- Source: user
- Primary owning slice: M002/S01
- Supporting slices: none
- Validation: validated
- Notes: 12 pytest-asyncio tests pass.

### R008 — FastAPI HTTP MCP Server
- Class: core-capability
- Status: validated
- Description: TCP/IP MCP server over HTTP (POST /mcp). Coexists with STDIO server.
- Why it matters: Networked transport for multi-host deployments.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: validated
- Notes: 11 HTTP MCP tests pass.

### R009 — LLM Function-Calling Adapter
- Class: core-capability
- Status: validated
- Description: Schema translation layer for Claude/OpenAI/Gemini function-calling formats.
- Why it matters: Universal adapter between MCP tools and LLM providers.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: validated
- Notes: 23 adapter tests pass, no live API calls.

### R010 — OAuth 2.1 Authorization Server with PKCE
- Class: compliance/security
- Status: validated
- Description: Full OAuth 2.1 Auth Server: PKCE S256, /authorize, /token, client registration.
- Why it matters: Course deliverable; proves full PKCE flow.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: validated
- Notes: Full PKCE flow proven by 8 auth tests.

### R011 — Confused Deputy Protection
- Class: compliance/security
- Status: validated
- Description: Tokens are audience-bound; wrong aud → HTTP 401.
- Why it matters: Prevents token replay across services.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: validated
- Notes: test_confused_deputy_wrong_aud_rejected passes.

### R012 — User-Bound Non-Deterministic Session IDs
- Class: compliance/security
- Status: validated
- Description: Session IDs in format user_id:secrets.token_urlsafe(32).
- Why it matters: Prevents session fixation and prediction.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: validated
- Notes: 10/10 unique session IDs verified.

### R013 — Security Audit Document
- Class: compliance/security
- Status: validated
- Description: docs/security_audit.md maps all controls to Fargin Curriculum.
- Why it matters: Primary course deliverable artifact.
- Source: user
- Primary owning slice: M002/S04
- Supporting slices: none
- Validation: validated
- Notes: 8 controls documented with module/function/test citations.

### R014 — Resource Server Token Validation
- Class: compliance/security
- Status: validated
- Description: FastAPI MCP server validates bearer tokens, enforces scopes, audience binding.
- Why it matters: Closes the security loop between issuance and enforcement.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: M002/S02
- Validation: validated
- Notes: test_protected_endpoint_no_token_returns_401, test_wrong_scope_rejected pass.

## Active

### R017 — Specialized Agent Pipeline (Analyst→Writer)
- Class: core-capability
- Status: active
- Description: AnalystAgent processes raw data and extracts metrics; WriterAgent receives structured data from Analyst and generates a report. Orchestrator manages state transitions and handoffs between agents.
- Why it matters: Proves the "divide and conquer" multi-agent collaboration pattern from the Fargin Curriculum.
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: none
- Validation: mapped
- Notes: Agents are Python classes (same interface as ReActAgent). Cross-agent state via Redis Session Manager.

### R018 — Redis Session Manager for Cross-Agent State
- Class: core-capability
- Status: active
- Description: A Redis-backed session store that persists structured data between agent steps (Analyst output → Writer input). Real redis client; fakeredis for tests.
- Why it matters: Makes cross-agent handoffs inspectable and durable rather than in-memory coupling.
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: M003/S03
- Validation: mapped
- Notes: Interface-compatible with real Redis; fakeredis used in all tests.

### R019 — MCP Context Primitive for Per-Tool Observability
- Class: quality-attribute
- Status: active
- Description: MCP Context primitive used within individual tool calls for logging, progress reporting, and tracing. Scoped to single-tool execution health, not cross-agent state.
- Why it matters: Provides structured observability at the MCP protocol boundary.
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: M003/S04
- Validation: mapped
- Notes: Context logs tool start/progress/completion. Not used for orchestrator-level state.

### R020 — Utility Function Economic Task Allocation
- Class: core-capability
- Status: active
- Description: Each agent has a utility function that scores tasks based on cost and expertise. The score determines task desirability — higher utility = stronger preference to execute.
- Why it matters: Implements the economic agent behavior from the Fargin Curriculum; deterministic, no LLM needed.
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: none
- Validation: mapped
- Notes: Utility = f(task_complexity, agent_expertise, execution_cost). Pure math, fully testable.

### R021 — Agent Auction / Bidding Mechanism
- Class: core-capability
- Status: active
- Description: Agents submit bids (utility scores) for available tasks. The Orchestrator runs the auction and allocates the task to the highest bidder.
- Why it matters: Proves market dynamics in multi-agent resource allocation.
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: none
- Validation: mapped
- Notes: Deterministic auction — no randomness. Tie-breaking by agent_id for stability.

### R022 — Asyncio Message Bus for Agent Routing
- Class: core-capability
- Status: active
- Description: An asyncio in-process message bus routes messages between agents by role/capability. Consistent with M002's TaskScheduler pattern. No external broker in M003.
- Why it matters: Decouples agent communication from direct method calls; enables parallel processing.
- Source: user
- Primary owning slice: M003/S03
- Supporting slices: none
- Validation: mapped
- Notes: External broker (Kafka/RabbitMQ) deferred to a future milestone.

### R023 — SSE Transport for Async Message Delivery
- Class: core-capability
- Status: active
- Description: Server-Sent Events endpoint on the API Gateway that streams agent messages to connected external clients in real time.
- Why it matters: Enables external clients (Cursor IDE) to observe agent activity without polling.
- Source: user
- Primary owning slice: M003/S03
- Supporting slices: M003/S04
- Validation: mapped
- Notes: sse_starlette already installed.

### R024 — MCP API Gateway
- Class: core-capability
- Status: active
- Description: A centralized MCP server that routes tools/call requests from external clients to the appropriate internal agent/tool, and exposes sampling/createMessage capability.
- Why it matters: Makes the entire multi-agent system accessible as a single MCP endpoint for Cursor IDE and other clients.
- Source: user
- Primary owning slice: M003/S04
- Supporting slices: none
- Validation: mapped
- Notes: New dedicated FastAPI app (not built on server_http_secured.py).

### R025 — sampling/createMessage Protocol Implementation
- Class: core-capability
- Status: active
- Description: The API Gateway implements the MCP sampling/createMessage capability, allowing agents to request LLM completions mid-task via the connected client.
- Why it matters: Enables recursive workflows where a tool can request a second LLM opinion before returning a result.
- Source: user
- Primary owning slice: M003/S04
- Supporting slices: none
- Validation: mapped
- Notes: Client response stubbed in tests. Real client (Cursor) exercises this in production.

### R026 — LangChain Bridge with OAuth Middleware
- Class: integration
- Status: active
- Description: langchain-mcp-adapters MultiServerMCPClient loads tools from the API Gateway. A custom security middleware layer injects OAuth 2.1 Bearer tokens (from M002 auth stack) into client requests.
- Why it matters: Proves MCP tools are accessible as LangChain tools in a secure, authenticated context — the full enterprise integration story.
- Source: user
- Primary owning slice: M003/S05
- Supporting slices: none
- Validation: mapped
- Notes: langchain-mcp-adapters 1.2.7 already installed. OAuth middleware is hand-rolled on top of the library.

## Deferred

### R015 — Live LLM API Calls
- Class: integration
- Status: deferred
- Description: Making live calls to Claude, GPT, or Gemini APIs from the adapter layer.
- Why it matters: Keeps tests deterministic; avoids secret management.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Schema translation only in M002/M003. Deferred to a future milestone.

### R016 — External Queue Infrastructure
- Class: operability
- Status: deferred
- Description: Kafka, RabbitMQ, or other external queue backends.
- Why it matters: Asyncio message bus proves the pattern; external broker is infrastructure.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Deferred from M002. Still deferred in M003. asyncio bus is sufficient.

## Out of Scope

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | validated | M001/S01 | none | validated |
| R002 | core-capability | validated | M001/S01 | none | validated |
| R003 | core-capability | validated | M001/S02 | none | validated |
| R004 | core-capability | validated | M001/S01 | M002/S04, M003/S05 | validated |
| R005 | security | validated | M001/S03 | none | validated |
| R006 | privacy | validated | M001/S03 | none | validated |
| R007 | core-capability | validated | M002/S01 | none | validated |
| R008 | core-capability | validated | M002/S02 | none | validated |
| R009 | core-capability | validated | M002/S02 | none | validated |
| R010 | compliance/security | validated | M002/S03 | none | validated |
| R011 | compliance/security | validated | M002/S03 | none | validated |
| R012 | compliance/security | validated | M002/S03 | none | validated |
| R013 | compliance/security | validated | M002/S04 | none | validated |
| R014 | compliance/security | validated | M002/S03 | M002/S02 | validated |
| R015 | integration | deferred | none | none | unmapped |
| R016 | operability | deferred | none | none | unmapped |
| R017 | core-capability | active | M003/S01 | none | mapped |
| R018 | core-capability | active | M003/S01 | M003/S03 | mapped |
| R019 | quality-attribute | active | M003/S01 | M003/S04 | mapped |
| R020 | core-capability | active | M003/S02 | none | mapped |
| R021 | core-capability | active | M003/S02 | none | mapped |
| R022 | core-capability | active | M003/S03 | none | mapped |
| R023 | core-capability | active | M003/S03 | M003/S04 | mapped |
| R024 | core-capability | active | M003/S04 | none | mapped |
| R025 | core-capability | active | M003/S04 | none | mapped |
| R026 | integration | active | M003/S05 | none | mapped |

## Coverage Summary

- Active requirements: 10 (R017–R026)
- Mapped to slices: 10
- Validated: 14 (R001–R014)
- Unmapped active requirements: 0
