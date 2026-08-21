"""
LangGraph State Machine Orchestrator — bounded, checkpointed execution graph.

Replaces the linear DeterministicOrchestrator with a finite state machine
that enforces:
  - Bounded depth (max iterations before forced termination)
  - Transactional state checkpointing (recoverable sessions)
  - Explicit state transitions (validate → plan → execute → evaluate → done/retry)
  - Typed plan steps with output chaining via {{steps.<id>.output}} references
  - DAG-derived execution ordering with bounded concurrency

Gate: set ORCHESTRATOR_MODE=langgraph to use this path.
"""
from __future__ import annotations

import logging
import os
import re as _re
from dataclasses import dataclass, field
from enum import Enum
from graphlib import TopologicalSorter, CycleError
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

MAX_ITERATIONS = int(os.getenv("GRAPH_MAX_ITERATIONS", "15"))
PLAN_MAX_PARALLEL = int(os.getenv("PLAN_MAX_PARALLEL", "4"))
PLAN_PARALLEL_ENABLED = os.getenv("PLAN_PARALLEL_ENABLED", "0") == "1"
STEP_TIMEOUT_S = float(os.getenv("STEP_TIMEOUT_S", "30"))

STEP_REF_PATTERN = _re.compile(r"\{\{steps\.([a-zA-Z0-9_]+)\.output\}\}")


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
	# Step IDs that completed before a HITL interrupt — skipped on replay.
	completed_step_ids: list[str]


# ---------------------------------------------------------------------------
# Structured output models for LLM nodes
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
	"""A single typed step in an execution plan."""
	id: str = Field(..., description="Unique step identifier, e.g. step1, step2")
	tool_name: str = Field(
		..., description="Tool to invoke",
		alias="tool_name",
	)
	arguments: dict[str, Any] = Field(
		default_factory=dict, description="Arguments dict — may contain {{steps.<id>.output}} references",
	)

	model_config = ConfigDict(populate_by_name=True)

	@classmethod
	def from_loose_dict(cls, d: dict[str, Any], fallback_id: str) -> "PlanStep":
		"""Accept the LLM's inconsistent naming and normalise."""
		step_id = d.get("id", fallback_id)
		tool = d.get("tool_name") or d.get("name") or d.get("tool") or ""
		args = d.get("arguments") or d.get("args") or d.get("parameters") or {}
		return cls(id=step_id, tool_name=tool, arguments=args)


class ExecutionPlan(BaseModel):
	"""LLM-generated execution plan validated via PydanticAI."""
	intent: str = Field(..., description="One-line goal description")
	steps: list[dict[str, Any]] = Field(
		..., min_length=1,
		description=(
			"Ordered tool calls: [{id, tool_name, arguments}]. "
			"Use {{steps.<id>.output}} in arguments to reference a prior step's output."
		),
	)

	def typed_steps(self) -> list[PlanStep]:
		"""Convert raw dicts to typed PlanStep objects."""
		return [
			PlanStep.from_loose_dict(s, fallback_id=f"step{i+1}")
			for i, s in enumerate(self.steps)
		]


def _resolve_references(
	arguments: dict[str, Any],
	step_outputs: dict[str, Any],
) -> dict[str, Any]:
	"""Replace {{steps.<id>.output}} tokens in argument values."""
	resolved: dict[str, Any] = {}
	for key, value in arguments.items():
		if isinstance(value, str):
			def _replacer(m: _re.Match) -> str:
				ref_id = m.group(1)
				out = step_outputs.get(ref_id)
				return str(out) if out is not None else m.group(0)
			resolved[key] = STEP_REF_PATTERN.sub(_replacer, value)
		else:
			resolved[key] = value
	return resolved


def _validate_step_references(steps: list[PlanStep]) -> list[str]:
	"""Return list of errors for references to unknown step IDs."""
	known_ids = {s.id for s in steps}
	errors: list[str] = []
	for step in steps:
		for _key, value in step.arguments.items():
			if isinstance(value, str):
				for m in STEP_REF_PATTERN.finditer(value):
					ref_id = m.group(1)
					if ref_id not in known_ids:
						errors.append(f"Step '{step.id}' references unknown step '{ref_id}'")
	return errors


