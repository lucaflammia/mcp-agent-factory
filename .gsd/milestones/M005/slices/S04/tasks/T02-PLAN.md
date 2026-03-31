---
estimated_steps: 16
estimated_files: 1
skills_used: []
---

# T02: Write and verify tests/test_s04.py — 7 cases covering all new surface

Create `tests/test_s04.py` with the following 7 test cases. Use `StubEmbedder` and `InMemoryVectorStore` throughout.

**Imports needed:** `pytest`, `asyncio`, `mcp_agent_factory.knowledge` (InMemoryVectorStore, StubEmbedder, IngestionWorker, query_knowledge_base), `mcp_agent_factory.agents.librarian` (LibrarianAgent), `mcp_agent_factory.agents.models` (AgentTask, MCPContext, RetrievalResult), `mcp_agent_factory.server_http` (TOOLS), `mcp_agent_factory.gateway.app` (gateway_app, set_vector_store, set_embedder, bus), `mcp_agent_factory.messaging.bus` (AgentMessage), `fastapi.testclient` (TestClient).

**Helper:** `_populated_store()` — creates a `StubEmbedder` and `InMemoryVectorStore`, upserts one chunk (`text='prior analysis about climate'`, `owner_id='alice'`), returns `(store, embedder)`.

1. **test_query_knowledge_base_returns_chunks** — call `query_knowledge_base('climate', 'alice', store, embedder)` on a populated store; assert result is a non-empty list and `result[0]['text'] == 'prior analysis about climate'` and `'score' in result[0]`.

2. **test_query_knowledge_base_empty_store** — call on a fresh `InMemoryVectorStore`; assert result == `[]`.

3. **test_librarian_agent_run** — instantiate `LibrarianAgent(store, embedder)`, create `task = AgentTask(id='alice', name='climate', payload={})`, `ctx = MCPContext(tool_name='test')`, call `asyncio.run(librarian.run(task, ctx))`, assert result is `RetrievalResult`, `result.session_key == 'alice'`, `len(result.chunks) >= 1`, `'Retrieved' in result.summary`.

4. **test_gateway_tool_registered** — assert any tool in `TOOLS` has `name == 'query_knowledge_base'`.

5. **test_gateway_query_knowledge_base_dev_mode** — use `set_vector_store` / `set_embedder` to inject populated store. Set env var `MCP_DEV_MODE=1` (via `monkeypatch.setenv` or `os.environ`). Then reload / patch `gateway.app.DEV_MODE = True` directly. Use `TestClient(gateway_app)` to POST `/mcp` with body `{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'query_knowledge_base', 'arguments': {'query': 'climate', 'top_k': 3}}}`. Assert response status 200 and the JSON result `content[0]['text']` contains chunk data (non-empty string).

6. **test_gateway_emits_sse_event** — inject populated store/embedder. Subscribe to `knowledge.retrieved` topic on `bus` before making the call. After calling `_mcp_dispatch` directly (import it), assert that `bus` received a message on `knowledge.retrieved` topic. Implementation: import `_mcp_dispatch` and `bus` from `gateway.app`; call `asyncio.run(_mcp_dispatch(req, None))` with DEV_MODE-style None claims and `gateway.app.DEV_MODE = True`; check `bus` queue. Simpler approach: after the TestClient call from T5, check that bus has the message by subscribing to `knowledge.retrieved` before the call and checking the queue after.

Actually, simplest approach for test_gateway_emits_sse_event: import `bus` from `gateway.app`, subscribe a queue to `knowledge.retrieved`, then make the TestClient call, then assert the queue is non-empty.

7. **test_cross_tenant_isolation_via_gateway** — inject populated store (chunks under `owner_id='alice'`), inject embedder. With `DEV_MODE=True` (None claims → owner_id='dev'), query for 'climate' → result should be `[]` (no chunks under 'dev'). Assert the content text is `'[]'`.

Run verification:
```bash
PYTHONPATH=src pytest tests/test_s04.py -v
PYTHONPATH=src pytest tests/ -v
```

## Inputs

- ``src/mcp_agent_factory/knowledge/tools.py``
- ``src/mcp_agent_factory/agents/librarian.py``
- ``src/mcp_agent_factory/agents/models.py``
- ``src/mcp_agent_factory/server_http.py``
- ``src/mcp_agent_factory/gateway/app.py``
- ``src/mcp_agent_factory/knowledge/__init__.py``

## Expected Output

- ``tests/test_s04.py``

## Verification

PYTHONPATH=src pytest tests/test_s04.py -v && PYTHONPATH=src pytest tests/ -v 2>&1 | tail -5
