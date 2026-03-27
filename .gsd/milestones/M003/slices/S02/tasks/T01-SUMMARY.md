---
id: T01
parent: S02
milestone: M003
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/economics/utility.py", "src/mcp_agent_factory/economics/auction.py"]
key_decisions: ["Tie-break by sorting (score DESC, agent_id ASC) — more readable than custom comparator", "COMPLEXITY_PENALTY=0.2, COST_FACTOR=0.1 as module-level constants for easy tuning"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "imports ok."
completed_at: 2026-03-27T10:49:09.647Z
blocker_discovered: false
---

# T01: UtilityFunction and Auction for deterministic economic task allocation with structured bidding trace logging.

> UtilityFunction and Auction for deterministic economic task allocation with structured bidding trace logging.

## What Happened
---
id: T01
parent: S02
milestone: M003
key_files:
  - src/mcp_agent_factory/economics/utility.py
  - src/mcp_agent_factory/economics/auction.py
key_decisions:
  - Tie-break by sorting (score DESC, agent_id ASC) — more readable than custom comparator
  - COMPLEXITY_PENALTY=0.2, COST_FACTOR=0.1 as module-level constants for easy tuning
duration: ""
verification_result: passed
completed_at: 2026-03-27T10:49:09.673Z
blocker_discovered: false
---

# T01: UtilityFunction and Auction for deterministic economic task allocation with structured bidding trace logging.

**UtilityFunction and Auction for deterministic economic task allocation with structured bidding trace logging.**

## What Happened

UtilityFunction scores tasks by expertise match, complexity penalty, and cost. Auction runs sealed-bid allocation with deterministic tie-breaking. Both emit structured JSON log lines.

## Verification

imports ok.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -c "from mcp_agent_factory.economics.auction import Auction; print('ok')"` | 0 | ✅ pass | 200ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/economics/utility.py`
- `src/mcp_agent_factory/economics/auction.py`


## Deviations
None.

## Known Issues
None.
