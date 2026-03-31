---
id: T01
parent: S04
milestone: M005
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/knowledge/tools.py", "src/mcp_agent_factory/agents/librarian.py", "src/mcp_agent_factory/agents/models.py", "src/mcp_agent_factory/knowledge/__init__.py", "src/mcp_agent_factory/server_http.py", "src/mcp_agent_factory/gateway/app.py"]
key_decisions: ["VectorStore.search signature adapted to real (owner_id, query_vector, top_k) form", "Module-level singleton + set_* injection helper pattern extended to vector store and embedder"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "Import smoke test passed (imports ok). Existing related tests (test_ingest, test_vector_store, test_gateway — 25 tests) all pass."
completed_at: 2026-03-31T11:23:58.088Z
blocker_discovered: false
---

# T01: Added RAG query_knowledge_base tool, LibrarianAgent, RetrievalResult model, and wired them into the gateway with SSE event emission

> Added RAG query_knowledge_base tool, LibrarianAgent, RetrievalResult model, and wired them into the gateway with SSE event emission

## What Happened
---
id: T01
parent: S04
milestone: M005
key_files:
  - src/mcp_agent_factory/knowledge/tools.py
  - src/mcp_agent_factory/agents/librarian.py
  - src/mcp_agent_factory/agents/models.py
  - src/mcp_agent_factory/knowledge/__init__.py
  - src/mcp_agent_factory/server_http.py
  - src/mcp_agent_factory/gateway/app.py
key_decisions:
  - VectorStore.search signature adapted to real (owner_id, query_vector, top_k) form
  - Module-level singleton + set_* injection helper pattern extended to vector store and embedder
duration: ""
verification_result: passed
completed_at: 2026-03-31T11:23:58.093Z
blocker_discovered: false
---

# T01: Added RAG query_knowledge_base tool, LibrarianAgent, RetrievalResult model, and wired them into the gateway with SSE event emission

**Added RAG query_knowledge_base tool, LibrarianAgent, RetrievalResult model, and wired them into the gateway with SSE event emission**

## What Happened

Created knowledge/tools.py with query_knowledge_base that embeds the query and calls store.search. The real VectorStore.search signature is (owner_id, query_vector, top_k) and returns (text, score) tuples — adapted from the plan. Added RetrievalResult to agents/models.py, created agents/librarian.py with LibrarianAgent, updated knowledge/__init__.py to re-export query_knowledge_base, appended query_knowledge_base to TOOLS in server_http.py, and in gateway/app.py added singletons, injection helpers, and dispatch branch that publishes a knowledge.retrieved AgentMessage to the bus on every RAG call.

## Verification

Import smoke test passed (imports ok). Existing related tests (test_ingest, test_vector_store, test_gateway — 25 tests) all pass.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `PYTHONPATH=src python -c "from mcp_agent_factory.knowledge import query_knowledge_base; from mcp_agent_factory.agents.librarian import LibrarianAgent; from mcp_agent_factory.agents.models import RetrievalResult; from mcp_agent_factory.gateway.app import set_vector_store, set_embedder; print('imports ok')"` | 0 | ✅ pass | 800ms |
| 2 | `PYTHONPATH=src python -m pytest tests/test_ingest.py tests/test_vector_store.py tests/test_gateway.py -x -q` | 0 | ✅ pass | 4910ms |


## Deviations

VectorStore.search signature is (owner_id, query_vector, top_k) not (query_vector, owner_id, top_k) as stated in the plan; search returns (text, score) tuples not (chunk_id, text, score). Implementation adapted to real signatures.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/knowledge/tools.py`
- `src/mcp_agent_factory/agents/librarian.py`
- `src/mcp_agent_factory/agents/models.py`
- `src/mcp_agent_factory/knowledge/__init__.py`
- `src/mcp_agent_factory/server_http.py`
- `src/mcp_agent_factory/gateway/app.py`


## Deviations
VectorStore.search signature is (owner_id, query_vector, top_k) not (query_vector, owner_id, top_k) as stated in the plan; search returns (text, score) tuples not (chunk_id, text, score). Implementation adapted to real signatures.

## Known Issues
None.
