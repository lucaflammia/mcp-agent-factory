# M012: Live Demonstration — AI Agents at Work

**Gathered:** 2026-05-01
**Status:** Ready for planning

## Project Description

A polished, zero-touch live demonstration of the full MCP agent stack. All underlying components exist from prior milestones (M001–M011). M012 is the bridge between code completeness and presentational reliability — wiring the pieces into a scripted narrative that runs end-to-end in front of an audience without friction.

## Why This Milestone

The system is technically complete but not demo-ready. Three gaps block a credible presentation:
1. No `agents/analyze` gateway endpoint — the demo narrative requires autonomous agent delegation, not tool call semantics
2. Agent-internal pipeline is "dark" in Jaeger — spans stop at `tool.analyse_and_report`, hiding the Privacy-First RAG story
3. No scripted runner — manual curl commands and config errors are silent demo killers

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `./demo.sh` and watch all three demo phases execute without manual intervention
- See `Gateway → AnalystAgent → LibrarianAgent → VectorStore` in Jaeger at `:16686` with token counts at each phase
- Hit `agents/analyze` via curl and get a real financial analysis result
- See a `-32602` error message naming the missing key when `LLM_PROVIDER=openai` but `OPENAI_API_KEY` is unset
- Watch the provider switch: two sequential requests produce responses from different models, side-by-side in terminal output

### Entry point / environment

- Entry point: `./demo.sh` + Jaeger UI at `:16686`
- Environment: local dev via `docker compose up`
- Live dependencies: gateway (:8000), Jaeger (:16686), Redis, OTel collector — all in Compose

## Completion Class

- Contract complete means: `agents/analyze` returns correct response shape and error codes; contract test green
- Integration complete means: full span chain visible in Jaeger with token attributes; `demo.sh` runs end-to-end
- Operational complete means: `docker compose up` brings everything healthy; no manual config steps

## Final Integrated Acceptance

- `./demo.sh` Phase 1: `agents/analyze` returns analysis result from local PDF
- `./demo.sh` Phase 2: Jaeger shows 4-phase span chain with token counts
- `./demo.sh` Phase 3: second request (openai, no key) returns `-32602` with named key
- Contract test: validates response shape and both error codes

## Architectural Decisions

### `_agents_dispatch()` Sub-Router
**Decision:** `elif method.startswith("agents/")` in `_mcp_dispatch_inner()` delegates to new `_agents_dispatch()`
**Rationale:** Separates agent orchestration from tool execution; establishes pattern for future streaming/long-running agent methods
**Alternatives:** Inline elif for `agents/analyze` — simpler but no sub-router pattern

### OTel Span Granularity
**Decision:** 4 child spans under `mcp.agents/analyze`: `agent.pdf_extract`, `agent.prune`, `agent.pii_scrub`, `agent.llm_route` with token counts
**Rationale:** Token counts in Jaeger turn the trace into a cost-optimization story; proves local processing before LLM engagement
**Alternatives:** Single pipeline span — cheaper but loses per-phase cost visibility

### Error Code Convention
**Decision:** `-32602` for missing provider key; `-32603` for pipeline phase failures
**Rationale:** Distinguishes user config errors from system crashes — audible in trace and terminal
**Alternatives:** All as `-32603` — loses the user/system distinction

### Demo Auth Strategy
**Decision:** `MCP_DEV_MODE=1` — bypass OAuth
**Rationale:** Expired tokens kill demos; auth tested separately in existing test suite
**Alternatives:** Full auth flow — adds token expiry risk mid-presentation

### Provider Switch Fallback
**Decision:** Fail fast with `-32602` naming the missing key — no silent Ollama fallback
**Rationale:** Silent fallback obscures which model ran; honest failure makes the model-agnosticism story credible
**Alternatives:** Fall back to Ollama — appears resilient but muddies the narrative

## Error Handling Strategy

- Pipeline failures: `-32603` + phase-naming message (e.g. `"pdf_extract failed: file not found"`)
- Provider not configured: `-32602` + `"OPENAI_API_KEY not set for provider 'openai'"`
- All exceptions recorded to active OTel span before re-raising
- No retries — fail fast

## Risks and Unknowns

- `DocumentAnalysisResult` telemetry fields may not be consistently populated — verify before S02
- OTel propagation through agent internals may require dep additions (`opentelemetry-api` in agent modules)
- `finance_q3_2024.pdf` content may not produce meaningful output with Ollama — rehearsal needed

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/gateway/app.py` — `_mcp_dispatch_inner()` insertion point for `_agents_dispatch()` delegation
- `src/mcp_agent_factory/agents/analyst.py` — `AnalystAgent.analyze_document()` target method; `DocumentAnalysisResult` return type
- `src/mcp_agent_factory/gateway/telemetry.py` — OTel setup; existing `mcp.*` and `tool.*` spans
- `scripts/smoke_test.sh` — pattern to follow for `demo.sh`

## Relevant Requirements

- R013 — `agents/analyze` JSON-RPC method
- R014 — `_agents_dispatch()` sub-router
- R015 — Error codes -32602 / -32603
- R016 — OTel 4-phase spans with token counts
- R017 — `demo.sh` zero-touch execution
- R018 — Provider switch with fail-fast
- R019 — Contract test for dispatch
- R020 — Jaeger perfect trace

## Scope

### In Scope
- `agents/analyze` method + `_agents_dispatch()` sub-router
- OTel 4-phase spans with token counts across agent pipeline
- `demo.sh` covering all three demo phases
- Contract test (response shape + error codes)
- Provider switch with fail-fast on missing key
- `MCP_DEV_MODE=1` for demo auth bypass

### Out of Scope / Non-Goals
- Full OAuth auth flow in the demo
- Generalizing `_agents_dispatch()` beyond `analyze`
- Streaming or long-running agent patterns
- Changes to `tools/call` dispatch or existing tools
- Test coverage beyond single contract test

## Technical Constraints

- Tab indentation throughout all Python source
- `MCP_DEV_MODE=1` already implemented via `DEV_MODE` module flag
- `demo.sh` must work from a clean `docker compose up` state

## Integration Points

- MCP gateway (:8000) — adds `agents/analyze` method
- Jaeger (:16686) — consumes OTel spans from new agent instrumentation
- `data/samples/finance_q3_2024.pdf` — demo input file

## Acceptance Criteria

**S01:** `curl agents/analyze` returns real result; contract test green (-32602 / -32603 verified)
**S02:** Jaeger shows 4 child spans with token attributes; Gateway → VectorStore chain visible
**S03:** `./demo.sh` zero-touch; Phase 3 shows `-32602` on missing key; side-by-side provider output
