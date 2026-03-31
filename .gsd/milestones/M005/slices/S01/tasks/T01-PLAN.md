---
estimated_steps: 5
estimated_files: 3
skills_used: []
---

# T01: Implement the knowledge/ package (Embedder, VectorStore protocols and impls)

Create the `src/mcp_agent_factory/knowledge/` package with three files:

1. `embedder.py` — defines `Embedder` Protocol with `embed(text: str) -> np.ndarray` method; implements `StubEmbedder` that produces a deterministic fixed-dimension (64-dim) float32 numpy vector from text via a seeded hash projection. Same input text must always return the same vector. Guard against zero-vectors by adding a small epsilon offset so cosine similarity never divides by zero.

2. `vector_store.py` — defines `VectorStore` Protocol with `upsert(owner_id: str, text: str, vector: np.ndarray) -> None` and `search(owner_id: str, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]` methods; implements `InMemoryVectorStore` using `dict[str, list[tuple[str, np.ndarray]]]` keyed by `owner_id`. `search` computes cosine similarity between `query_vector` and all stored vectors for that `owner_id` only, returns top-k `(text, score)` tuples sorted descending by score. Cross-namespace data is never touched.

3. `__init__.py` — re-exports: `Embedder`, `StubEmbedder`, `VectorStore`, `InMemoryVectorStore`.

Conventions: tab indentation throughout; type hints; numpy for all vector math. No other dependencies.

## Inputs

- None specified.

## Expected Output

- ``src/mcp_agent_factory/knowledge/__init__.py``
- ``src/mcp_agent_factory/knowledge/embedder.py``
- ``src/mcp_agent_factory/knowledge/vector_store.py``

## Verification

python -c "from mcp_agent_factory.knowledge import StubEmbedder, InMemoryVectorStore; e=StubEmbedder(); s=InMemoryVectorStore(); v=e.embed('hello'); s.upsert('u1','hello',v); r=s.search('u1',v,1); assert len(r)==1; assert r[0][0]=='hello'; print('OK')"
