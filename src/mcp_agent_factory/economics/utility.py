"""
Utility function for economic task allocation.

Each agent has a profile (capabilities, expertise, cost). The utility function
scores how desirable a task is for a given agent profile — higher score means
the agent both wants the task and is well-suited to execute it.

Formula:
	utility = (expertise_match * expertise_score)
			  - (COMPLEXITY_PENALTY * task.complexity)
			  - (COST_FACTOR * cost_per_unit)

	expertise_match: 1.0 if task.required_capability in agent capabilities, else 0.3
	COMPLEXITY_PENALTY: 0.2  (penalizes agents for high-complexity tasks)
	COST_FACTOR: 0.1         (penalizes expensive agents)

Result is clamped to [0.0, 1.0].
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from mcp_agent_factory.agents.models import AgentTask

logger = logging.getLogger(__name__)

COMPLEXITY_PENALTY = 0.2
COST_FACTOR = 0.1
EXPERTISE_MATCH_FULL = 1.0
EXPERTISE_MATCH_PARTIAL = 0.3


class AgentProfile(BaseModel):
	"""Static capability and cost description for an agent."""
	agent_id: str
	capabilities: list[str] = Field(default_factory=list)
	expertise_score: float = Field(default=0.5, ge=0.0, le=1.0)
	cost_per_unit: float = Field(default=1.0, ge=0.0)


class UtilityFunction:
	"""
	Scores the desirability of a task for a given agent profile.

	Higher score = agent prefers to take this task.
	"""

	def score(self, task: AgentTask, profile: AgentProfile) -> float:
		"""
		Compute and return the utility score in [0.0, 1.0].
		"""
		expertise_match = (
			EXPERTISE_MATCH_FULL
			if task.required_capability in profile.capabilities
			else EXPERTISE_MATCH_PARTIAL
		)
		raw = (
			expertise_match * profile.expertise_score
			- COMPLEXITY_PENALTY * task.complexity
			- COST_FACTOR * profile.cost_per_unit
		)
		result = max(0.0, min(1.0, raw))

		logger.debug(json.dumps({
			"event": "utility_score",
			"agent_id": profile.agent_id,
			"task_id": task.id,
			"expertise_match": expertise_match,
			"raw_score": round(raw, 4),
			"clamped_score": round(result, 4),
		}))
		return result
