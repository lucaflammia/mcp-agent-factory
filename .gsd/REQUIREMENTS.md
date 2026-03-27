# Requirements

This file is the explicit capability and coverage contract for the project.

Use it to track what is actively in scope, what has been validated by completed work, what is intentionally deferred, and what is explicitly out of scope.

Guidelines:
- Keep requirements capability-oriented, not a giant feature wishlist.
- Requirements should be atomic, testable, and stated in plain language.
- Every **Active** requirement should be mapped to a slice, deferred, blocked with reason, or moved out of scope.
- Each requirement should have one accountable primary owner and may have supporting slices.
- Research may suggest requirements, but research does not silently make them binding.
- Validation means the requirement was actually proven by completed work and verification, not just discussed.

## Validated

### R001 — Core Orchestration Engine
- Class: core-capability
- Status: validated
- Description: The orchestrator must manage and route tasks between agents.
- Why it matters: Essential for multi-agent functionality.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: validated
- Notes: 12 lifecycle tests + 4 e2e routing tests pass — MCPOrchestrator routes tool calls between client and server subprocess over STDIO.

### R002 — MCP Communication Protocol
- Class: core-capability
- Status: validated
- Description: Implement a standardized client-server communication layer using JSON-RPC 2.0 for agent interaction.
- Why it matters: Universal connection layer for agents.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: validated
- Notes: 12/12 pytest tests pass over live STDIO subprocess — initialize handshake, tools/list, tools/call all verified.

### R003 — ReAct Pattern Implementation
- Class: core-capability
- Status: validated
- Description: Agents must follow the Perception-Reasoning-Action loop, utilizing tool discovery and execution.
- Why it matters: Enables adaptive agent behavior and dynamic tool usage.
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: none
- Validation: validated
- Notes: 11 ReAct tests pass — ReActAgent implements full Perception→Reasoning→Action cycle with list_tools + call_tool, step trace verified.

### R004 — Fargin Curriculum Integration
- Class: core-capability
- Status: validated
- Description: Agent behaviors and configurations must be demonstrably derived from the Fargin Curriculum theory.
- Why it matters: The core theoretical foundation of the project.
- Source: research
- Primary owning slice: M001/S01
- Supporting slices: M002/S04
- Validation: validated
- Notes: Server/orchestrator/ReActAgent maps to Fargin Perception→Reasoning→Action theory. M002/S04 extends with security audit mapping.

### R005 — Schema Validation for Security
- Class: security
- Status: validated
- Description: All tool arguments and messages must be validated against defined schemas (Pydantic v2).
- Why it matters: Prevents vulnerabilities and ensures data integrity.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: validated
- Notes: Pydantic v2 model_validate in server dispatch; 5 test cases prove isError=True on bad inputs.

### R006 — Privacy-First Design
- Class: privacy
- Status: validated
- Description: The architecture must prioritize on-device inference and minimize data egress for sensitive workloads.
- Why it matters: Core requirement for secure enterprise environments.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: validated
- Notes: PrivacyConfig defaults local_only=True/allow_egress=False; assert_no_egress() raises RuntimeError on allow_egress=True; 3 tests prove both branches.

## Active

### R007 — Async Task Scheduler
- Class: core-capability
- Status: active
- Description: An asyncio-based stateful TaskScheduler manages the agent lifecycle: inbox (asyncio.Queue), priority queue, tool handler dispatch, fail_task retry logic, and structured state logging.
- Why it matters: Enables autonomous agent loops without blocking I/O — the Fargin Curriculum's async chapter identifies this as structural, not optional, for production agents.
- Source: user
- Primary owning slice: M002/S01
- Supporting slices: none
- Validation: mapped
- Notes: Inbox via asyncio.Queue (in-process). External queue infrastructure (Redis/HTTP) deferred to a future milestone.

### R008 — FastAPI HTTP MCP Server
- Class: core-capability
- Status: active
- Description: A TCP/IP MCP server implemented with FastAPI that exposes the full MCP protocol (initialize → tools/list → tools/call) over HTTP. Coexists with the STDIO server; M001 tests remain unaffected.
- Why it matters: Moves beyond subprocess-only architecture to a real networked transport ready for multi-host deployments.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: mapped
- Notes: Async end-to-end. STDIO server stays untouched.

