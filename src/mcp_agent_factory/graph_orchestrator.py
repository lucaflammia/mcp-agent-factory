"""
LangGraph State Machine Orchestrator — bounded, checkpointed execution graph.

Replaces the linear DeterministicOrchestrator with a finite state machine
that enforces:
  - Bounded depth (max iterations before forced termination)
  - Transactional state checkpointing (recoverable sessions)
  - Explicit state transitions (validate → plan → execute → evaluate → done/retry)

Gate: set ORCHESTRATOR_MODE=langgraph to use this path.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_ITERATIONS = int(os.getenv("GRAPH_MAX_ITERATIONS", "15"))


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class Phase(str, Enum):
	VALIDATE = "validate"
	PLAN = "plan"
	EXECUTE = "execute"
	EVALUATE = "evaluate"
	DONE = "done"
	FAILED = "failed"


class GraphState(TypedDict, total=False):
	"""Typed state dict flowing through the LangGraph graph."""
	task: str
	phase: str
	iteration: int
	plan: dict[str, Any] | None
	execution_result: dict[str, Any] | None
	evaluation_verdict: dict[str, Any] | None
	final_result: dict[str, Any] | None
	error: str | None
	tools: list[dict[str, Any]]
	history: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Structured output models for LLM nodes
# ---------------------------------------------------------------------------

class ExecutionPlan(BaseModel):
	"""LLM-generated execution plan validated via PydanticAI."""
	intent: str = Field(..., description="One-line goal description")
	steps: list[dict[str, Any]] = Field(
		..., min_length=1, description="Ordered tool calls: [{tool_name, arguments}]"
	)


class EvaluationResult(BaseModel):
	"""LLM critic's structured assessment of execution output."""
	passed: bool = Field(..., description="Whether the output meets the task requirements")
	score: float = Field(..., ge=0.0, le=1.0, description="Quality score 0-1")
	findings: list[str] = Field(default_factory=list, description="Issues found")
	revision_notes: str = Field(default="", description="What to fix on retry")


# ---------------------------------------------------------------------------
# Graph orchestrator
# ---------------------------------------------------------------------------

