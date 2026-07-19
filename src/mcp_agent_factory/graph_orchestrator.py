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


# Tool names that require human approval before execution (destructive operations).
DESTRUCTIVE_TOOL_PATTERNS: list[str] = [
	"write", "delete", "drop", "update", "insert", "exec", "run", "deploy",
]


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
	# When True the graph is interrupted and paused in Redis,
	# awaiting an out-of-band approval signal before resuming.
	require_user_approval: bool
	hitl_reason: str | None


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
		checkpointer = None
		redis_saver_ctx = None
		try:
			from langgraph.checkpoint.redis import RedisSaver
			redis_saver_ctx = RedisSaver.from_conn_string(redis_url)
			checkpointer = redis_saver_ctx.__enter__()
			checkpointer.setup()
		except Exception as exc:  # noqa: BLE001
			logger.warning("RedisSaver unavailable (%s), falling back to MemorySaver", exc)
			redis_saver_ctx = None
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
			import json
			import re
			from pydantic_ai import Agent

			tool_descriptions = "\n".join(
				f"- {t['name']}: {t.get('description', '')} args: {list((t.get('inputSchema') or {}).get('properties', {}).keys())}"
				for t in state["tools"]
			)

			system = (
				"You are a planning agent. Output a JSON object with exactly two keys:\n"
				"  intent: one-line goal string\n"
				"  steps: array of objects each with tool_name and arguments keys\n\n"
				f"Available tools:\n{tool_descriptions}\n\n"
				"Example for 'add 3 and 4':\n"
				'{"intent": "add two numbers", "steps": [{"tool_name": "add", "arguments": {"a": 3, "b": 4}}]}'
			)

			prompt = state["task"]
			history = state.get("history", [])
			if history:
				last = history[-1]
				prompt += (
					f"\n\nPrevious attempt failed. Evaluation: {last.get('evaluation', {})}"
					f"\nRevise your plan accordingly."
				)

			# Primary path: PydanticAI structured output
			try:
				agent: Agent[None, ExecutionPlan] = Agent(
					self.model_name,
					system_prompt=system,
					result_type=ExecutionPlan,
					retries=2,
				)
				result = await agent.run(prompt)
				plan = result.data.model_dump()
				logger.info("plan_node: structured plan with %d steps", len(plan.get("steps", [])))
				return {**state, "phase": Phase.EXECUTE.value, "plan": plan}
			except Exception as exc:
				logger.warning("plan_node: PydanticAI structured output failed (%s), trying JSON fallback", exc)

			# Fallback: plain LLM call + JSON extraction
			try:
				fallback_agent: Agent[None, str] = Agent(
					self.model_name,
					system_prompt=system,
				)
				raw = await fallback_agent.run(prompt)
				raw_text = raw.data if isinstance(raw.data, str) else str(raw.data)
				# Extract first JSON object from the response
				match = re.search(r'\{.*\}', raw_text, re.DOTALL)
				if not match:
					raise ValueError("No JSON object found in LLM response")
				plan_dict = json.loads(match.group())
				plan = ExecutionPlan(**plan_dict).model_dump()
				logger.info("plan_node: fallback plan with %d steps", len(plan.get("steps", [])))
				return {**state, "phase": Phase.EXECUTE.value, "plan": plan}
			except Exception as exc2:
				logger.error("plan_node: both planning paths failed: %s", exc2)
				return {**state, "phase": Phase.FAILED.value, "error": f"Planning failed: {exc2}"}

		async def execute_node(state: GraphState) -> GraphState:
			import asyncio
			from langgraph.types import interrupt as lg_interrupt

			# Pass through if planning already failed
			if state.get("phase") == Phase.FAILED.value:
				return state

			plan = state.get("plan")
			if not plan or not plan.get("steps"):
				return {**state, "phase": Phase.FAILED.value, "error": "No plan to execute"}

			# Scan for destructive tool calls and pause for human approval.
			for step in plan["steps"]:
				tool_name = (
					step.get("tool_name") or step.get("name") or step.get("tool") or ""
				).lower()
				if any(pat in tool_name for pat in DESTRUCTIVE_TOOL_PATTERNS):
					reason = f"Tool '{tool_name}' requires human approval before execution."
					logger.info("HITL interrupt triggered: %s", reason)
					# Persist the interrupt reason into state before suspending.
					# LangGraph serialises current state to Redis, then raises
					# GraphInterrupt — the caller resumes by replaying with approval.
					lg_interrupt({"reason": reason, "plan": plan})
					# Execution continues here only after external approval is received.

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
					"require_user_approval": False,
					"hitl_reason": None,
				}

			# Critical system constraint failures (score==0) require
			# human intervention rather than an autonomous retry.
			is_critical_failure = verdict.get("score", 1.0) == 0.0
			if is_critical_failure:
				from langgraph.types import interrupt as lg_interrupt
				hitl_reason = (
					"Critical evaluation failure: the evaluator scored the output 0. "
					"Human review is required before the graph may retry. "
					f"Findings: {verdict.get('findings', [])}"
				)
				logger.warning("HITL interrupt on critical failure: %s", hitl_reason)
				lg_interrupt({"reason": hitl_reason, "verdict": verdict})
				# Resumes here after human approves a retry.

			if iteration >= self.max_iterations:
				return {
					**state,
					"phase": Phase.FAILED.value,
					"iteration": iteration,
					"evaluation_verdict": verdict,
					"error": f"Max iterations ({self.max_iterations}) reached without passing evaluation",
					"history": history,
					"require_user_approval": False,
					"hitl_reason": None,
				}

			# Retry — loop back to plan
			return {
				**state,
				"phase": Phase.PLAN.value,
				"iteration": iteration,
				"evaluation_verdict": verdict,
				"history": history,
				"require_user_approval": False,
				"hitl_reason": None,
			}

		# -- Routing ----------------------------------------------------------

		def route_after_validate(state: GraphState) -> str:
			return "plan" if state.get("phase") == Phase.PLAN.value else "end"

		def route_after_plan(state: GraphState) -> str:
			return "end" if state.get("phase") == Phase.FAILED.value else "execute"

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
		graph.add_conditional_edges("plan", route_after_plan, {"execute": "execute", "end": END})
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
			"require_user_approval": False,
			"hitl_reason": None,
		}

		config = {"configurable": {"thread_id": thread_id}}
		try:
			final_state = await compiled.ainvoke(initial_state, config=config)
		finally:
			if redis_saver_ctx is not None:
				try:
					redis_saver_ctx.__exit__(None, None, None)
				except Exception:
					pass
		return dict(final_state)
