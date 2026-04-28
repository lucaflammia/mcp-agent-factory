# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — Local PDF text extraction via MCP tool `file_context_extractor` using pypdf — processes PDF on-device and returns targeted page snippets
- Class: core-capability
- Status: active
- Description: Local PDF text extraction via MCP tool `file_context_extractor` using pypdf — processes PDF on-device and returns targeted page snippets
- Why it matters: Raw PDF must never leave the local environment; on-device extraction is the privacy foundation for the whole analyst pipeline
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R002 — AnalystAgent upgraded to full document analysis pipeline: invoke file_context_extractor → ContextPruner → PIIGate → UnifiedRouter
- Class: core-capability
- Status: active
- Description: AnalystAgent upgraded to full document analysis pipeline: invoke file_context_extractor → ContextPruner → PIIGate → UnifiedRouter
- Why it matters: Demonstrates the full M001–M009 infrastructure stack through a concrete, business-relevant use case
- Source: user
- Primary owning slice: M010/S02
- Validation: unmapped

### R003 — GeminiHandler for UnifiedRouter using HTTP-only Gemini REST API via httpx — mirrors AnthropicHandler interface
- Class: core-capability
- Status: active
- Description: GeminiHandler for UnifiedRouter using HTTP-only Gemini REST API via httpx — mirrors AnthropicHandler interface
- Why it matters: Adds a second cloud provider to demonstrate real multi-provider routing without adding SDK dependencies
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R004 — Per-request provider resolution: UnifiedRouter.route() reads LLM_PROVIDER env var on every call and builds handler list with first-wins ordering (anthropic/gemini/ollama)
- Class: core-capability
- Status: active
- Description: Per-request provider resolution: UnifiedRouter.route() reads LLM_PROVIDER env var on every call and builds handler list with first-wins ordering (anthropic/gemini/ollama)
- Why it matters: Enables live provider switching without restart — the core "hot switch" demo capability
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R005 — GeminiHandler logs an EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to Ollama
- Class: failure-visibility
- Status: active
- Description: GeminiHandler logs an EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to Ollama
- Why it matters: Demonstrates self-healing infrastructure — the logs show the system tried Gemini, explained failure, and recovered automatically
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R006 — Demo script scripts/demo_analyst.py: three-phase structured terminal output (extraction logs, KPI/risk analysis, provider metadata footer) plus live provider switch mid-session
- Class: primary-user-loop
- Status: active
- Description: Demo script scripts/demo_analyst.py: three-phase structured terminal output (extraction logs, KPI/risk analysis, provider metadata footer) plus live provider switch mid-session
- Why it matters: Primary stakeholder proof — if the demo script runs end-to-end with a real PDF and shows a provider switch, the milestone claim is proven
- Source: user
- Primary owning slice: M010/S03
- Validation: unmapped

### R007 — Local PDF text extraction via file_context_extractor MCP tool using pypdf; raw PDF never leaves the device
- Class: core-capability
- Status: active
- Description: Local PDF text extraction via file_context_extractor MCP tool using pypdf; raw PDF never leaves the device
- Why it matters: Privacy-first document ingestion; proves the system can handle real corporate document formats before LLM routing
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R008 — AnalystAgent upgraded to full document analysis pipeline: extract via MCP tool → prune via ContextPruner → scrub via PIIGate → route via UnifiedRouter
- Class: primary-user-loop
- Status: active
- Description: AnalystAgent upgraded to full document analysis pipeline: extract via MCP tool → prune via ContextPruner → scrub via PIIGate → route via UnifiedRouter
- Why it matters: Wires all M009 infrastructure through a real user-visible use case; proves the production claim end-to-end
- Source: user
- Primary owning slice: M010/S02
- Validation: unmapped

### R009 — GeminiHandler for UnifiedRouter using HTTP-only httpx REST calls, mirroring AnthropicHandler structure; no google-generativeai SDK dependency
- Class: integration
- Status: active
- Description: GeminiHandler for UnifiedRouter using HTTP-only httpx REST calls, mirroring AnthropicHandler structure; no google-generativeai SDK dependency
- Why it matters: Adds a third LLM provider to the routing chain; validates the handler abstraction is extensible
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R010 — Per-request provider resolution via LLM_PROVIDER env var with first-wins ordering; no restart required to switch providers
- Class: core-capability
- Status: active
- Description: Per-request provider resolution via LLM_PROVIDER env var with first-wins ordering; no restart required to switch providers
- Why it matters: Live provider switching is the headline demo feature; proves the system is operationally flexible
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R011 — GeminiHandler logs EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to next handler
- Class: observability
- Status: active
- Description: GeminiHandler logs EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to next handler
- Why it matters: Makes self-healing behavior observable; demonstrates the EventLog infrastructure is wired through real failure paths
- Source: user
- Primary owning slice: M010/S01
- Validation: unmapped

### R012 — Demo script (scripts/demo_analyst.py) with three-phase structured terminal output and live provider switch; acts as the milestone integration test
- Class: primary-user-loop
- Status: active
- Description: Demo script (scripts/demo_analyst.py) with three-phase structured terminal output and live provider switch; acts as the milestone integration test
- Why it matters: Stakeholder-facing proof of the production claim; Phase 1 (extraction), Phase 2 (analysis), Phase 3 (provider metadata footer) make the pipeline tangible
- Source: user
- Primary owning slice: M010/S03
- Supporting slices: M010/S01, M010/S02
- Validation: unmapped

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M010/S01 | none | unmapped |
| R002 | core-capability | active | M010/S02 | none | unmapped |
| R003 | core-capability | active | M010/S01 | none | unmapped |
| R004 | core-capability | active | M010/S01 | none | unmapped |
| R005 | failure-visibility | active | M010/S01 | none | unmapped |
| R006 | primary-user-loop | active | M010/S03 | none | unmapped |
| R007 | core-capability | active | M010/S01 | none | unmapped |
| R008 | primary-user-loop | active | M010/S02 | none | unmapped |
| R009 | integration | active | M010/S01 | none | unmapped |
| R010 | core-capability | active | M010/S01 | none | unmapped |
| R011 | observability | active | M010/S01 | none | unmapped |
| R012 | primary-user-loop | active | M010/S03 | M010/S01, M010/S02 | unmapped |

## Coverage Summary

- Active requirements: 12
- Mapped to slices: 12
- Validated: 0
- Unmapped active requirements: 0
