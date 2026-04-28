# M010: Production Analyst & Provider Switch

**Gathered:** 2026-04-28
**Status:** Ready for planning

## Project Description

Shift from infrastructure building to a concrete business application. The AnalystAgent is upgraded from its current numeric-stub to a real document analyst: it reads a PDF locally via an MCP tool, prunes irrelevant chunks through the existing ContextPruner, scrubs PII via PIIGate, then routes the pruned context to an LLM via UnifiedRouter. A live demo script shows the full pipeline and a seamless provider switch between Claude, Gemini, and Ollama without restarting anything.

## Why This Milestone

All infrastructure (UnifiedRouter, ContextPruner, PIIGate, ValidationGate, EventLog) was built across M001–M009 but never wired through a real user-visible use case. This milestone proves the system earns its "production" claim: a real PDF goes in, structured analysis comes out, and the provider can be swapped live.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `python scripts/demo_analyst.py` against a real PDF file on disk and see: Phase 1 (extraction logs with token reduction numbers), Phase 2 (KPIs and risk areas as a clean markdown list), Phase 3 (provider metadata footer with provider name, cost, status)
- Change `LLM_PROVIDER=gemini` (or `anthropic` / `ollama`) and re-run — the next request routes to the new provider without restarting; the demo script exercises this live switch automatically

### Entry point / environment

- Entry point: `python scripts/demo_analyst.py`
- Environment: local dev
- Live dependencies involved: Anthropic API (optional), Gemini REST API (optional), local Ollama (fallback)

## Completion Class

- Contract complete means: unit tests pass for GeminiHandler JSON mapping and factory routing logic; AnalystAgent tests updated to new pipeline interface
- Integration complete means: demo script runs end-to-end with a real PDF, produces structured output, switches provider mid-script
- Operational complete means: missing API key → EventLog warning logged + graceful Ollama fallback

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- `python scripts/demo_analyst.py` runs end-to-end with `data/samples/finance_q3_2024.pdf`, prints all three phases, and shows provider metadata
- After the first run, the script switches `LLM_PROVIDER` and re-runs — output shows the new provider in the metadata footer
- Existing 323-test suite stays green

## Architectural Decisions

### Per-Request Provider Resolution

**Decision:** `UnifiedRouter.route()` reads `os.getenv("LLM_PROVIDER")` on every call and builds the handler list dynamically (factory pattern) rather than using the fixed list passed at construction time.

**Rationale:** Handler constructors are cheap (no persistent connections). This is the simplest correct approach for live provider switching — no daemon, no file-watcher, no restart required.

**Alternatives Considered:**
- File-watcher / SIGHUP reload — more complex, requires a running server process; unnecessary given stateless handlers

### First-Wins Provider Ordering

**Decision:** `LLM_PROVIDER=anthropic` → `[AnthropicHandler, OllamaHandler]`; `gemini` → `[GeminiHandler, OllamaHandler]`; `ollama` → `[OllamaHandler]`. Ollama is always the universal fallback.

**Rationale:** Preserves the M009 fallback chain; cloud providers fail over to local gracefully. The demo can show the switch without sacrificing resilience.

**Alternatives Considered:**
- Exclusive routing (only one provider, no fallback) — cleaner demo readout but loses the "self-healing infrastructure" narrative

### GeminiHandler: HTTP-only via httpx

**Decision:** `GeminiHandler` calls the Gemini REST API directly via `httpx` (already a dependency), mirroring `AnthropicHandler` structure.

**Rationale:** Avoids adding `google-generativeai` SDK; smaller dependency footprint on the T480; consistent with existing handler patterns.

**Alternatives Considered:**
- `google-generativeai` SDK — heavier, potential version conflicts, unnecessary for the REST call pattern already established

### EventLog Warning Before ProviderError

**Decision:** When `GEMINI_API_KEY` is absent, `GeminiHandler.call()` logs a warning to `EventLog` before raising `ProviderError("gemini", detail="GEMINI_API_KEY not set")`.

**Rationale:** Makes the "self-healing" behavior observable in logs — the system tried Gemini, explained why it failed, and recovered. Demonstrates the observability infrastructure built in prior milestones earning its keep.

### PDF Extraction: pypdf, local only

**Decision:** New MCP tool `file_context_extractor` uses `pypdf` for local text extraction; returns targeted page snippets. Raw PDF never leaves the device.

**Rationale:** `pypdf` is pure Python, no system dependencies, fits the T480. The local extraction step before `ContextPruner` validates the "dirty data → clean LLM input" pipeline end-to-end.

## Error Handling Strategy

- PDF not found or unreadable → `AnalystAgent` returns an `AnalysisResult` with the exception message in `summary`
- All LLM providers fail → last `ProviderError` propagates to the demo script, which prints a red error line
- PII gate strips disallowed fields silently (existing behavior, unchanged)
- `GEMINI_API_KEY` missing → `GeminiHandler.call()` logs EventLog warning then raises `ProviderError`, falls back to next handler
- `ANTHROPIC_API_KEY` missing → same pattern (already exists in `AnthropicHandler`)

