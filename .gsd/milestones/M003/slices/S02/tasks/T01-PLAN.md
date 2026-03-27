---
estimated_steps: 19
estimated_files: 1
skills_used: []
---

# T01: UtilityFunction, AgentProfile, and Auction

1. Create src/mcp_agent_factory/economics/__init__.py
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

## Inputs

- `src/mcp_agent_factory/agents/models.py`

## Expected Output

- `src/mcp_agent_factory/economics/__init__.py`
- `src/mcp_agent_factory/economics/utility.py`
- `src/mcp_agent_factory/economics/auction.py`

## Verification

python -c "from mcp_agent_factory.economics.auction import Auction; from mcp_agent_factory.economics.utility import UtilityFunction, AgentProfile; print('imports ok')"
