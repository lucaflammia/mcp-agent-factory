"""
MultiAgentOrchestrator — coordinates the Analyst→Writer pipeline.

Manages state transitions:
  1. Run AnalystAgent → AnalysisResult
  2. Persist AnalysisResult to Redis Session Manager
  3. Read back from Redis (proves durability)
  4. Run WriterAgent → ReportResult

MCP Context logs every state transition so the full execution trace
is available for debugging and observability.
"""
from __future__ import annotations

from mcp_agent_factory.agents.analyst import AnalystAgent
from mcp_agent_factory.agents.models import AgentTask, MCPContext, ReportResult
from mcp_agent_factory.agents.writer import WriterAgent
from mcp_agent_factory.session.manager import RedisSessionManager


class MultiAgentOrchestrator:
	"""
	Coordinates the AnalystAgent → WriterAgent pipeline.

	Parameters
	----------
	session :
		RedisSessionManager for cross-agent state persistence.
	"""

	def __init__(self, session: RedisSessionManager) -> None:
		self._session = session
		self._analyst = AnalystAgent()
		self._writer = WriterAgent()

	async def run_pipeline(self, task: AgentTask, ctx: MCPContext) -> ReportResult:
		"""
		Execute the full Analyst → Redis handoff → Writer pipeline.

		State transitions logged via ctx at each step.
		"""
		ctx.log(f"orchestrator: starting pipeline for task '{task.name}'")

		# Step 1 — Analyst phase
		ctx.log("orchestrator: dispatching to AnalystAgent")
		analysis = await self._analyst.run(task, ctx)

		# Step 2 — Persist handoff in Redis
		ctx.log(f"orchestrator: persisting handoff to Redis (key={analysis.session_key})")
		await self._session.set(analysis.session_key, analysis.model_dump())

		# Step 3 — Read back to prove durability (simulates Writer fetching from Redis)
		ctx.log("orchestrator: reading handoff from Redis")
		raw = await self._session.get(analysis.session_key)
		if raw is None:
			raise RuntimeError(f"Redis handoff missing for key {analysis.session_key!r}")

		from mcp_agent_factory.agents.models import AnalysisResult
		restored = AnalysisResult(**raw)

		# Step 4 — Writer phase
		ctx.log("orchestrator: dispatching to WriterAgent")
		report = await self._writer.run(restored, ctx)

		ctx.log("orchestrator: pipeline complete")
		return report