## Risks and Unknowns

- `pypdf` text extraction quality on complex PDFs — may produce garbled text for image-heavy or scan-based PDFs; acceptable for the demo with a clean sample PDF
- Gemini REST API response shape may differ from Anthropic in edge cases (streaming, error codes) — mitigated by unit tests against the mapping logic

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/agents/analyst.py` — current stub; to be upgraded
- `src/mcp_agent_factory/gateway/router.py` — `UnifiedRouter` with `AnthropicHandler` and `OllamaHandler`; factory logic goes here
- `src/mcp_agent_factory/gateway/pruner.py` — `ContextPruner` cosine similarity; already wired in query_knowledge_base
- `src/mcp_agent_factory/gateway/validation.py` — `PIIGate` / `ValidationGate`; to be used in analyst pipeline
- `src/mcp_agent_factory/streams/eventlog.py` — `EventLog` append; used for GeminiHandler warning

## Relevant Requirements

- R033 — UnifiedRouter with handler abstraction; validated by S01
- R034 — Automatic fallback from cloud to Ollama; validated by S01
- R035 — Gateway-level PII scrubbing; validated by S02
- R036 — Context pruning before LLM call; validated by S02
- R043 — Local PDF extraction via MCP tool; owned by S01
- R044 — AnalystAgent full document pipeline; owned by S02
- R045 — GeminiHandler HTTP-only; owned by S01
- R046 — Per-request provider resolution via LLM_PROVIDER; owned by S01
- R047 — EventLog warning before ProviderError; owned by S01
- R048 — Demo script three-phase output + live provider switch; owned by S03

## Scope

### In Scope

- `file_context_extractor` MCP tool (pypdf local extraction, returns page snippets)
- `GeminiHandler` (httpx, mirrors AnthropicHandler, EventLog warning on missing key)
- Per-request provider resolution factory in `UnifiedRouter.route()`
- First-wins handler ordering driven by `LLM_PROVIDER` env var
- `AnalystAgent` upgraded: extract → prune → scrub → route
- `data/samples/finance_q3_2024.pdf` sample document committed to repo
- `scripts/demo_analyst.py` three-phase structured output + live provider switch
- New unit tests: GeminiHandler mapping, factory routing logic
- Updated AnalystAgent tests (MCP tool call vs old dict stub)
- `pypdf` and `httpx` added to `pyproject.toml` dependencies

### Out of Scope / Non-Goals

- Streaming LLM responses
- Multi-document batch analysis
- Persistent analysis results / storage
- Gemini SDK (`google-generativeai`)
- Hot-reload via file-watcher or SIGHUP (per-request env-var read is sufficient)

## Technical Constraints

- `httpx` must be added as an explicit dependency (currently implied but not declared)
- `pypdf` must be added as a dependency
- All existing tests must stay green — no regressions

## Integration Points

- Anthropic API — existing `AnthropicHandler` unchanged; `LLM_PROVIDER=anthropic` puts it first
- Gemini REST API (`generativelanguage.googleapis.com`) — new `GeminiHandler` via httpx
- Local Ollama — existing `OllamaHandler` unchanged; universal fallback
- EventLog — `GeminiHandler` appends warning events

## Testing Requirements

- Unit: `GeminiHandler` JSON mapping (request format, response parsing, missing-key path)
- Unit: factory function — changing `LLM_PROVIDER` reorders the handler list correctly
- Updated: `AnalystAgent` tests reflect new MCP tool call interface
- Integration: demo script runs end-to-end (acts as the integration test)
- Regression: full `pytest tests/ -v` suite must stay green

## Acceptance Criteria

**S01 (LLM Provider Infrastructure):**
- `LLM_PROVIDER=gemini python -c "..."` returns a Gemini-shaped response
- Changing env var → Anthropic handler becomes primary
- `GEMINI_API_KEY` absent → EventLog warning logged + Ollama fallback succeeds
- Unit tests for handler factory and GeminiHandler mapping pass

**S02 (AnalystAgent Document Pipeline):**
- `AnalystAgent.run()` with a real PDF task: invokes `file_context_extractor`, runs ContextPruner, runs PIIGate, routes via UnifiedRouter
- Tests pass with a fixture PDF; old dict-stub tests removed/updated
- `pypdf` extraction produces non-empty text from the sample PDF

**S03 (Demo Script & Integration Proof):**
- `python scripts/demo_analyst.py` runs end-to-end without error
- Phase 1 output shows "Reading PDF..." and token reduction numbers
- Phase 2 output shows KPIs and risk areas as a markdown list
- Phase 3 footer shows `[Provider]: <name> | [Cost]: $X.XXX | [Status]: Success`
- Script automatically switches `LLM_PROVIDER` and re-runs; footer shows new provider

## Open Questions

- None — all decisions locked during discussion.