@dataclass
class GraphOrchestrator:
	"""
	LangGraph-based state machine with PydanticAI structured nodes.

	Nodes:
	  validate → plan → execute → evaluate → (done | retry→plan)

	Retry loops are bounded by MAX_ITERATIONS. State is checkpointed
	via LangGraph's RedisSaver for distributed session recovery.
	"""
	model_name: str = field(
		default_factory=lambda: os.getenv("PYDANTIC_AI_MODEL", "google-gla:gemini-2.5-flash")
	)
	max_iterations: int = field(default_factory=lambda: MAX_ITERATIONS)

	async def run(
		self,
		task: str,
		tools: list[dict[str, Any]],
		call_tool_fn,
		thread_id: str = "default",
	) -> dict[str, Any]:
		"""
		Execute the full graph-based orchestration loop.

		Returns the final GraphState as a dict.
		"""
		from langgraph.graph import StateGraph, END

		redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
		try:
			from langgraph.checkpoint.redis import RedisSaver
			checkpointer = RedisSaver.from_conn_string(redis_url)
		except Exception as exc:  # noqa: BLE001
			logger.warning("RedisSaver unavailable (%s), falling back to MemorySaver", exc)
			from langgraph.checkpoint.memory import MemorySaver
			checkpointer = MemorySaver()

		# -- Node functions --------------------------------------------------

		async def validate_node(state: GraphState) -> GraphState:
			if not state.get("task"):
				return {**state, "phase": Phase.FAILED.value, "error": "Empty task"}
			if not state.get("tools"):
				return {**state, "phase": Phase.FAILED.value, "error": "No tools available"}
			return {**state, "phase": Phase.PLAN.value}

		async def plan_node(state: GraphState) -> GraphState:
			from pydantic_ai import Agent

			tool_descriptions = "\n".join(
				f"- {t['name']}: {t.get('description', '')} (schema: {t.get('inputSchema', {})})"
				for t in state["tools"]
			)

			agent: Agent[None, ExecutionPlan] = Agent(
				self.model_name,
				system_prompt=(
					"You are a planning agent. Given a task and available tools, "
					"create an execution plan with the correct tool calls.\n\n"
					f"Available tools:\n{tool_descriptions}\n\n"
					"Each step in 'steps' MUST be a JSON object with exactly these two keys:\n"
					"  tool_name: the exact tool name string from the list above\n"
					"  arguments: a JSON object with the tool's required parameters\n"
					"Example: {\"tool_name\": \"add\", \"arguments\": {\"a\": 3, \"b\": 4}}"
				),
				result_type=ExecutionPlan,
				retries=2,
			)

			prompt = state["task"]
			history = state.get("history", [])
			if history:
				last = history[-1]
				prompt += (
					f"\n\nPrevious attempt failed. Evaluation: {last.get('evaluation', {})}"
					f"\nRevise your plan accordingly."
				)

			try:
				result = await agent.run(prompt)
				plan = result.data.model_dump()
			except Exception as exc:
				logger.error("planning failed: %s", exc)
				return {**state, "phase": Phase.FAILED.value, "error": f"Planning failed: {exc}"}

			return {**state, "phase": Phase.EXECUTE.value, "plan": plan}

		async def execute_node(state: GraphState) -> GraphState:
			import asyncio
			plan = state.get("plan")
			if not plan or not plan.get("steps"):
				return {**state, "phase": Phase.FAILED.value, "error": "No plan to execute"}

			results = []
			for step in plan["steps"]:
				# Accept multiple naming conventions LLMs use for the tool name
				tool_name = (
					step.get("tool_name")
					or step.get("name")
					or step.get("tool")
					or ""
				)
				# Accept multiple naming conventions for the arguments dict
				arguments = (
					step.get("arguments")
					or step.get("args")
					or step.get("parameters")
					or {}
				)
				try:
					if asyncio.iscoroutinefunction(call_tool_fn):
						result = await call_tool_fn(tool_name, arguments)
					else:
						result = call_tool_fn(tool_name, arguments)
					results.append({"tool": tool_name, "result": result, "success": True})
				except Exception as exc:
					results.append({"tool": tool_name, "error": str(exc), "success": False})

			return {
				**state,
				"phase": Phase.EVALUATE.value,
				"execution_result": {"steps": results},
			}

		async def evaluate_node(state: GraphState) -> GraphState:
			from pydantic_ai import Agent

			exec_result = state.get("execution_result", {})
			task = state["task"]

			agent: Agent[None, EvaluationResult] = Agent(
				self.model_name,
				system_prompt=(
					"You are an isolated critic evaluator. Assess whether the execution "
					"results satisfy the original task. Be strict — only pass if the "
					"task is fully and correctly completed."
				),
				result_type=EvaluationResult,
				retries=2,
			)

			try:
				result = await agent.run(
					f"Task: {task}\n\nExecution results: {exec_result}"
				)
				verdict = result.data.model_dump()
			except Exception as exc:
				logger.error("evaluation failed: %s", exc)
				verdict = {"passed": False, "score": 0.0, "findings": [str(exc)], "revision_notes": "Evaluation failed"}

			iteration = state.get("iteration", 0) + 1
			history = list(state.get("history", []))
			history.append({
				"iteration": iteration,
				"plan": state.get("plan"),
				"execution": exec_result,
				"evaluation": verdict,
			})

			if verdict.get("passed", False):
				# Extract final text result
				steps = exec_result.get("steps", [])
				final_text = ""
				for s in steps:
					r = s.get("result", {})
					try:
						final_text = r["content"][0]["text"]
					except (KeyError, IndexError, TypeError):
						final_text = str(r)

				return {
					**state,
					"phase": Phase.DONE.value,
					"iteration": iteration,
					"evaluation_verdict": verdict,
					"final_result": {"text": final_text, "iterations": iteration},
					"history": history,
				}

			if iteration >= self.max_iterations:
				return {
					**state,
					"phase": Phase.FAILED.value,
					"iteration": iteration,
					"evaluation_verdict": verdict,
					"error": f"Max iterations ({self.max_iterations}) reached without passing evaluation",
					"history": history,
				}

			# Retry — loop back to plan
			return {
				**state,
				"phase": Phase.PLAN.value,
				"iteration": iteration,
				"evaluation_verdict": verdict,
				"history": history,
			}

		# -- Routing ----------------------------------------------------------

		def route_after_validate(state: GraphState) -> str:
			return "plan" if state.get("phase") == Phase.PLAN.value else "end"

		def route_after_evaluate(state: GraphState) -> str:
			phase = state.get("phase", "")
			if phase == Phase.DONE.value:
				return "end"
			if phase == Phase.FAILED.value:
				return "end"
			return "plan"  # retry

		# -- Build graph ------------------------------------------------------

		graph = StateGraph(GraphState)
		graph.add_node("validate", validate_node)
		graph.add_node("plan", plan_node)
		graph.add_node("execute", execute_node)
		graph.add_node("evaluate", evaluate_node)

		graph.set_entry_point("validate")
		graph.add_conditional_edges("validate", route_after_validate, {"plan": "plan", "end": END})
		graph.add_edge("plan", "execute")
		graph.add_edge("execute", "evaluate")
		graph.add_conditional_edges("evaluate", route_after_evaluate, {"plan": "plan", "end": END})

		compiled = graph.compile(checkpointer=checkpointer)

		initial_state: GraphState = {
			"task": task,
			"phase": Phase.VALIDATE.value,
			"iteration": 0,
			"plan": None,
			"execution_result": None,
			"evaluation_verdict": None,
			"final_result": None,
			"error": None,
			"tools": tools,
			"history": [],
		}

		config = {"configurable": {"thread_id": thread_id}}
		final_state = await compiled.ainvoke(initial_state, config=config)
		return dict(final_state)
