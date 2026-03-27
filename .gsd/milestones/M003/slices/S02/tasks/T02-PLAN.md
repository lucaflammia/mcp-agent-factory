---
estimated_steps: 12
estimated_files: 1
skills_used: []
---

# T02: Economics tests

1. Create tests/test_economics.py
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

## Inputs

- `src/mcp_agent_factory/economics/utility.py`
- `src/mcp_agent_factory/economics/auction.py`

## Expected Output

- `tests/test_economics.py`

## Verification

python -m pytest tests/test_economics.py -v
