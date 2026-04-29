# Requirements

This file is the explicit capability and coverage contract for the project.

## Validated

### R001 — Local PDF text extraction via MCP tool `file_context_extractor` using pypdf — processes PDF on-device and returns targeted page snippets
- Class: core-capability
- Status: validated
- Description: Local PDF text extraction via MCP tool `file_context_extractor` using pypdf — processes PDF on-device and returns targeted page snippets
- Why it matters: Raw PDF must never leave the local environment; on-device extraction is the privacy foundation for the whole analyst pipeline
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: file_context_extractor MCP tool added using pypdf; local-only extraction confirmed in M010-SUMMARY.md and pdf_tool.py

### R002 — AnalystAgent upgraded to full document analysis pipeline: invoke file_context_extractor → ContextPruner → PIIGate → UnifiedRouter
- Class: core-capability
- Status: validated
- Description: AnalystAgent upgraded to full document analysis pipeline: invoke file_context_extractor → ContextPruner → PIIGate → UnifiedRouter
- Why it matters: Demonstrates the full M001–M009 infrastructure stack through a concrete, business-relevant use case
- Source: user
- Primary owning slice: M010/S02
- Validation: M010/S02: AnalystAgent.analyze_document() implements extract→prune→scrub→route pipeline; 25 tests pass

### R003 — GeminiHandler for UnifiedRouter using HTTP-only Gemini REST API via httpx — mirrors AnthropicHandler interface
- Class: core-capability
- Status: validated
- Description: GeminiHandler for UnifiedRouter using HTTP-only Gemini REST API via httpx — mirrors AnthropicHandler interface
- Why it matters: Adds a second cloud provider to demonstrate real multi-provider routing without adding SDK dependencies
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: GeminiHandler implemented via httpx REST, no google-generativeai SDK; confirmed in router.py and M010-SUMMARY.md

### R004 — Per-request provider resolution: UnifiedRouter.route() reads LLM_PROVIDER env var on every call and builds handler list with first-wins ordering (anthropic/gemini/ollama)
- Class: core-capability
- Status: validated
- Description: Per-request provider resolution: UnifiedRouter.route() reads LLM_PROVIDER env var on every call and builds handler list with first-wins ordering (anthropic/gemini/ollama)
- Why it matters: Enables live provider switching without restart — the core "hot switch" demo capability
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: provider_factory() re-reads LLM_PROVIDER env per call; live switching requires no restart — confirmed in M010-SUMMARY.md lessons

### R005 — GeminiHandler logs an EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to Ollama
- Class: failure-visibility
- Status: validated
- Description: GeminiHandler logs an EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to Ollama
- Why it matters: Demonstrates self-healing infrastructure — the logs show the system tried Gemini, explained failure, and recovered automatically
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: GeminiHandler emits EventLog warning when GEMINI_API_KEY absent, falls back to Ollama; confirmed in M010-SUMMARY.md

### R006 — Demo script scripts/demo_analyst.py: three-phase structured terminal output (extraction logs, KPI/risk analysis, provider metadata footer) plus live provider switch mid-session
- Class: primary-user-loop
- Status: validated
- Description: Demo script scripts/demo_analyst.py: three-phase structured terminal output (extraction logs, KPI/risk analysis, provider metadata footer) plus live provider switch mid-session
- Why it matters: Primary stakeholder proof — if the demo script runs end-to-end with a real PDF and shows a provider switch, the milestone claim is proven
- Source: user
- Primary owning slice: M010/S03
- Validation: M010/S03: demo_analyst.py ships with three-phase terminal output and live provider switch; real PDF sample at data/samples/finance_q3_2024.pdf

### R007 — Local PDF text extraction via file_context_extractor MCP tool using pypdf; raw PDF never leaves the device
- Class: core-capability
- Status: validated
- Description: Local PDF text extraction via file_context_extractor MCP tool using pypdf; raw PDF never leaves the device
- Why it matters: Privacy-first document ingestion; proves the system can handle real corporate document formats before LLM routing
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: file_context_extractor uses pypdf, local-only; raw PDF never sent to network — privacy-first confirmed in M010-SUMMARY.md

### R008 — AnalystAgent upgraded to full document analysis pipeline: extract via MCP tool → prune via ContextPruner → scrub via PIIGate → route via UnifiedRouter
- Class: primary-user-loop
- Status: validated
- Description: AnalystAgent upgraded to full document analysis pipeline: extract via MCP tool → prune via ContextPruner → scrub via PIIGate → route via UnifiedRouter
- Why it matters: Wires all M009 infrastructure through a real user-visible use case; proves the production claim end-to-end
- Source: user
- Primary owning slice: M010/S02
- Validation: M010/S02: analyze_document() pipeline wires extract→prune→scrub→route using DocumentAnalysisTask/Result; full suite 348 passed

