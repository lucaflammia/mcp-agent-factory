"""
AnalystAgent — specialized agent for data processing and metric extraction.

Provides two execution modes:

1. ``run()`` — legacy dict-based mode: extracts numeric metrics from task.payload,
   generates trend observations. Used by the multi-agent pipeline (M003+).

2. ``analyze_document()`` — document analysis mode: reads a local PDF via
   file_context_extractor, prunes context, scrubs PII, then routes to an LLM
   via UnifiedRouter (provider_factory). Used by the M010 demo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp_agent_factory.agents.models import AgentTask, AnalysisResult, MCPContext
from mcp_agent_factory.gateway.router import LLMRequest, provider_factory
from mcp_agent_factory.gateway.pruner import ContextPruner
from mcp_agent_factory.gateway.validation import PIIGate, _default_allow_list
from mcp_agent_factory.knowledge.embedder import StubEmbedder
from mcp_agent_factory.knowledge.pdf_tool import file_context_extractor


@dataclass
class DocumentAnalysisTask:
	"""Input for analyze_document(): points to a local PDF and a natural-language query."""
	pdf_path: str
	query: str = "Identify key KPIs and risk areas"
	max_pages: int = 20
	extra_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentAnalysisResult:
	"""Output from analyze_document()."""
	summary: str
	provider: str
	input_tokens: int
	output_tokens: int
	cost_usd: float
	pages_read: int
	total_pages: int
	chunks_before_pruning: int
	chunks_after_pruning: int


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

	async def analyze_document(
		self,
		task: DocumentAnalysisTask,
		ctx: MCPContext | None = None,
	) -> DocumentAnalysisResult:
		"""Full document analysis pipeline: extract → prune → scrub → LLM.

		Steps:
		  1. Extract text snippets from PDF via file_context_extractor (local, no egress).
		  2. Prune snippets to those relevant to task.query via ContextPruner + StubEmbedder.
		  3. Scrub PII from the pruned context via PIIGate.
		  4. Route to the active LLM provider via provider_factory().
		  5. Return a DocumentAnalysisResult with the LLM summary and telemetry.
		"""
		def _log(msg: str) -> None:
			if ctx:
				ctx.log(msg)

		_log(f"analyst: reading PDF '{task.pdf_path}'")

		extraction = file_context_extractor(task.pdf_path, query=task.query, max_pages=task.max_pages)
		raw_chunks = [s["text"] for s in extraction["snippets"]]
		chunks_before = len(raw_chunks)

		_log(f"analyst: extracted {chunks_before} pages, pruning for relevance")

		pruner = ContextPruner()
		pruned = pruner.prune(task.query, raw_chunks, StubEmbedder())
		# Fall back to all chunks if pruner discards everything (low-signal stub embedder)
		if not pruned:
			pruned = raw_chunks
		chunks_after = len(pruned)

		_log(f"analyst: {chunks_before} → {chunks_after} chunks after pruning")

		gate = PIIGate()
		context_text = "\n\n".join(pruned)
		allow = _default_allow_list() | frozenset({"context"})
		scrubbed = gate.scrub({"context": context_text}, allow_list=allow)
		clean_context = scrubbed["context"]

		prompt = (
			f"You are a financial analyst. Based on the following document excerpts, "
			f"answer this query: {task.query}\n\n"
			f"Document excerpts:\n{clean_context}\n\n"
			f"Provide a structured response with:\n"
			f"1. Key KPIs found (with values if present)\n"
			f"2. Risk areas identified\n"
			f"3. Brief executive summary"
		)

		_log(f"analyst: routing to LLM (provider={_current_provider()})")

		router = provider_factory()
		req = LLMRequest(tool_name="analyze_document", args={}, prompt=prompt)
		response = await router.route(req)

		_log("analyst: LLM response received")

		return DocumentAnalysisResult(
			summary=response["content"],
			provider=response.get("model", "unknown"),
			input_tokens=response.get("input_tokens", 0),
			output_tokens=response.get("output_tokens", 0),
			cost_usd=response.get("cost_usd", 0.0),
			pages_read=extraction["pages_read"],
			total_pages=extraction["total_pages"],
			chunks_before_pruning=chunks_before,
			chunks_after_pruning=chunks_after,
		)


def _current_provider() -> str:
	"""Return the active LLM_PROVIDER env var for logging."""
	import os
	return os.environ.get("LLM_PROVIDER", "anthropic").lower()
