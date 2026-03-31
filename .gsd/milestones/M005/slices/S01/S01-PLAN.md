# S01: Vector Store + Multi-Tenant Middleware

**Goal:** Create the `knowledge/` package with `Embedder` Protocol + `StubEmbedder` and `VectorStore` Protocol + `InMemoryVectorStore`, enforcing per-`owner_id` namespace isolation and cosine-similarity ranking via numpy.
**Demo:** After this: pytest tests/test_vector_store.py -v passes — cosine ranking correct, cross-tenant query returns empty

## Tasks
- [x] **T01: Created knowledge/ package with Embedder + StubEmbedder and VectorStore + InMemoryVectorStore with per-owner_id namespace isolation and cosine-similarity ranking** — Create the `src/mcp_agent_factory/knowledge/` package with three files:

1. `embedder.py` — defines `Embedder` Protocol with `embed(text: str) -> np.ndarray` method; implements `StubEmbedder` that produces a deterministic fixed-dimension (64-dim) float32 numpy vector from text via a seeded hash projection. Same input text must always return the same vector. Guard against zero-vectors by adding a small epsilon offset so cosine similarity never divides by zero.

2. `vector_store.py` — defines `VectorStore` Protocol with `upsert(owner_id: str, text: str, vector: np.ndarray) -> None` and `search(owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]` methods; implements `InMemoryVectorStore` using `dict[str, list[tuple[str, np.ndarray]]]` keyed by `owner_id`. `search` computes cosine similarity between `query_vector` and all stored vectors for that `owner_id` only, returns top-k `(text, score)` tuples sorted descending by score. Cross-namespace data is never touched.

3. `__init__.py` — re-exports: `Embedder`, `StubEmbedder`, `VectorStore`, `InMemoryVectorStore`.

Conventions: tab indentation throughout; type hints; numpy for all vector math. No other dependencies.
  - Estimate: 30m
  - Files: src/mcp_agent_factory/knowledge/__init__.py, src/mcp_agent_factory/knowledge/embedder.py, src/mcp_agent_factory/knowledge/vector_store.py
  - Verify: python -c "from mcp_agent_factory.knowledge import StubEmbedder, InMemoryVectorStore; e=StubEmbedder(); s=InMemoryVectorStore(); v=e.embed('hello'); s.upsert('u1','hello',v); r=s.search('u1',v,1); assert len(r)==1; assert r[0][0]=='hello'; print('OK')"
- [x] **T02: Created tests/test_vector_store.py with 6 passing test cases covering cosine ranking, cross-tenant isolation, top_k, and StubEmbedder determinism** — Create `tests/test_vector_store.py` covering all correctness and isolation cases, then run the full suite to confirm no regressions.

Test cases to include:
1. **Upsert + query returns result** — upsert one chunk, query with same vector, assert one result returned.
2. **Cosine ranking correct** — upsert two texts: an identical duplicate of the query text and an unrelated text; assert the identical text ranks first (higher score).
3. **Cross-tenant isolation** — upsert as `owner_id='alice'`, query as `owner_id='bob'`, assert empty list returned.
4. **Empty store returns empty** — query on a fresh store with no data, assert `[]`.
5. **top_k respected** — upsert 5 chunks, query with top_k=2, assert exactly 2 results returned.
6. **StubEmbedder determinism** — call `embed('foo')` twice, assert `np.array_equal(v1, v2)`.

Import path: `from mcp_agent_factory.knowledge import StubEmbedder, InMemoryVectorStore`.

After writing tests, run:
- `pytest tests/test_vector_store.py -v` — must pass all 6 cases
- `pytest tests/ -v --ignore=tests/test_vector_store.py` — must pass (no regressions)
  - Estimate: 20m
  - Files: tests/test_vector_store.py
  - Verify: pytest tests/test_vector_store.py -v && pytest tests/ -v --ignore=tests/test_vector_store.py