### R009 — GeminiHandler for UnifiedRouter using HTTP-only httpx REST calls, mirroring AnthropicHandler structure; no google-generativeai SDK dependency
- Class: integration
- Status: validated
- Description: GeminiHandler for UnifiedRouter using HTTP-only httpx REST calls, mirroring AnthropicHandler structure; no google-generativeai SDK dependency
- Why it matters: Adds a third LLM provider to the routing chain; validates the handler abstraction is extensible
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: GeminiHandler uses httpx only, mirrors AnthropicHandler; no SDK dependency added to pyproject.toml

### R010 — Per-request provider resolution via LLM_PROVIDER env var with first-wins ordering; no restart required to switch providers
- Class: core-capability
- Status: validated
- Description: Per-request provider resolution via LLM_PROVIDER env var with first-wins ordering; no restart required to switch providers
- Why it matters: Live provider switching is the headline demo feature; proves the system is operationally flexible
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: provider_factory() reads LLM_PROVIDER on every route() call; first-wins ordering confirmed in router.py

### R011 — GeminiHandler logs EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to next handler
- Class: observability
- Status: validated
- Description: GeminiHandler logs EventLog warning before raising ProviderError when GEMINI_API_KEY is absent, then falls back to next handler
- Why it matters: Makes self-healing behavior observable; demonstrates the EventLog infrastructure is wired through real failure paths
- Source: user
- Primary owning slice: M010/S01
- Validation: M010/S01: GeminiHandler.complete() logs EventLog warning on missing key before raising ProviderError; fallback chain picks up Ollama

### R012 — Demo script (scripts/demo_analyst.py) with three-phase structured terminal output and live provider switch; acts as the milestone integration test
- Class: primary-user-loop
- Status: validated
- Description: Demo script (scripts/demo_analyst.py) with three-phase structured terminal output and live provider switch; acts as the milestone integration test
- Why it matters: Stakeholder-facing proof of the production claim; Phase 1 (extraction), Phase 2 (analysis), Phase 3 (provider metadata footer) make the pipeline tangible
- Source: user
- Primary owning slice: M010/S03
- Supporting slices: M010/S01, M010/S02
- Validation: M010/S03: demo_analyst.py delivers Phase 1 (extraction), Phase 2 (analysis), Phase 3 (provider metadata footer) with live switch mid-session

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | validated | M010/S01 | none | M010/S01: file_context_extractor MCP tool added using pypdf; local-only extraction confirmed in M010-SUMMARY.md and pdf_tool.py |
| R002 | core-capability | validated | M010/S02 | none | M010/S02: AnalystAgent.analyze_document() implements extract→prune→scrub→route pipeline; 25 tests pass |
| R003 | core-capability | validated | M010/S01 | none | M010/S01: GeminiHandler implemented via httpx REST, no google-generativeai SDK; confirmed in router.py and M010-SUMMARY.md |
| R004 | core-capability | validated | M010/S01 | none | M010/S01: provider_factory() re-reads LLM_PROVIDER env per call; live switching requires no restart — confirmed in M010-SUMMARY.md lessons |
| R005 | failure-visibility | validated | M010/S01 | none | M010/S01: GeminiHandler emits EventLog warning when GEMINI_API_KEY absent, falls back to Ollama; confirmed in M010-SUMMARY.md |
| R006 | primary-user-loop | validated | M010/S03 | none | M010/S03: demo_analyst.py ships with three-phase terminal output and live provider switch; real PDF sample at data/samples/finance_q3_2024.pdf |
| R007 | core-capability | validated | M010/S01 | none | M010/S01: file_context_extractor uses pypdf, local-only; raw PDF never sent to network — privacy-first confirmed in M010-SUMMARY.md |
| R008 | primary-user-loop | validated | M010/S02 | none | M010/S02: analyze_document() pipeline wires extract→prune→scrub→route using DocumentAnalysisTask/Result; full suite 348 passed |
| R009 | integration | validated | M010/S01 | none | M010/S01: GeminiHandler uses httpx only, mirrors AnthropicHandler; no SDK dependency added to pyproject.toml |
| R010 | core-capability | validated | M010/S01 | none | M010/S01: provider_factory() reads LLM_PROVIDER on every route() call; first-wins ordering confirmed in router.py |
| R011 | observability | validated | M010/S01 | none | M010/S01: GeminiHandler.complete() logs EventLog warning on missing key before raising ProviderError; fallback chain picks up Ollama |
| R012 | primary-user-loop | validated | M010/S03 | M010/S01, M010/S02 | M010/S03: demo_analyst.py delivers Phase 1 (extraction), Phase 2 (analysis), Phase 3 (provider metadata footer) with live switch mid-session |

## Coverage Summary

- Active requirements: 0
- Mapped to slices: 0
- Validated: 12 (R001, R002, R003, R004, R005, R006, R007, R008, R009, R010, R011, R012)
- Unmapped active requirements: 0
