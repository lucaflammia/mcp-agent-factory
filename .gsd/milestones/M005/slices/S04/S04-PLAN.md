# S04: LibrarianAgent + Gateway Tool + SSE Events

**Goal:** Expose the RAG layer end-to-end: `query_knowledge_base` tool registered on the gateway, LibrarianAgent for retrieval synthesis, and `knowledge_retrieved` SSE event emitted on every RAG query.
**Demo:** After this: mcp_call(server='agent-factory', tool='query_knowledge_base', args={...}) returns chunks; SSE stream shows knowledge_retrieved event

## Tasks
- [ ] **T01: Implement knowledge/tools.py, LibrarianAgent, and gateway wiring** — Create all new production code for S04:

1. **`src/mcp_agent_factory/knowledge/tools.py`** — define `query_knowledge_base(query: str, owner_id: str, store: VectorStore, embedder: Embedder, top_k: int = 5) -> list[dict]`. Embed via `embedder.embed(query)`, call `store.search(query_vector, owner_id, top_k)`, return list of dicts with `text` and `score` keys from each (chunk_id, text, score) tuple returned by search. Use tab indentation.

2. **`src/mcp_agent_factory/knowledge/__init__.py`** — add `query_knowledge_base` to re-exports alongside existing symbols.

3. **`src/mcp_agent_factory/agents/models.py`** — add `RetrievalResult(BaseModel)` with fields `session_key: str`, `chunks: list[dict] = Field(default_factory=list)`, `summary: str = ''`. Place after `ReportResult`.

4. **`src/mcp_agent_factory/agents/librarian.py`** — implement `LibrarianAgent` with `__init__(self, store: VectorStore, embedder: Embedder, top_k: int = 5)` and `async run(self, task: AgentTask, ctx: MCPContext) -> RetrievalResult`. Call `query_knowledge_base(task.name, task.id, store, embedder, top_k)` — use `task.id` as owner_id (callers set this to the JWT sub). Return `RetrievalResult(session_key=task.id, chunks=chunks, summary=f'Retrieved {len(chunks)} chunk(s) for query: {task.name}')`.

5. **`src/mcp_agent_factory/server_http.py`** — append to `TOOLS` list: `{"name": "query_knowledge_base", "description": "Query the vector knowledge base for relevant prior context.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Natural language query"}, "top_k": {"type": "integer", "default": 5, "description": "Number of results"}}, "required": ["query"]}}`.

6. **`src/mcp_agent_factory/gateway/app.py`** — (a) Import `InMemoryVectorStore`, `StubEmbedder`, `query_knowledge_base` from `mcp_agent_factory.knowledge`. (b) Add module-level singletons after existing ones: `_vector_store: InMemoryVectorStore = InMemoryVectorStore()` and `_embedder: StubEmbedder = StubEmbedder()`. (c) Add test-injection helpers `set_vector_store(store)` and `set_embedder(embedder)` that replace the module-level singletons. (d) In `_mcp_dispatch`, add a new `if tool_name == "query_knowledge_base":` branch: extract `owner_id = _claims['sub'] if _claims else 'dev'`, call `chunks = query_knowledge_base(args.get('query', ''), owner_id, _vector_store, _embedder, args.get('top_k', 5))`, publish `bus.publish('knowledge.retrieved', AgentMessage(topic='knowledge.retrieved', sender='gateway', recipient='*', content={'owner_id': owner_id, 'chunk_count': len(chunks), 'source': 'vector_store'}))`, return `_ok(req_id, {'content': [{'type': 'text', 'text': str(chunks)}]})`.
  - Estimate: 45m
  - Files: src/mcp_agent_factory/knowledge/tools.py, src/mcp_agent_factory/knowledge/__init__.py, src/mcp_agent_factory/agents/models.py, src/mcp_agent_factory/agents/librarian.py, src/mcp_agent_factory/server_http.py, src/mcp_agent_factory/gateway/app.py
  - Verify: PYTHONPATH=src python -c "from mcp_agent_factory.knowledge import query_knowledge_base; from mcp_agent_factory.agents.librarian import LibrarianAgent; from mcp_agent_factory.agents.models import RetrievalResult; from mcp_agent_factory.gateway.app import set_vector_store, set_embedder; print('imports ok')"
- [ ] **T02: Write and verify tests/test_s04.py — 7 cases covering all new surface** — Create `tests/test_s04.py` with the following 7 test cases. Use `StubEmbedder` and `InMemoryVectorStore` throughout.

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
  - Estimate: 45m
  - Files: tests/test_s04.py
  - Verify: PYTHONPATH=src pytest tests/test_s04.py -v && PYTHONPATH=src pytest tests/ -v 2>&1 | tail -5
