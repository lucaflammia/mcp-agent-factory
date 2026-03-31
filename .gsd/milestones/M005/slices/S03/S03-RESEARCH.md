# S03: Knowledge-Augmented Auction — Research

**Date:** 2026-03-31
**Status:** Ready for planning

## Summary

S03 adds a shallow vector probe to the auction bidding cycle and a +20% utility boost for agents with `knowledge_retrieval` capability when relevant context is found. The work touches two existing files (`economics/utility.py`, `economics/auction.py`) and adds one new test file. The knowledge/ package from S01 is already fully in place — S03 just wires it into the economics layer.

This is light, well-scoped work: the existing code patterns are clear, the change surface is small, and there are no new dependencies or abstractions needed.

## Recommendation

Inject an optional `VectorStore` + query string into `Auction.run()`. The auction performs a shallow probe (top_k=1 is sufficient to determine "context found"). Pass a boolean `knowledge_context_found` flag down to `UtilityFunction.score()`. If true and the agent's capabilities include `knowledge_retrieval`, multiply raw score by 1.2, then clamp to 1.0 as usual.

Keep the existing `score()` signature backward-compatible by adding optional parameters (default `None`/`False`). All existing tests continue to pass without modification.

## Implementation Landscape

### Key Files

- `src/mcp_agent_factory/economics/utility.py` — `UtilityFunction.score(task, profile)` needs a `knowledge_boost: bool = False` parameter. When `True` and `"knowledge_retrieval" in profile.capabilities`, multiply raw score by 1.2 before clamping.
- `src/mcp_agent_factory/economics/auction.py` — `Auction.__init__` and `Auction.run()` need an optional `VectorStore` + `owner_id` injection. Before computing bids, do a `store.search(query=task.name, owner_id=owner_id, top_k=1)` — if results non-empty, `knowledge_boost=True` is passed to utility scoring for profiles with `knowledge_retrieval`.
- `src/mcp_agent_factory/knowledge/vector_store.py` — Already exists (S01). Import `VectorStore`, `InMemoryVectorStore`.
- `tests/test_knowledge_auction.py` — New test file. Use `InMemoryVectorStore` + `StubEmbedder` to pre-populate context, then verify the +20% boost applies (or not).
- `tests/test_economics.py` — Must continue to pass without changes (backward-compat validation).

### Build Order

1. Update `UtilityFunction.score()` with `knowledge_boost` parameter — self-contained, no dependencies.
2. Update `Auction.run()` to accept optional vector store and perform shallow probe — depends on step 1.
3. Write `tests/test_knowledge_auction.py` — depends on both steps above.
4. Verify `pytest tests/test_economics.py tests/test_knowledge_auction.py -v` all green.

### Verification Approach

```
PYTHONPATH=src pytest tests/test_knowledge_auction.py -v   # new tests pass
PYTHONPATH=src pytest tests/test_economics.py -v           # no regressions
```

## Constraints

- `UtilityFunction.score()` signature must remain backward-compatible — existing callers pass no knowledge args.
- `Auction.run()` must remain backward-compatible — `store` and `owner_id` must have defaults (`None`).
- Tab indentation (project convention).
- `raw_score * 1.2`, then `min(1.0, ...)` — clamp after boost, not before.
- No new dependencies — only imports from `knowledge/` (already in-tree).

## Common Pitfalls

- **Boost applied before clamping** — multiply by 1.2 on `raw` before `max(0.0, min(1.0, ...))`, not on the already-clamped value.
- **Probe owner_id** — the auction probe needs an `owner_id`; tests should pass a test owner string; production will use JWT sub. Make it a required param when store is provided, or default to empty string with a guard.
- **Import cycle** — `auction.py` importing from `knowledge/` is fine (one-way dependency); no cycle risk.
