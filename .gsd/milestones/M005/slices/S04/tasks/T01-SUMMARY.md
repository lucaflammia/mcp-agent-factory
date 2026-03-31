---
id: T01
parent: S04
milestone: M005
provides:
  - query_knowledge_base tool function
  - LibrarianAgent with async run()
  - RetrievalResult model
  - gateway query_knowledge_base dispatch + SSE event
key_files:
  - src/mcp_agent_factory/knowledge/tools.py
  - src/mcp_agent_factory/agents/librarian.py
  - src/mcp_agent_factory/agents/models.py
  - src/mcp_agent_factory/knowledge/__init__.py
  - src/mcp_agent_factory/server_http.py
  - src/mcp_agent_factory/gateway/app.py
key_decisions:
  - VectorStore.search signature is (owner_id, query_vector, top_k) — adapted from plan which had query_vector first
  - search returns (text, score) tuples (no chunk_id) — tools.py adapted accordingly
patterns_established:
  - Module-level singletons with set_* injection helpers pattern extended to vector store and embedder
observability_surfaces:
  - gateway/app.py publishes AgentMessage to 'knowledge.retrieved' topic on every RAG call; SSE subscribers see the event
duration: ~5m
verification_result: passed
completed_at: 2026-03-31
blocker_discovered: false
---

# T01: Implement knowledge/tools.py, LibrarianAgent, and gateway wiring

**Added RAG query_knowledge_base tool, LibrarianAgent, RetrievalResult model, and wired them into the gateway with SSE event emission.**

## What Happened

Created `knowledge/tools.py` with `query_knowledge_base` that embeds the query via the Embedder and calls `store.search`. The real `VectorStore.search` signature is `(owner_id, query_vector, top_k)` and returns `(text, score)` tuples (not `(chunk_id, text, score)` as the plan stated) — the implementation was adapted accordingly.

Added `RetrievalResult` to `agents/models.py` after `ReportResult`. Created `agents/librarian.py` with `LibrarianAgent` using `task.name` as the query and `task.id` as owner_id. Updated `knowledge/__init__.py` to re-export `query_knowledge_base`. Appended `query_knowledge_base` to `TOOLS` in `server_http.py`. In `gateway/app.py`: imported the new knowledge symbols, added `_vector_store` and `_embedder` module-level singletons, added `set_vector_store` and `set_embedder` injection helpers, and added the `query_knowledge_base` dispatch branch that publishes a `knowledge.retrieved` `AgentMessage` to the bus.

## Verification

```
PYTHONPATH=src python -c "from mcp_agent_factory.knowledge import query_knowledge_base; from mcp_agent_factory.agents.librarian import LibrarianAgent; from mcp_agent_factory.agents.models import RetrievalResult; from mcp_agent_factory.gateway.app import set_vector_store, set_embedder; print('imports ok')"
# → imports ok
```

Existing related tests (test_ingest, test_vector_store, test_gateway) all pass.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `PYTHONPATH=src python -c "from mcp_agent_factory.knowledge import query_knowledge_base; ..."` | 0 | ✅ pass | <1s |
| 2 | `PYTHONPATH=src python -m pytest tests/test_ingest.py tests/test_vector_store.py tests/test_gateway.py -x -q` | 0 | ✅ pass | 4.91s |

## Diagnostics

SSE event: subscribe to `/sse/v1/events` and call `query_knowledge_base` — observe `knowledge.retrieved` event with `owner_id`, `chunk_count`, and `source` fields in content.

## Deviations

- `VectorStore.search` signature is `(owner_id, query_vector, top_k)` not `(query_vector, owner_id, top_k)` as stated in the plan. Implementation adapted to real signature.
- `search` returns `(text, score)` tuples, not `(chunk_id, text, score)`. Dict construction adapted.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/knowledge/tools.py` — new: `query_knowledge_base` function
- `src/mcp_agent_factory/agents/librarian.py` — new: `LibrarianAgent`
- `src/mcp_agent_factory/agents/models.py` — added `RetrievalResult` model
- `src/mcp_agent_factory/knowledge/__init__.py` — re-exports `query_knowledge_base`
- `src/mcp_agent_factory/server_http.py` — appended `query_knowledge_base` to `TOOLS`
- `src/mcp_agent_factory/gateway/app.py` — singletons, injection helpers, dispatch branch
