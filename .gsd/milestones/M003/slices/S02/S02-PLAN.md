# S02: Economic Task Allocation (Utility + Auction)

**Goal:** Implement UtilityFunction, AgentProfile, and Auction. Each agent scores a task using a utility function; the Orchestrator runs the auction and allocates to the highest bidder. Deterministic, no LLM needed.
**Demo:** After this: pytest tests/test_economics.py -v passes — utility functions score tasks, auction selects highest bidder, bidding trace logged.

## Tasks
- [x] **T01: UtilityFunction and Auction for deterministic economic task allocation with structured bidding trace logging.** — 1. Create src/mcp_agent_factory/economics/__init__.py
2. Create src/mcp_agent_factory/economics/utility.py:
   - AgentProfile(BaseModel): agent_id, capabilities (list[str]), expertise_score (float 0-1), cost_per_unit (float)
   - UtilityFunction:
     - score(task: AgentTask, profile: AgentProfile) -> float
     - Formula: utility = (expertise_match * expertise_score) - (complexity_penalty * task.complexity) - (cost_factor * profile.cost_per_unit)
     - expertise_match = 1.0 if task.required_capability in profile.capabilities else 0.3
     - complexity_penalty = 0.2
     - cost_factor = 0.1
     - Clamp result to [0.0, 1.0]
     - Log score via structured JSON logger.debug
3. Create src/mcp_agent_factory/economics/auction.py:
   - BidResult(BaseModel): task_id, bids (dict[str, float]), winner_id (str), winning_bid (float)
   - Auction:
     - run(task: AgentTask, profiles: list[AgentProfile]) -> BidResult
     - Scores each profile via UtilityFunction.score()
     - Winner = highest score; tie-break by agent_id (alphabetical, lowest wins)
     - Logs bidding trace as structured JSON: {event: auction_result, task_id, bids, winner_id}
     - Raises ValueError if profiles list is empty
  - Estimate: 20min
  - Files: src/mcp_agent_factory/economics/
  - Verify: python -c "from mcp_agent_factory.economics.auction import Auction; from mcp_agent_factory.economics.utility import UtilityFunction, AgentProfile; print('imports ok')"
- [x] **T02: 12 economics tests — utility scoring, auction allocation, tie-breaking, structured logging — all passing in 0.43s.** — 1. Create tests/test_economics.py
2. Test cases:
   - test_utility_score_capability_match: matching capability produces higher score than no match
   - test_utility_score_high_cost_lowers_score: profile with high cost_per_unit scores lower
   - test_utility_score_clamped_to_unit_interval: score always in [0.0, 1.0]
   - test_utility_score_complexity_impact: higher task complexity lowers score
   - test_auction_selects_highest_bidder: 3 profiles, known scores, correct winner
   - test_auction_tiebreak_by_agent_id: equal scores, alphabetically lowest agent_id wins
   - test_auction_empty_profiles_raises: ValueError on empty list
   - test_auction_bid_result_contains_all_bids: BidResult.bids has entry for every profile
   - test_auction_logs_bidding_trace: caplog verifies auction_result JSON event
   - test_single_agent_wins_auction: one profile, always wins
  - Estimate: 20min
  - Files: tests/test_economics.py
  - Verify: python -m pytest tests/test_economics.py -v
