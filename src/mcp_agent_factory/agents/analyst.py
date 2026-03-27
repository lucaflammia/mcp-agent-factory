"""
AnalystAgent — specialized agent for data processing and metric extraction.

Receives an AgentTask with a payload dict, extracts numeric values as metrics,
generates trend observations, and produces an AnalysisResult for handoff to
WriterAgent via the Redis Session Manager.

Observability: uses MCPContext to log start, progress, and completion.
"""
from __future__ import annotations

from mcp_agent_factory.agents.models import AgentTask, AnalysisResult, MCPContext


class AnalystAgent:
	"""
	Processes raw task payload and produces structured AnalysisResult.

	Metric extraction: any float/int value in task.payload becomes a metric.
	Trend generation: derives two trend strings from the highest and lowest
	metric values (deterministic, no LLM needed).
	"""

	async def run(self, task: AgentTask, ctx: MCPContext) -> AnalysisResult:
		ctx.log(f"analyst: starting task '{task.name}'")
		ctx.report_progress(0.1, "extracting metrics from payload")

		# Extract numeric values from payload as metrics
		metrics: dict[str, float] = {}
		for key, value in task.payload.items():
			if isinstance(value, (int, float)):
				metrics[key] = float(value)

		ctx.report_progress(0.6, "generating trend observations")

		# Generate deterministic trend observations
		trends: list[str] = []
		if metrics:
			max_key = max(metrics, key=lambda k: metrics[k])
			min_key = min(metrics, key=lambda k: metrics[k])
			trends.append(f"'{max_key}' shows the highest value at {metrics[max_key]:.2f}")
			if max_key != min_key:
				trends.append(f"'{min_key}' shows the lowest value at {metrics[min_key]:.2f}")
		else:
			trends.append("No numeric metrics found in payload")

		summary = (
			f"Analyzed {len(metrics)} metric(s) from task '{task.name}'. "
			f"Key finding: {trends[0] if trends else 'no data'}."
		)

		ctx.report_progress(1.0, "analysis complete")
		ctx.log(f"analyst: produced {len(metrics)} metrics, {len(trends)} trends")

		return AnalysisResult(
			session_key=task.id,
			metrics=metrics,
			trends=trends,
			summary=summary,
		)
