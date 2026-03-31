---
id: S04
parent: M005
milestone: M005
provides:
  - query_knowledge_base MCP tool callable via gateway
  - LibrarianAgent for retrieval synthesis
  - knowledge.retrieved SSE event on every RAG query
  - RetrievalResult model for agent handoff
requires:
  - slice: S01
    provides: InMemoryVectorStore, VectorStore protocol, StubEmbedder
  - slice: S02
    provides: IngestionWorker pattern
  - slice: S03
    provides: knowledge module structure
affects:
  []
key_files:
  - src/mcp_agent_factory/knowledge/tools.py
  - src/mcp_agent_factory/agents/librarian.py
  - src/mcp_agent_factory/agents/models.py
  - src/mcp_agent_factory/gateway/app.py
  - tests/test_s04.py
key_decisions:
  - gateway dispatch resolves owner_id from JWT sub when present, falls back to 'dev' for unauthenticated callers
  - Module-level singleton + set_* injection helper pattern extended to vector store and embedder
patterns_established:
  - subscribe-before-action + q.empty()/q.get_nowait() for synchronous bus event assertions in TestClient tests
observability_surfaces:
  - gateway/app.py publishes AgentMessage to 'knowledge.retrieved' topic on every RAG call — SSE subscribers see owner_id, chunk_count, and source fields
drill_down_paths:
  - .gsd/milestones/M005/slices/S04/tasks/T01-SUMMARY.md
  - .gsd/milestones/M005/slices/S04/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-31T11:30:44.898Z
blocker_discovered: false
---

# S04: LibrarianAgent + Gateway Tool + SSE Events

**Exposed RAG layer end-to-end: query_knowledge_base gateway tool, LibrarianAgent, knowledge.retrieved SSE event, and 7 passing tests**

## What Happened

T01 created all production code: query_knowledge_base tool function, LibrarianAgent, RetrievalResult model, query_knowledge_base entry in TOOLS, and the gateway dispatch branch that calls the RAG layer and publishes a knowledge.retrieved AgentMessage to the bus. T02 wrote tests/test_s04.py with 7 cases verifying the full surface — empty store, chunk retrieval, LibrarianAgent.run, gateway tool registration, dev-mode call, SSE event emission, and cross-tenant isolation. All 7 pass; 60 tests across related files pass with no regressions.

## Verification

PYTHONPATH=src pytest tests/test_s04.py -v → 7/7 passed. Broader suite (60 tests across test_s04, test_ingest, test_vector_store, test_gateway, test_pipeline, test_schema_validation) passes with no regressions.

## Requirements Advanced

None.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

VectorStore.search signature adapted (owner_id first, not query_vector first). store.upsert() used directly in tests instead of IngestionWorker (which requires a bus). bus.subscribe returns asyncio.Queue — tests use q.empty()/q.get_nowait().

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/knowledge/tools.py` — New: query_knowledge_base function
- `src/mcp_agent_factory/agents/librarian.py` — New: LibrarianAgent
- `src/mcp_agent_factory/agents/models.py` — Added RetrievalResult model
- `src/mcp_agent_factory/knowledge/__init__.py` — Re-exports query_knowledge_base
- `src/mcp_agent_factory/server_http.py` — Appended query_knowledge_base to TOOLS
- `src/mcp_agent_factory/gateway/app.py` — Added _vector_store/_embedder singletons, set_vector_store/set_embedder helpers, query_knowledge_base dispatch branch with knowledge.retrieved SSE event
- `tests/test_s04.py` — New: 7 tests covering full S04 surface
