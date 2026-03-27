---
id: S02
parent: M003
milestone: M003
provides:
  - UtilityFunction.score(task, profile) → float in [0,1]
  - AgentProfile Pydantic model: agent_id, capabilities, expertise_score, cost_per_unit
  - Auction.run(task, profiles) → BidResult with bids dict and winner_id
  - BidResult Pydantic model: task_id, bids, winner_id, winning_bid
requires:
  - slice: S01
    provides: AgentTask model
affects:
  - S03
  - S04
key_files:
  - src/mcp_agent_factory/economics/utility.py
  - src/mcp_agent_factory/economics/auction.py
  - tests/test_economics.py
key_decisions:
  - Tie-break: sort (score DESC, agent_id ASC) for deterministic stability
  - COMPLEXITY_PENALTY and COST_FACTOR as module-level constants
patterns_established:
  - UtilityFunction: pluggable scoring via AgentProfile + AgentTask
  - Auction: sorted tie-break pattern for deterministic winner selection
observability_surfaces:
  - event=utility_score JSON per agent per task
  - event=auction_result JSON with full bids dict and winner
drill_down_paths:
  - .gsd/milestones/M003/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M003/slices/S02/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-03-27T10:49:33.177Z
blocker_discovered: false
---

# S02: Economic Task Allocation (Utility + Auction)

**Economic task allocation via utility functions and auction bidding — proven by 12 passing tests.**

## What Happened

S02 delivered UtilityFunction and Auction in two lean tasks. Formula, tie-breaking, and observability all proven by 12 tests in 0.43s.

## Verification

python -m pytest tests/test_economics.py -v → 12 passed in 0.43s.

## Requirements Advanced

- R020 — UtilityFunction scores tasks; Auction allocates to highest bidder
- R021 — Auction.run() runs first-price sealed-bid with deterministic tie-breaking

## Requirements Validated

- R020 — test_utility_score_capability_match, test_utility_score_complexity_impact prove formula correctness
- R021 — test_auction_selects_highest_bidder, test_auction_tiebreak_by_agent_id prove deterministic allocation

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

UtilityFunction uses fixed penalty/cost coefficients — tunable but not configurable at runtime.

## Follow-ups

None.

## Files Created/Modified

- `src/mcp_agent_factory/economics/utility.py` — UtilityFunction and AgentProfile for task scoring
- `src/mcp_agent_factory/economics/auction.py` — Auction with BidResult — first-price sealed-bid with deterministic tie-breaking
- `tests/test_economics.py` — 12 economics tests
