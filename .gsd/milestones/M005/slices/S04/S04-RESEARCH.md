# S04: LibrarianAgent + Gateway Tool + SSE Events — Research

**Date:** 2026-03-31
**Status:** Ready for planning

## Summary

S04 is straightforward wiring of existing components. All foundational pieces (VectorStore, Embedder, StubEmbedder, InMemoryVectorStore, IngestionWorker) exist in `knowledge/`. The gateway pattern is established in `gateway/app.py`. SSE event emission is established in `messaging/sse_v1_router.py`. LibrarianAgent follows the AnalystAgent pattern in `agents/analyst.py`.

Four deliverables: (1) `knowledge/tools.py` with a `query_knowledge_base` function, (2) `agents/librarian.py` with LibrarianAgent, (3) gateway wiring (`query_knowledge_base` tool + `knowledge_retrieved` SSE event), (4) tests covering all new surface.

## Recommendation

Build in this order: `knowledge/tools.py` first (shared by LibrarianAgent and gateway), then `agents/librarian.py`, then gateway integration, then tests. The SSE event should be emitted from within the `_mcp_dispatch` handler after calling `query_knowledge_base` — publish to `knowledge.retrieved` on the module-level `bus`.

## Implementation Landscape

### Key Files

- `src/mcp_agent_factory/knowledge/tools.py` — **new file**. `query_knowledge_base(query: str, owner_id: str, store: VectorStore, embedder: Embedder, top_k: int = 5) -> list[dict]`. Embeds the query string via `embedder.embed(query)`, calls `store.search(query_vector, owner_id, top_k)`, returns list of dicts with `text` and `score` keys.
- `src/mcp_agent_factory/knowledge/__init__.py` — add `query_knowledge_base` to re-exports.
- `src/mcp_agent_factory/agents/librarian.py` — **new file**. `LibrarianAgent` with `__init__(store, embedder, top_k=5)` and `async run(task: AgentTask, ctx: MCPContext) -> RetrievalResult`. Calls `query_knowledge_base(task.name, owner_id, ...)`. Returns a `RetrievalResult` (new model or inline dict — follow `ReportResult` pattern from `agents/models.py`).
- `src/mcp_agent_factory/agents/models.py` — add `RetrievalResult(BaseModel)` with `session_key: str`, `chunks: list[dict]`, `summary: str`.
- `src/mcp_agent_factory/server_http.py` — add `query_knowledge_base` entry to the `TOOLS` list (lines 58+). Input schema: `{"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 5}}, "required": ["query"]}`. Note: `owner_id` is never in the schema — it comes from JWT `sub`.
- `src/mcp_agent_factory/gateway/app.py` — add module-level `InMemoryVectorStore` + `StubEmbedder` singletons (with test-injection helpers `set_vector_store`/`set_embedder`). Add `if tool_name == "query_knowledge_base":` branch in `_mcp_dispatch` that: extracts `owner_id` from `_claims['sub']` (or `"dev"` in DEV_MODE), calls `query_knowledge_base(...)`, publishes `knowledge_retrieved` SSE event to `bus`, returns chunks as content.
- `src/mcp_agent_factory/messaging/sse_v1_router.py` — no changes needed. The `knowledge_retrieved` event is emitted by publishing to a topic on the bus (e.g. `knowledge.retrieved`) and the existing SSE stream delivers it. Clients subscribe to `knowledge.retrieved` topic.
- `tests/test_s04.py` — **new file**. Test cases: `test_query_knowledge_base_returns_chunks`, `test_query_knowledge_base_empty_store`, `test_librarian_agent_run`, `test_gateway_tool_registered`, `test_gateway_query_knowledge_base_dev_mode`, `test_gateway_emits_sse_event`, `test_cross_tenant_isolation_via_gateway` (queries as `"bob"` after indexing as `"alice"` → empty).

### Build Order

1. `knowledge/tools.py` + `__init__.py` update — unblocks LibrarianAgent and gateway
2. `agents/models.py` — add `RetrievalResult`
3. `agents/librarian.py` — uses tools.py + models.py
4. `server_http.py` TOOLS list update + `gateway/app.py` handler
5. `tests/test_s04.py` — exercises all of the above

### Verification Approach

```bash
PYTHONPATH=src pytest tests/test_s04.py -v          # new tests
PYTHONPATH=src pytest tests/ -v                      # full suite, no regressions
```

Gateway integration (live):
```bash
MCP_DEV_MODE=1 uvicorn mcp_agent_factory.gateway.app:gateway_app --port 8000
# then mcp_call with query_knowledge_base tool
```

## Constraints

- `owner_id` MUST come from `_claims['sub']` in authenticated calls, never from tool arguments (D007).
- In DEV_MODE (`_claims is None`), use a fallback like `"dev"` for owner_id.
- `VectorStore.search()` takes `query_vector: np.ndarray`, not a string — always embed first (lesson from S03).
- Tab indentation throughout (project convention).
- `AgentTask` model fields are `id`, `name`, `payload`, `complexity`, `required_capability` — NOT `task_id`/`description`/`context`. LibrarianAgent should use `task.name` as the query string.
- TOOLS is defined in `server_http.py` and imported by `gateway/app.py` — add new tool there.

## Common Pitfalls

- **owner_id from args vs claims** — Never accept owner_id from the tool `arguments` dict in the gateway. Always derive from `_claims['sub']`. In DEV_MODE where `_claims is None`, use a constant like `"dev"`.
- **SSE event emission** — The `knowledge_retrieved` event should be published to the bus (e.g. `bus.publish("knowledge.retrieved", AgentMessage(...))`) so any SSE subscriber on that topic receives it. No changes to sse_v1_router.py are needed.
- **Module-level singletons for store/embedder** — Follow the pattern of `bus`, `sampling_handler` in gateway/app.py: create module-level singletons + `set_*` helpers for test injection.
- **RetrievalResult vs dict** — Define `RetrievalResult` in `agents/models.py` to keep consistency with `AnalysisResult`/`ReportResult`. LibrarianAgent.run() should return it.
