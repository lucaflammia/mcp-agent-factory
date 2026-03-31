---
id: S01
parent: M005
milestone: M005
provides:
  - InMemoryVectorStore with per-owner_id namespace isolation
  - StubEmbedder for deterministic test vectors
  - Embedder + VectorStore protocols for swappable backends
requires:
  []
affects:
  - S02
  - S03
  - S04
key_files:
  - src/mcp_agent_factory/knowledge/__init__.py
  - src/mcp_agent_factory/knowledge/embedder.py
  - src/mcp_agent_factory/knowledge/vector_store.py
  - tests/test_vector_store.py
key_decisions:
  - StubEmbedder uses SHA-256 hash of text as numpy RNG seed for deterministic 64-dim float32 vectors
  - InMemoryVectorStore uses defaultdict keyed by owner_id; search is strictly scoped to owner namespace
  - Epsilon guard on vectors prevents cosine division-by-zero
patterns_established:
  - Protocol-based Embedder/VectorStore abstraction — real backends slot in without code changes
  - owner_id as mandatory namespace key on all upsert/search calls — mirrors JWT sub claim pattern from M002
observability_surfaces:
  - none
drill_down_paths:
  - milestones/M005/slices/S01/tasks/T01-SUMMARY.md
  - milestones/M005/slices/S01/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-31T07:17:35.524Z
blocker_discovered: false
---

# S01: Vector Store + Multi-Tenant Middleware

**knowledge/ package with protocol-based VectorStore + Embedder, per-owner_id namespace isolation, cosine-similarity ranking, and 6 passing pytest cases**

## What Happened

T01 created the knowledge/ package under src/mcp_agent_factory/knowledge/ with three files: embedder.py (Embedder Protocol + StubEmbedder using SHA-256-seeded 64-dim float32 numpy vectors with epsilon guard), vector_store.py (VectorStore Protocol + InMemoryVectorStore using defaultdict keyed by owner_id, cosine-similarity search strictly scoped to owner namespace), and __init__.py re-exporting all four symbols. T02 wrote tests/test_vector_store.py with 6 pytest cases covering upsert+query, cosine ranking, cross-tenant isolation, empty store, top_k, and StubEmbedder determinism — all 6 passed, and the existing 183-test suite continued to pass with no regressions.

## Verification

PYTHONPATH=src pytest tests/test_vector_store.py -v — 6/6 passed (exit 0). PYTHONPATH=src pytest tests/ -v --ignore=tests/test_vector_store.py — 183/183 passed (exit 0).

## Requirements Advanced

- R101 — Cross-tenant isolation enforced at InMemoryVectorStore.search — querying as bob after upserting as alice returns empty list, proven by test_cross_tenant_isolation
- R107 — Embedder and VectorStore defined as Protocols with in-memory numpy implementations; production backends slot in without code changes

## Requirements Validated

- R101 — test_cross_tenant_isolation: upsert as owner_id='alice', search as owner_id='bob' → [] — passes 6/6 in CI
- R107 — Protocol abstractions defined and exercised by 6 passing tests; StubEmbedder and InMemoryVectorStore are concrete swap-in implementations

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

StubEmbedder is a hash-projection stub — not semantically meaningful. Real sentence-transformer backend must be wired behind the Embedder protocol before production use. InMemoryVectorStore is not persistent across process restarts.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/knowledge/__init__.py` — Re-exports Embedder, StubEmbedder, VectorStore, InMemoryVectorStore
- `src/mcp_agent_factory/knowledge/embedder.py` — Embedder Protocol + StubEmbedder (SHA-256-seeded 64-dim float32 deterministic vectors)
- `src/mcp_agent_factory/knowledge/vector_store.py` — VectorStore Protocol + InMemoryVectorStore (defaultdict by owner_id, cosine-similarity search)
- `tests/test_vector_store.py` — 6 pytest cases: upsert+query, cosine ranking, cross-tenant isolation, empty store, top_k, StubEmbedder determinism
