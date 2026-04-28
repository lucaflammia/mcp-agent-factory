---
slice: S03
milestone: M009
title: Context Pruner with Cosine Filtering
status: complete
---

# S03 Summary — Context Pruner with Cosine Filtering

## One-liner
ContextPruner filters message chunks by cosine similarity, dropping irrelevant content and passing on-topic chunks through to the LLM.

## What was built
- `src/mcp_agent_factory/gateway/pruner.py` — `ContextPruner` with `prune(query, chunks, embedder, threshold)` method
- Embeds query and each chunk via the `Embedder` protocol, computes cosine similarity, returns filtered list
- Empty-context fallthrough (no chunks above threshold) returns empty list without error
- Threshold is configurable per-call; defaults to 0.7

## Verification
`pytest tests/test_m009_s03.py` — 14 passed.

Confirmed:
- Below-threshold chunk dropped
- On-topic chunk above threshold passes
- Empty input → empty output
- threshold=0.0 passes all chunks
- All edge cases covered

## Requirements advanced
- R036: Context pruner drops irrelevant chunks (validated)
