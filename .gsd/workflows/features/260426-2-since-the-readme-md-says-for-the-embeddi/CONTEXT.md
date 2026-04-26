# Feature: LocalEmbedder — Real Semantic Embeddings

## Problem
`StubEmbedder` uses hash-seeded random projection. It's deterministic but not semantic —
querying "climate" won't find "prior climate analysis" unless you use the exact same string.
This makes the knowledge RAG layer functionally useless for real semantic retrieval.

## Solution
Add a `LocalEmbedder` backed by `sentence-transformers` (already installed) using the
`all-MiniLM-L6-v2` model (22MB, runs fully offline, no API key needed). Wire it as the
default in `gateway/app.py`.

## Key Decisions
- **Library:** `sentence-transformers` (already in the Python env)
- **Model:** `all-MiniLM-L6-v2` — small (22MB), fast, 384-dim, well-known quality
- **Dimension:** 384 (vs StubEmbedder's 64) — `InMemoryVectorStore` is dim-agnostic (cosine)
- **Tests:** Keep `StubEmbedder` in unit tests (no model download, instant, deterministic)
- **Lazy loading:** Model loaded on first `.embed()` call to avoid import-time cost

## In Scope
- Add `LocalEmbedder` class to `knowledge/embedder.py`
- Export from `knowledge/__init__.py`
- Switch default in `gateway/app.py` from `StubEmbedder` to `LocalEmbedder`
- Add `sentence-transformers` to `pyproject.toml` optional deps (`[ml]` extra)
- Update README example note

## Out of Scope
- Persistent vector store (still in-memory)
- Changing test fixtures (tests stay on StubEmbedder for speed)
- Batch embedding optimization