### R009 — LLM Function-Calling Adapter
- Class: core-capability
- Status: active
- Description: An abstraction layer that translates MCP tool descriptors into the native function-calling schemas for Claude, GPT, and Gemini.
- Why it matters: Enables the HTTP MCP server to serve as a universal adapter between MCP tools and any major LLM provider.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: mapped
- Notes: Schema translation only — produces correctly-shaped payloads tested with fixtures. No live API calls required.

### R010 — OAuth 2.1 Authorization Server with PKCE
- Class: compliance/security
- Status: active
- Description: A full OAuth 2.1 Authorization Server implementing /authorize, /token, client registration, PKCE flow, and granular scope definitions.
- Why it matters: Non-negotiable security requirement from the Fargin Curriculum; proves the full authorization code + PKCE flow is correctly implemented, not just token validation.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: mapped
- Notes: Self-contained, testable without external IdP. Built on authlib (already installed, Starlette integration confirmed).

### R011 — Confused Deputy Protection
- Class: compliance/security
- Status: active
- Description: Tokens must be audience-bound — MCP Resource Servers only accept tokens explicitly issued for their scope/audience. Requests bearing tokens intended for other services must be rejected.
- Why it matters: Without audience binding, a token stolen from one service can be replayed against another — the confused deputy vulnerability.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: mapped
- Notes: Enforced at the Resource Server middleware layer via `aud` claim validation.

### R012 — User-Bound Non-Deterministic Session IDs
- Class: compliance/security
- Status: active
- Description: Session identifiers must be non-deterministic, user-bound (format: user_id:session_id where session_id is a cryptographic random), and validated on every request.
- Why it matters: Prevents session fixation and session prediction attacks.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: mapped
- Notes: session_id component generated via secrets.token_urlsafe or uuid4.

### R013 — Security Audit Document
- Class: compliance/security
- Status: active
- Description: A written audit document (docs/security_audit.md) mapping every implemented security control to the corresponding Fargin Curriculum benchmark.
- Why it matters: The course's primary deliverable artifact — demonstrates that the implementation is Theory-to-Action, not just working code.
- Source: user
- Primary owning slice: M002/S04
- Supporting slices: none
- Validation: mapped
- Notes: Must reference actual code paths (module, function) for each mapped control.

### R014 — Resource Server Token Validation
- Class: compliance/security
- Status: active
- Description: The FastAPI MCP server operates as an OAuth 2.1 Resource Server — validates bearer tokens, enforces scopes, and rejects tokens with wrong audience.
- Why it matters: Closes the security loop: the Auth Server issues, the Resource Server enforces.
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: M002/S02
- Validation: mapped
- Notes: Separate FastAPI app from the Auth Server — clean boundary between issuance and enforcement.

## Deferred

## Out of Scope

### R015 — Live LLM API Calls
- Class: integration
- Status: out-of-scope
- Description: Making live calls to Claude, GPT, or Gemini APIs from the adapter layer.
- Why it matters: Keeps tests deterministic, avoids secret management, defers external latency.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Schema translation only in M002. Live API integration deferred to a future milestone if needed.

### R016 — External Queue Infrastructure
- Class: operability
- Status: out-of-scope
- Description: Redis, HTTP polling, or other external queue backends for the TaskScheduler inbox.
- Why it matters: Keeps M002 self-contained; asyncio.Queue is sufficient to prove the scheduler architecture.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Deferred to a future milestone.

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | validated | M001/S01 | none | validated |
| R002 | core-capability | validated | M001/S01 | none | validated |
| R003 | core-capability | validated | M001/S02 | none | validated |
| R004 | core-capability | validated | M001/S01 | M002/S04 | validated |
| R005 | security | validated | M001/S03 | none | validated |
| R006 | privacy | validated | M001/S03 | none | validated |
| R007 | core-capability | active | M002/S01 | none | mapped |
| R008 | core-capability | active | M002/S02 | none | mapped |
| R009 | core-capability | active | M002/S02 | none | mapped |
| R010 | compliance/security | active | M002/S03 | none | mapped |
| R011 | compliance/security | active | M002/S03 | none | mapped |
| R012 | compliance/security | active | M002/S03 | none | mapped |
| R013 | compliance/security | active | M002/S04 | none | mapped |
| R014 | compliance/security | active | M002/S03 | M002/S02 | mapped |
| R015 | integration | out-of-scope | none | none | n/a |
| R016 | operability | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 8 (R007–R014)
- Mapped to slices: 8
- Validated: 6 (R001–R006)
- Unmapped active requirements: 0