def _build_dag(steps: list[PlanStep]) -> dict[str, set[str]]:
	"""Build dependency graph by inspecting {{steps.*}} references."""
	deps: dict[str, set[str]] = {s.id: set() for s in steps}
	for step in steps:
		for _key, value in step.arguments.items():
			if isinstance(value, str):
				for m in STEP_REF_PATTERN.finditer(value):
					deps[step.id].add(m.group(1))
	return deps


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
	_checkpointer: Any = field(default=None, init=False, repr=False)
	_redis_saver_ctx: Any = field(default=None, init=False, repr=False)

	async def _ensure_checkpointer(self):
		"""Lazily initialise the checkpointer once, reuse across run() calls."""
		if self._checkpointer is not None:
			return
		redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
		try:
			from langgraph.checkpoint.redis.aio import AsyncRedisSaver
			self._redis_saver_ctx = AsyncRedisSaver.from_conn_string(redis_url)
			self._checkpointer = await self._redis_saver_ctx.__aenter__()
			await self._checkpointer.setup()
		except Exception as exc:  # noqa: BLE001
			logger.warning("AsyncRedisSaver unavailable (%s), falling back to MemorySaver", exc)
			self._redis_saver_ctx = None
			from langgraph.checkpoint.memory import MemorySaver
			self._checkpointer = MemorySaver()

	async def close(self):
		"""Release the checkpointer connection if one was opened."""
		if self._redis_saver_ctx is not None:
			try:
				await self._redis_saver_ctx.__aexit__(None, None, None)
			except Exception:
				pass
			self._redis_saver_ctx = None
		self._checkpointer = None

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

		await self._ensure_checkpointer()

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
				"  steps: array of objects each with id, tool_name, and arguments keys\n\n"
				"Each step needs a unique id (e.g. step1, step2). To use a previous step's "
				"output as input, reference it with {{steps.<id>.output}} in argument values.\n\n"
				f"Available tools:\n{tool_descriptions}\n\n"
				"Example for 'add 3 and 4 then echo the result':\n"
				'{"intent": "add then echo", "steps": ['
				'{"id": "step1", "tool_name": "add", "arguments": {"a": 3, "b": 4}}, '
				'{"id": "step2", "tool_name": "echo", "arguments": {"message": "{{steps.step1.output}}"}}'
				']}'
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

			if state.get("phase") == Phase.FAILED.value:
				return state

			plan = state.get("plan")
			if not plan or not plan.get("steps"):
				return {**state, "phase": Phase.FAILED.value, "error": "No plan to execute"}

			exec_plan = ExecutionPlan(**plan)
			typed_steps = exec_plan.typed_steps()

			# Validate references before any execution.
			ref_errors = _validate_step_references(typed_steps)
			if ref_errors:
				return {
					**state,
					"phase": Phase.FAILED.value,
					"error": f"Invalid step references: {'; '.join(ref_errors)}",
				}

			# HITL: scan ALL steps for destructive tools before executing any.
			for step in typed_steps:
				if any(pat in step.tool_name.lower() for pat in DESTRUCTIVE_TOOL_PATTERNS):
					reason = f"Tool '{step.tool_name}' requires human approval before execution."
					logger.info("HITL interrupt triggered: %s", reason)
					lg_interrupt({"reason": reason, "plan": plan})

			# Build DAG and determine execution order.
			deps = _build_dag(typed_steps)
			step_map = {s.id: s for s in typed_steps}
			step_outputs: dict[str, Any] = {}
			completed_ids: set[str] = set(state.get("completed_step_ids", []))
			results: list[dict[str, Any]] = []
			semaphore = asyncio.Semaphore(PLAN_MAX_PARALLEL)

			async def _run_step(step: PlanStep) -> dict[str, Any]:
				if step.id in completed_ids:
					return {"tool": step.tool_name, "step_id": step.id, "result": "skipped (already completed)", "success": True}
				resolved_args = _resolve_references(step.arguments, step_outputs)
				async with semaphore:
					try:
						if asyncio.iscoroutinefunction(call_tool_fn):
							result = await asyncio.wait_for(
								call_tool_fn(step.tool_name, resolved_args),
								timeout=STEP_TIMEOUT_S,
							)
						else:
							result = await asyncio.wait_for(
								asyncio.get_event_loop().run_in_executor(None, call_tool_fn, step.tool_name, resolved_args),
								timeout=STEP_TIMEOUT_S,
							)
						step_outputs[step.id] = result
						completed_ids.add(step.id)
						return {"tool": step.tool_name, "step_id": step.id, "result": result, "success": True}
					except asyncio.TimeoutError:
						return {"tool": step.tool_name, "step_id": step.id, "error": f"Timed out after {STEP_TIMEOUT_S}s", "success": False}
					except Exception as exc:
						return {"tool": step.tool_name, "step_id": step.id, "error": str(exc), "success": False}

			try:
				sorter = TopologicalSorter(deps)
				sorter.prepare()

				while sorter.is_active():
					ready_batch = list(sorter.get_ready())
					if PLAN_PARALLEL_ENABLED and len(ready_batch) > 1:
						batch_results = await asyncio.gather(
							*[_run_step(step_map[sid]) for sid in ready_batch],
							return_exceptions=True,
						)
						for sid, br in zip(ready_batch, batch_results):
							if isinstance(br, Exception):
								results.append({"tool": step_map[sid].tool_name, "step_id": sid, "error": str(br), "success": False})
							else:
								results.append(br)
							sorter.done(sid)
					else:
						for sid in ready_batch:
							r = await _run_step(step_map[sid])
							results.append(r)
							sorter.done(sid)

			except CycleError as exc:
				logger.warning("Cyclic step references detected (%s), falling back to sequential", exc)
				for step in typed_steps:
					r = await _run_step(step)
					results.append(r)

			return {
				**state,
				"phase": Phase.EVALUATE.value,
				"execution_result": {"steps": results},
				"completed_step_ids": list(completed_ids),
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
				steps = exec_result.get("steps", [])
				step_texts: list[str] = []
				for s in steps:
					r = s.get("result", {})
					try:
						step_texts.append(r["content"][0]["text"])
					except (KeyError, IndexError, TypeError):
						step_texts.append(str(r))

				return {
					**state,
					"phase": Phase.DONE.value,
					"iteration": iteration,
					"evaluation_verdict": verdict,
					"final_result": {
						"text": step_texts[-1] if step_texts else "",
						"all_step_outputs": step_texts,
						"iterations": iteration,
					},
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

		compiled = graph.compile(checkpointer=self._checkpointer)

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
			"completed_step_ids": [],
		}

		config = {"configurable": {"thread_id": thread_id}}
		final_state = await compiled.ainvoke(initial_state, config=config)
		return dict(final_state)
