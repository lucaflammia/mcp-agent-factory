---
estimated_steps: 7
estimated_files: 6
skills_used: []
---

# T01: Implement knowledge/tools.py, LibrarianAgent, and gateway wiring

Create all new production code for S04:

1. **`src/mcp_agent_factory/knowledge/tools.py`** — define `query_knowledge_base(query: str, owner_id: str, store: VectorStore, embedder: Embedder, top_k: int = 5) -> list[dict]`. Embed via `embedder.embed(query)`, call `store.search(query_vector, owner_id, top_k)`, return list of dicts with `text` and `score` keys from each (chunk_id, text, score) tuple returned by search. Use tab indentation.

2. **`src/mcp_agent_factory/knowledge/__init__.py`** — add `query_knowledge_base` to re-exports alongside existing symbols.

3. **`src/mcp_agent_factory/agents/models.py`** — add `RetrievalResult(BaseModel)` with fields `session_key: str`, `chunks: list[dict] = Field(default_factory=list)`, `summary: str = ''`. Place after `ReportResult`.

4. **`src/mcp_agent_factory/agents/librarian.py`** — implement `LibrarianAgent` with `__init__(self, store: VectorStore, embedder: Embedder, top_k: int = 5)` and `async run(self, task: AgentTask, ctx: MCPContext) -> RetrievalResult`. Call `query_knowledge_base(task.name, task.id, store, embedder, top_k)` — use `task.id` as owner_id (callers set this to the JWT sub). Return `RetrievalResult(session_key=task.id, chunks=chunks, summary=f'Retrieved {len(chunks)} chunk(s) for query: {task.name}')`.

5. **`src/mcp_agent_factory/server_http.py`** — append to `TOOLS` list: `{"name": "query_knowledge_base", "description": "Query the vector knowledge base for relevant prior context.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Natural language query"}, "top_k": {"type": "integer", "default": 5, "description": "Number of results"}}, "required": ["query"]}}`.

6. **`src/mcp_agent_factory/gateway/app.py`** — (a) Import `InMemoryVectorStore`, `StubEmbedder`, `query_knowledge_base` from `mcp_agent_factory.knowledge`. (b) Add module-level singletons after existing ones: `_vector_store: InMemoryVectorStore = InMemoryVectorStore()` and `_embedder: StubEmbedder = StubEmbedder()`. (c) Add test-injection helpers `set_vector_store(store)` and `set_embedder(embedder)` that replace the module-level singletons. (d) In `_mcp_dispatch`, add a new `if tool_name == "query_knowledge_base":` branch: extract `owner_id = _claims['sub'] if _claims else 'dev'`, call `chunks = query_knowledge_base(args.get('query', ''), owner_id, _vector_store, _embedder, args.get('top_k', 5))`, publish `bus.publish('knowledge.retrieved', AgentMessage(topic='knowledge.retrieved', sender='gateway', recipient='*', content={'owner_id': owner_id, 'chunk_count': len(chunks), 'source': 'vector_store'}))`, return `_ok(req_id, {'content': [{'type': 'text', 'text': str(chunks)}]})`.

## Inputs

- ``src/mcp_agent_factory/knowledge/__init__.py``
- ``src/mcp_agent_factory/knowledge/vector_store.py``
- ``src/mcp_agent_factory/knowledge/embedder.py``
- ``src/mcp_agent_factory/agents/models.py``
- ``src/mcp_agent_factory/agents/analyst.py``
- ``src/mcp_agent_factory/server_http.py``
- ``src/mcp_agent_factory/gateway/app.py``
- ``src/mcp_agent_factory/messaging/bus.py``

## Expected Output

- ``src/mcp_agent_factory/knowledge/tools.py``
- ``src/mcp_agent_factory/agents/librarian.py``
- ``src/mcp_agent_factory/agents/models.py` (RetrievalResult added)`
- ``src/mcp_agent_factory/knowledge/__init__.py` (query_knowledge_base re-exported)`
- ``src/mcp_agent_factory/server_http.py` (query_knowledge_base in TOOLS)`
- ``src/mcp_agent_factory/gateway/app.py` (singletons + dispatch branch added)`

## Verification

PYTHONPATH=src python -c "from mcp_agent_factory.knowledge import query_knowledge_base; from mcp_agent_factory.agents.librarian import LibrarianAgent; from mcp_agent_factory.agents.models import RetrievalResult; from mcp_agent_factory.gateway.app import set_vector_store, set_embedder; print('imports ok')"

## Observability Impact

gateway/app.py publishes AgentMessage to knowledge.retrieved topic on each RAG call — SSE subscribers see the event.
