"""
WriterAgent — specialized agent for report generation.

Receives an AnalysisResult from the Redis Session Manager (via the Orchestrator)
and produces a formatted professional report as ReportResult.

Observability: uses MCPContext to log start and completion.
"""
from __future__ import annotations

from mcp_agent_factory.agents.models import AnalysisResult, MCPContext, ReportResult


class WriterAgent:
	"""
	Generates a structured report from AnalysisResult.

	The report includes: an executive summary, a metrics table, and
	trend observations — deterministic formatting, no LLM needed.

	If *bus* is provided, publishes an ``agent.output.final`` message after
	each report so downstream workers (e.g. IngestionWorker) can process it.
	"""

	def __init__(self, bus=None) -> None:
		self._bus = bus

	async def run(self, analysis: AnalysisResult, ctx: MCPContext, *, owner_id: str = "") -> ReportResult:
		ctx.log(f"writer: generating report for session '{analysis.session_key}'")

		trace: list[str] = []
		lines: list[str] = []

		# Header
		lines.append("# Analysis Report")
		lines.append("")

		# Executive summary
		lines.append("## Executive Summary")
		lines.append(analysis.summary)
		lines.append("")
		trace.append("wrote executive summary")

		# Metrics table
		if analysis.metrics:
			lines.append("## Metrics")
			lines.append("| Metric | Value |")
			lines.append("|--------|-------|")
			for name, value in sorted(analysis.metrics.items()):
				lines.append(f"| {name} | {value:.4f} |")
			lines.append("")
			trace.append(f"wrote metrics table ({len(analysis.metrics)} entries)")

		# Trends
		if analysis.trends:
			lines.append("## Trend Observations")
			for trend in analysis.trends:
				lines.append(f"- {trend}")
			lines.append("")
			trace.append(f"wrote {len(analysis.trends)} trend observations")

		report_text = "\n".join(lines)
		ctx.log(f"writer: report complete ({len(report_text)} chars)")

		if self._bus is not None:
			from mcp_agent_factory.messaging.bus import AgentMessage
			self._bus.publish(
				"agent.output.final",
				AgentMessage(
					topic="agent.output.final",
					sender="writer-agent",
					content={
						"text": report_text,
						"owner_id": owner_id,
						"session_key": analysis.session_key,
					},
				),
			)

		return ReportResult(
			session_key=analysis.session_key,
			report_text=report_text,
			agent_trace=trace,
		)
