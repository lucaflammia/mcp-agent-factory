---
id: S02
parent: M012
milestone: M012
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - (none)
key_decisions:
  - (none)
patterns_established:
  - (none)
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-05-01T14:48:15.171Z
blocker_discovered: false
---

# S02: Full OTel Pipeline Instrumentation

**Added 5 OTel child spans across the agent pipeline — 4 in AnalystAgent.analyze_document() and 1 in InMemoryVectorStore.search() — all carrying token count and diagnostic attributes.**

## What Happened

AnalystAgent.analyze_document() now emits agent.pdf_extract, agent.prune, agent.pii_scrub, and agent.llm_route spans under the mcp.agents/analyze root span. Each span carries contextually relevant attributes: chunk counts, page counts, token estimates (chars/4), provider name, and cost. InMemoryVectorStore.search() emits agent.vector_store.search with owner_id, top_k, and result_count. All spans use get_tracer() which falls back to a no-op when OTEL is not configured — 9 existing tests pass without modification.

## Verification

python3.11 -m pytest tests/test_agents_dispatch.py tests/test_vector_store.py -v → 9 passed

## Requirements Advanced

None.

## Requirements Validated

- R015 — 4 child spans with token counts in analyst.py; VectorStore span in vector_store.py
- R020 — Span chain Gateway→AnalystAgent→phases→VectorStore emitted to Jaeger exporter

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/agents/analyst.py` — 
- `src/mcp_agent_factory/knowledge/vector_store.py` — 
