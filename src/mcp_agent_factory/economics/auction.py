"""
Auction mechanism for economic task allocation.

Runs a first-price sealed-bid auction: each agent profile submits a bid
(its utility score for the task), and the Orchestrator allocates the task
to the highest bidder. Tie-breaking is deterministic: alphabetically lowest
agent_id wins.

Observability: logs the full bidding trace as a structured JSON line.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from mcp_agent_factory.agents.models import AgentTask
from mcp_agent_factory.economics.utility import AgentProfile, UtilityFunction

logger = logging.getLogger(__name__)


class BidResult(BaseModel):
	"""Result of an auction run."""
	task_id: str
	bids: dict[str, float]          # agent_id → bid score
	winner_id: str
	winning_bid: float


class Auction:
	"""
	First-price sealed-bid auction for task allocation.

	Each agent profile scores the task via UtilityFunction.
	The highest scorer wins. Ties broken by alphabetically lowest agent_id.
	"""

	def __init__(self) -> None:
		self._utility = UtilityFunction()

	def run(self, task: AgentTask, profiles: list[AgentProfile]) -> BidResult:
		"""
		Run the auction and return the winner.

		Raises ValueError if *profiles* is empty.
		"""
		if not profiles:
			raise ValueError("Auction requires at least one agent profile")

		bids: dict[str, float] = {
			profile.agent_id: self._utility.score(task, profile)
			for profile in profiles
		}

		# Winner: highest score; tie-break by alphabetically lowest agent_id
		winner_id = max(
			bids,
			key=lambda aid: (bids[aid], -ord(aid[0]) if aid else 0),
		)
		# Re-implement tie-break cleanly: sort descending by score, then ascending by id
		sorted_agents = sorted(bids.items(), key=lambda kv: (-kv[1], kv[0]))
		winner_id = sorted_agents[0][0]
		winning_bid = bids[winner_id]

		logger.debug(json.dumps({
			"event": "auction_result",
			"task_id": task.id,
			"task_name": task.name,
			"bids": {k: round(v, 4) for k, v in bids.items()},
			"winner_id": winner_id,
			"winning_bid": round(winning_bid, 4),
		}))

		return BidResult(
			task_id=task.id,
			bids=bids,
			winner_id=winner_id,
			winning_bid=winning_bid,
		)
