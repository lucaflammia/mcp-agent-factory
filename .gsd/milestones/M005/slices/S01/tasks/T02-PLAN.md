---
estimated_steps: 12
estimated_files: 1
skills_used: []
---

# T02: Write test suite for vector store and verify all cases pass

Create `tests/test_vector_store.py` covering all correctness and isolation cases, then run the full suite to confirm no regressions.

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

## Inputs

- ``src/mcp_agent_factory/knowledge/__init__.py``
- ``src/mcp_agent_factory/knowledge/embedder.py``
- ``src/mcp_agent_factory/knowledge/vector_store.py``

## Expected Output

- ``tests/test_vector_store.py``

## Verification

pytest tests/test_vector_store.py -v && pytest tests/ -v --ignore=tests/test_vector_store.py
