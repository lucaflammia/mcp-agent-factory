# S01: Vector Store + Multi-Tenant Middleware — Research

**Date:** 2026-03-31
**Status:** Ready for planning

## Summary

S01 is greenfield work: the entire `knowledge/` package does not yet exist. All other required
infrastructure (numpy, MessageBus, JWT auth, AgentProfile/AgentTask models) is already in place.
The slice delivers two Protocols (`VectorStore`, `Embedder`) and their default implementations
(`InMemoryVectorStore`, `StubEmbedder`), all under `src/mcp_agent_factory/knowledge/`.
No existing files need changes in S01 — downstream slices (S02, S03, S04) will wire in those
files. The core algorithmic risk is cosine-similarity correctness; everything else is
straightforward Python data-structure work.

Isolation is the security invariant: every `upsert` and `search` call carries an `owner_id`
and the store must never leak across namespaces. Tests must prove the two-user cross-tenant case
returns empty.

## Recommendation

Build the `knowledge/` package in a single logical unit. The natural seam is
`embedder.py` → `vector_store.py` (embedder produces vectors, store holds and ranks them).
Write the test file first to drive the API shape, then implement. No external libraries needed
beyond numpy.

## Implementation Landscape

### Key Files (all NEW — none exist today)

- `src/mcp_agent_factory/knowledge/__init__.py` — package init; re-export public symbols
- `src/mcp_agent_factory/knowledge/embedder.py` — `Embedder` Protocol + `StubEmbedder` (deterministic hash → fixed-dim float32 vector via numpy; same text → same vector every time)
- `src/mcp_agent_factory/knowledge/vector_store.py` — `VectorStore` Protocol + `InMemoryVectorStore`; storage keyed by `owner_id`; cosine similarity ranking via numpy; returns list of `(chunk_text, score)` tuples
- `tests/test_vector_store.py` — NEW test file; success criterion for the slice

### Existing Files (read-only for S01 context)

- `src/mcp_agent_factory/agents/models.py` — `AgentTask`, `MCPContext`; no changes in S01
- `src/mcp_agent_factory/messaging/bus.py` — `MessageBus`, `AgentMessage`; no changes in S01
- `src/mcp_agent_factory/auth/resource.py` — `make_verify_token`; shows `claims['sub']` is the owner_id source; no changes in S01
- `src/mcp_agent_factory/economics/utility.py` — `AgentProfile`, `UtilityFunction`; no changes in S01 (S03 modifies these)
- `tests/test_economics.py` — regression baseline; must keep passing

### Build Order

1. `knowledge/embedder.py` first — `StubEmbedder` produces deterministic vectors; this is the
   input to the store. Simple to test in isolation (same text → same numpy array).
2. `knowledge/vector_store.py` second — depends only on embedder output shape.
   Implement `InMemoryVectorStore`: dict-of-lists keyed by `owner_id`; upsert appends
   `(text, vector)` tuples; search computes cosine similarity between query vector and all
   stored vectors for that owner, returns top-k sorted descending.
3. `knowledge/__init__.py` — re-export; no logic.
4. `tests/test_vector_store.py` — covers: upsert+query ranking correct, cross-tenant query
   returns empty, empty store returns empty, identical texts rank above unrelated texts.

### Verification Approach

```
pytest tests/test_vector_store.py -v
```

Must pass: cosine ranking correct, cross-tenant query returns empty.
Existing suite must not regress:
```
pytest tests/ -v --ignore=tests/test_vector_store.py
```

## Constraints

- numpy already installed (v2.4.2); no new dependencies needed
- Tab indentation throughout (project convention)
- `owner_id` partitions storage — never cross namespaces; this is a hard security boundary (R101, D007)
- `StubEmbedder` must be deterministic: same input text → same output vector every call (needed so tests are reproducible)
- Fixed embedding dimension (e.g. 64 or 128) — must be consistent between upsert and query
- Protocol pattern (not ABC): both `VectorStore` and `Embedder` defined as `typing.Protocol` (D006)

## Common Pitfalls

- **Zero-vector inputs to cosine similarity** — if a stub text hashes to a zero vector, division-by-zero will occur. Guard with a small epsilon or ensure the hash function never produces all-zeros.
- **Dimension mismatch between upsert and query** — StubEmbedder must always return the same fixed dimension regardless of text length; a variable-length hash will break cosine computation.
- **Cross-tenant data leak via missing owner_id filter** — store must partition by `owner_id` at storage level, not filter after the fact across a shared list.
- **Score ordering ties** — when all scores are equal (e.g. random stub vectors), test assertions on ranked order should be flexible or use distinct texts that produce meaningfully different projections.
