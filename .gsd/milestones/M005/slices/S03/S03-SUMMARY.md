---
id: S03
parent: M005
milestone: M005
provides:
  - knowledge_boost parameter on UtilityFunction.score()
  - store/query_vector/owner_id optional parameters on Auction.run()
  - 8-case test suite in tests/test_knowledge_auction.py
requires:
  - slice: S01
    provides: InMemoryVectorStore and VectorStore protocol used in auction probe
affects:
  - S04
key_files:
  - src/mcp_agent_factory/economics/utility.py
  - src/mcp_agent_factory/economics/auction.py
  - tests/test_knowledge_auction.py
key_decisions:
  - Auction probe uses query_vector (np.ndarray) matching actual VectorStore.search() signature, not a string query as described in plan
patterns_established:
  - knowledge_boost flag on UtilityFunction.score() — backward-compatible optional bool, applied as raw*1.2 before clamp
  - Auction optional store/query_vector/owner_id parameters — all default to None/'', keeping existing call sites unmodified
observability_surfaces:
  - none
drill_down_paths:
  - .gsd/milestones/M005/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M005/slices/S03/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-31T07:32:41.961Z
blocker_discovered: false
---

# S03: Knowledge-Augmented Auction

**Shallow vector probe wired into Auction.run() with +20% utility boost for knowledge_retrieval agents; all 20 tests pass with zero regressions**

## What Happened

T01 modified UtilityFunction.score() to accept an optional knowledge_boost: bool = False parameter — when True and the profile has 'knowledge_retrieval' in capabilities, raw score is multiplied by 1.2 before clamping. Auction.__init__ and Auction.run() were extended with store: VectorStore | None = None, query_vector: np.ndarray | None = None, and owner_id: str = '' parameters. Before computing bids, if store and query_vector are both provided, the probe calls store.search(query_vector, owner_id, top_k=1); a non-empty result triggers knowledge_boost=True for each capable profile. One deviation from the plan: the plan described store.search(query=task.name) as a string query, but actual VectorStore.search() takes query_vector: np.ndarray — the parameter was adapted accordingly. T01 also created tests/test_knowledge_auction.py with 8 test cases covering the boost path, no-boost fallback, backward compatibility, graceful degradation, and clamping. T02 confirmed the full suite of 20 tests (8 new + 12 existing economics) pass cleanly.

## Verification

PYTHONPATH=src pytest tests/test_knowledge_auction.py tests/test_economics.py -v → 20 passed in 1.04s. Inline verification command (assert s_yes > s_no) → OK.

## Requirements Advanced

- R103 — Implemented +20% utility score boost (raw*1.2, clamped to 1.0) for agents with knowledge_retrieval capability when vector probe returns results

## Requirements Validated

- R103 — test_auction_with_populated_store_boosts_kr and test_knowledge_boost_applied confirm boost is applied; test_no_boost_without_capability and test_auction_with_empty_store_no_boost confirm it's not applied spuriously; 20/20 tests pass

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

Plan described store.search(query=task.name) with a string query argument. Actual VectorStore.search() signature (from S01) takes query_vector: np.ndarray. Auction.run() was extended with query_vector parameter instead; callers must supply an embedded vector, not a raw string.

## Known Limitations

Callers of Auction.run() who want the boost must supply a pre-embedded query_vector — there is no string-to-vector convenience path in the auction layer. S04 (LibrarianAgent) will need to embed the task query before passing it to the auction.

## Follow-ups

S04 must embed task.name (or a task description) into a query_vector before calling Auction.run() if it wants the boost to apply. The StubEmbedder from S01 is available for tests.

## Files Created/Modified

- `src/mcp_agent_factory/economics/utility.py` — Added knowledge_boost: bool = False parameter to score(); applies raw*1.2 before clamp when True and profile has knowledge_retrieval capability
- `src/mcp_agent_factory/economics/auction.py` — Added store, query_vector, owner_id optional parameters to __init__ and run(); probes store before bidding and sets knowledge_boost flag
- `tests/test_knowledge_auction.py` — 8 test cases covering boost path, no-boost fallback, backward compat, graceful degradation, and clamping
