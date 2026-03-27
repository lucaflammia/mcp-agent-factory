# S02: Economic Task Allocation (Utility + Auction) — UAT

**Milestone:** M003
**Written:** 2026-03-27T10:49:33.178Z

## UAT: Economic Task Allocation\n\n```python\nfrom mcp_agent_factory.agents.models import AgentTask\nfrom mcp_agent_factory.economics.utility import AgentProfile, UtilityFunction\nfrom mcp_agent_factory.economics.auction import Auction\n\ntask = AgentTask(name=\"analyse\", payload={}, complexity=0.5, required_capability=\"analysis\")\nprofiles = [\n    AgentProfile(agent_id=\"analyst\", capabilities=[\"analysis\"], expertise_score=0.9, cost_per_unit=0.5),\n    AgentProfile(agent_id=\"writer\", capabilities=[\"writing\"], expertise_score=0.8, cost_per_unit=0.3),\n]\nresult = Auction().run(task, profiles)\nprint(f\"Winner: {result.winner_id} (bid={result.winning_bid:.3f})\")\nprint(f\"All bids: {result.bids}\")\n```\nExpected: analyst wins with higher bid.
