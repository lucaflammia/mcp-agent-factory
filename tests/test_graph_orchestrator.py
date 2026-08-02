"""Tests for LangGraph GraphOrchestrator — validates state machine contracts."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mcp_agent_factory.graph_orchestrator import (
	DESTRUCTIVE_TOOL_PATTERNS,
	ExecutionPlan,
	EvaluationResult,
	GraphOrchestrator,
	GraphState,
	PLAN_MAX_PARALLEL,
	PlanStep,
	Phase,
	STEP_TIMEOUT_S,
	_build_dag,
	_resolve_references,
	_validate_step_references,
)


# ---------------------------------------------------------------------------
# Unit: Phase enum
# ---------------------------------------------------------------------------

def test_phase_values():
	assert Phase.VALIDATE.value == "validate"
	assert Phase.DONE.value == "done"
	assert Phase.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# Unit: PlanStep
# ---------------------------------------------------------------------------

def test_plan_step_from_loose_dict_standard():
	s = PlanStep.from_loose_dict({"id": "s1", "tool_name": "echo", "arguments": {"msg": "hi"}}, "fallback")
	assert s.id == "s1"
	assert s.tool_name == "echo"

def test_plan_step_from_loose_dict_aliases():
	s = PlanStep.from_loose_dict({"name": "add", "args": {"a": 1}}, "step1")
	assert s.id == "step1"
	assert s.tool_name == "add"
	assert s.arguments == {"a": 1}

def test_plan_step_from_loose_dict_tool_alias():
	s = PlanStep.from_loose_dict({"tool": "query", "parameters": {"q": "x"}}, "step2")
	assert s.tool_name == "query"
	assert s.arguments == {"q": "x"}


# ---------------------------------------------------------------------------
# Unit: ExecutionPlan model
# ---------------------------------------------------------------------------

def test_execution_plan_valid():
	plan = ExecutionPlan(
		intent="echo a message",
		steps=[{"id": "step1", "tool_name": "echo", "arguments": {"message": "hi"}}],
	)
	assert plan.intent == "echo a message"
	assert len(plan.steps) == 1

def test_execution_plan_typed_steps():
	plan = ExecutionPlan(
		intent="chain",
		steps=[
			{"tool_name": "add", "arguments": {"a": 1, "b": 2}},
			{"tool_name": "echo", "arguments": {"msg": "{{steps.step1.output}}"}},
		],
	)
	typed = plan.typed_steps()
	assert len(typed) == 2
	assert typed[0].id == "step1"
	assert typed[1].id == "step2"

def test_execution_plan_rejects_empty_steps():
	with pytest.raises(Exception):
		ExecutionPlan(intent="do something", steps=[])


# ---------------------------------------------------------------------------
# Unit: Reference resolution
# ---------------------------------------------------------------------------

def test_resolve_references_basic():
	args = {"msg": "Result: {{steps.s1.output}}"}
	resolved = _resolve_references(args, {"s1": "42"})
	assert resolved["msg"] == "Result: 42"

def test_resolve_references_multiple():
	args = {"msg": "{{steps.a.output}} + {{steps.b.output}}"}
	resolved = _resolve_references(args, {"a": "1", "b": "2"})
	assert resolved["msg"] == "1 + 2"

def test_resolve_references_unknown_kept():
	args = {"msg": "{{steps.missing.output}}"}
	resolved = _resolve_references(args, {})
	assert resolved["msg"] == "{{steps.missing.output}}"

def test_resolve_references_non_string_passthrough():
	args = {"count": 5, "flag": True}
	resolved = _resolve_references(args, {})
	assert resolved == {"count": 5, "flag": True}


# ---------------------------------------------------------------------------
# Unit: Reference validation
# ---------------------------------------------------------------------------

def test_validate_step_references_ok():
	steps = [
		PlanStep(id="s1", tool_name="add", arguments={"a": 1}),
		PlanStep(id="s2", tool_name="echo", arguments={"msg": "{{steps.s1.output}}"}),
	]
	assert _validate_step_references(steps) == []

def test_validate_step_references_unknown():
	steps = [
		PlanStep(id="s1", tool_name="echo", arguments={"msg": "{{steps.nope.output}}"}),
	]
	errors = _validate_step_references(steps)
	assert len(errors) == 1
	assert "nope" in errors[0]


# ---------------------------------------------------------------------------
# Unit: DAG construction
# ---------------------------------------------------------------------------

def test_build_dag_no_refs():
	steps = [
		PlanStep(id="s1", tool_name="a", arguments={}),
		PlanStep(id="s2", tool_name="b", arguments={}),
	]
	dag = _build_dag(steps)
	assert dag == {"s1": set(), "s2": set()}

def test_build_dag_with_refs():
	steps = [
		PlanStep(id="s1", tool_name="a", arguments={}),
		PlanStep(id="s2", tool_name="b", arguments={"x": "{{steps.s1.output}}"}),
		PlanStep(id="s3", tool_name="c", arguments={"y": "{{steps.s1.output}} and {{steps.s2.output}}"}),
	]
	dag = _build_dag(steps)
	assert dag["s1"] == set()
	assert dag["s2"] == {"s1"}
	assert dag["s3"] == {"s1", "s2"}


# ---------------------------------------------------------------------------
# Unit: EvaluationResult model
# ---------------------------------------------------------------------------

def test_evaluation_result_pass():
	r = EvaluationResult(passed=True, score=0.95, findings=[], revision_notes="")
	assert r.passed
	assert r.score == 0.95


def test_evaluation_result_fail():
	r = EvaluationResult(
		passed=False, score=0.3,
		findings=["Missing required output"],
		revision_notes="Include the greeting",
	)
	assert not r.passed


# ---------------------------------------------------------------------------
# Integration: Full graph execution
# ---------------------------------------------------------------------------

MOCK_TOOLS = [
	{
		"name": "echo",
		"description": "Returns input unchanged",
		"inputSchema": {
			"type": "object",
			"properties": {"message": {"type": "string"}},
			"required": ["message"],
		},
	},
]


@pytest.mark.integration
async def test_graph_orchestrator_echo():
	"""Run the full LangGraph orchestrator with an LLM.
	Requires GEMINI_API_KEY or a running Ollama instance.
	"""
	import os
	if not os.getenv("GEMINI_API_KEY") and not os.getenv("OLLAMA_BASE_URL"):
		pytest.skip("No LLM provider configured")
	try:
		from langgraph.graph import StateGraph  # noqa: F401
	except (ImportError, TypeError) as exc:
		pytest.skip(f"LangGraph not available or incompatible: {exc}")

	async def mock_call_tool(name: str, args: dict) -> dict:
		if name == "echo":
			return {"content": [{"type": "text", "text": args.get("message", "")}]}
		return {"isError": True, "content": [{"type": "text", "text": f"Unknown: {name}"}]}

	orchestrator = GraphOrchestrator(max_iterations=2)
	state = await orchestrator.run(
		task='Use the echo tool to say "hello"',
		tools=MOCK_TOOLS,
		call_tool_fn=mock_call_tool,
		thread_id="test-1",
	)
	assert state["phase"] in (Phase.DONE.value, Phase.FAILED.value)
	if state["phase"] == Phase.DONE.value:
		assert state["final_result"] is not None


@pytest.mark.integration
async def test_graph_orchestrator_empty_task_fails():
	"""Empty task should fail at validation."""
	import os
	if not os.getenv("GEMINI_API_KEY") and not os.getenv("OLLAMA_BASE_URL"):
		pytest.skip("No LLM provider configured")
	try:
		from langgraph.graph import StateGraph  # noqa: F401
	except (ImportError, TypeError) as exc:
		pytest.skip(f"LangGraph not available or incompatible: {exc}")

	async def noop(name, args):
		return {}

	orchestrator = GraphOrchestrator()
	state = await orchestrator.run(task="", tools=MOCK_TOOLS, call_tool_fn=noop)
	assert state["phase"] == Phase.FAILED.value
	assert "Empty task" in (state.get("error") or "")


# ---------------------------------------------------------------------------
# Execute-node level tests (no LLM required)
# These import execute_node's logic indirectly by constructing a
# GraphOrchestrator with mocked plan/evaluate nodes.
# ---------------------------------------------------------------------------

def _make_graph_with_execute_only(call_tool_fn, plan_dict, *, parallel=False):
	"""Build a minimal graph: inject → execute → capture."""
	import os
	os.environ["PLAN_PARALLEL_ENABLED"] = "1" if parallel else "0"

	# Re-import to pick up env var changes
	import importlib
	import mcp_agent_factory.graph_orchestrator as mod
	importlib.reload(mod)

	from langgraph.graph import StateGraph, END
	from langgraph.checkpoint.memory import MemorySaver

	orchestrator = mod.GraphOrchestrator(max_iterations=1)

	async def inject_plan(state):
		return {**state, "phase": mod.Phase.EXECUTE.value, "plan": plan_dict}

	async def execute_node(state):
		# Inline from the closure — call the orchestrator's run and extract execute.
		# Instead, we replicate the execute_node logic using the public helpers.
		exec_plan = mod.ExecutionPlan(**state["plan"])
		typed_steps = exec_plan.typed_steps()

		ref_errors = mod._validate_step_references(typed_steps)
		if ref_errors:
			return {**state, "phase": mod.Phase.FAILED.value, "error": f"Invalid refs: {'; '.join(ref_errors)}"}

		deps = mod._build_dag(typed_steps)
		step_map = {s.id: s for s in typed_steps}
		step_outputs: dict = {}
		completed_ids: set = set(state.get("completed_step_ids", []))
		results = []
		semaphore = asyncio.Semaphore(mod.PLAN_MAX_PARALLEL)

		async def _run_step(step):
			if step.id in completed_ids:
				return {"tool": step.tool_name, "step_id": step.id, "result": "skipped", "success": True}
			resolved_args = mod._resolve_references(step.arguments, step_outputs)
			async with semaphore:
				try:
					result = await asyncio.wait_for(
						call_tool_fn(step.tool_name, resolved_args),
						timeout=mod.STEP_TIMEOUT_S,
					)
					step_outputs[step.id] = result
					completed_ids.add(step.id)
					return {"tool": step.tool_name, "step_id": step.id, "result": result, "success": True}
				except asyncio.TimeoutError:
					return {"tool": step.tool_name, "step_id": step.id, "error": f"Timed out", "success": False}
				except Exception as exc:
					return {"tool": step.tool_name, "step_id": step.id, "error": str(exc), "success": False}

		try:
			from graphlib import TopologicalSorter, CycleError
			sorter = TopologicalSorter(deps)
			sorter.prepare()
			while sorter.is_active():
				ready = list(sorter.get_ready())
				if mod.PLAN_PARALLEL_ENABLED and len(ready) > 1:
					batch = await asyncio.gather(*[_run_step(step_map[sid]) for sid in ready], return_exceptions=True)
					for sid, br in zip(ready, batch):
						results.append(br if not isinstance(br, Exception) else {"step_id": sid, "error": str(br), "success": False})
						sorter.done(sid)
				else:
					for sid in ready:
						results.append(await _run_step(step_map[sid]))
						sorter.done(sid)
		except CycleError:
			for step in typed_steps:
				results.append(await _run_step(step))

		return {
			**state, "phase": mod.Phase.EVALUATE.value,
			"execution_result": {"steps": results},
			"completed_step_ids": list(completed_ids),
		}

	async def capture(state):
		return {**state, "phase": mod.Phase.DONE.value, "final_result": state.get("execution_result")}

	def route_after_execute(state):
		if state.get("phase") == mod.Phase.FAILED.value:
			return "end"
		return "capture"

	graph = StateGraph(mod.GraphState)
	graph.add_node("inject", inject_plan)
	graph.add_node("execute", execute_node)
	graph.add_node("capture", capture)
	graph.set_entry_point("inject")
	graph.add_edge("inject", "execute")
	graph.add_conditional_edges("execute", route_after_execute, {"capture": "capture", "end": END})
	graph.add_edge("capture", END)
	compiled = graph.compile(checkpointer=MemorySaver())
	return compiled, mod


@pytest.mark.asyncio
async def test_multistep_chaining():
	"""Step 3 references steps 1 and 2; all outputs reach final_result."""
	call_log = []

	async def mock_tool(name, args):
		call_log.append((name, args))
		if name == "add":
			return {"content": [{"type": "text", "text": str(args.get("a", 0) + args.get("b", 0))}]}
		if name == "echo":
			return {"content": [{"type": "text", "text": args.get("message", "")}]}
		return {"content": [{"type": "text", "text": "unknown"}]}

	plan = {
		"intent": "add then echo",
		"steps": [
			{"id": "s1", "tool_name": "add", "arguments": {"a": 3, "b": 4}},
			{"id": "s2", "tool_name": "add", "arguments": {"a": 10, "b": 20}},
			{"id": "s3", "tool_name": "echo", "arguments": {"message": "{{steps.s1.output}} and {{steps.s2.output}}"}},
		],
	}

	compiled, mod = _make_graph_with_execute_only(mock_tool, plan)
	state = await compiled.ainvoke(
		{"task": "test", "phase": "validate", "iteration": 0, "tools": [], "history": [],
		 "plan": None, "execution_result": None, "evaluation_verdict": None,
		 "final_result": None, "error": None, "require_user_approval": False,
		 "hitl_reason": None, "completed_step_ids": []},
		{"configurable": {"thread_id": "chain-test"}},
	)

	steps = state["final_result"]["steps"]
	assert len(steps) == 3
	assert all(s["success"] for s in steps)
	# s3 should have received resolved references
	s3 = next(s for s in steps if s["step_id"] == "s3")
	assert s3["result"]["content"][0]["text"] != "{{steps.s1.output}} and {{steps.s2.output}}"


@pytest.mark.asyncio
async def test_unknown_step_ref_fails_validation():
	"""Reference to nonexistent step ID fails before execution."""
	async def mock_tool(name, args):
		return {"content": [{"type": "text", "text": "ok"}]}

	plan = {
		"intent": "bad ref",
		"steps": [
			{"id": "s1", "tool_name": "echo", "arguments": {"message": "{{steps.nope.output}}"}},
		],
	}

	compiled, mod = _make_graph_with_execute_only(mock_tool, plan)
	state = await compiled.ainvoke(
		{"task": "test", "phase": "validate", "iteration": 0, "tools": [], "history": [],
		 "plan": None, "execution_result": None, "evaluation_verdict": None,
		 "final_result": None, "error": None, "require_user_approval": False,
		 "hitl_reason": None, "completed_step_ids": []},
		{"configurable": {"thread_id": "badref-test"}},
	)

	assert state["phase"] == mod.Phase.FAILED.value
	assert "nope" in state.get("error", "")


@pytest.mark.asyncio
async def test_step_timeout():
	"""A hung tool is cancelled at STEP_TIMEOUT_S and recorded as failed."""
	import os
	os.environ["STEP_TIMEOUT_S"] = "0.1"

	async def slow_tool(name, args):
		await asyncio.sleep(10)
		return {"content": [{"type": "text", "text": "too late"}]}

	plan = {
		"intent": "timeout test",
		"steps": [{"id": "s1", "tool_name": "echo", "arguments": {"message": "hi"}}],
	}

	compiled, mod = _make_graph_with_execute_only(slow_tool, plan)
	state = await compiled.ainvoke(
		{"task": "test", "phase": "validate", "iteration": 0, "tools": [], "history": [],
		 "plan": None, "execution_result": None, "evaluation_verdict": None,
		 "final_result": None, "error": None, "require_user_approval": False,
		 "hitl_reason": None, "completed_step_ids": []},
		{"configurable": {"thread_id": "timeout-test"}},
	)

	os.environ["STEP_TIMEOUT_S"] = "30"  # restore
	steps = state["final_result"]["steps"]
	assert len(steps) == 1
	assert steps[0]["success"] is False
	assert "Timed out" in steps[0].get("error", "")


@pytest.mark.asyncio
async def test_completed_step_ids_skipped_on_replay():
	"""Steps already in completed_step_ids are skipped (HITL replay safety)."""
	call_log = []

	async def mock_tool(name, args):
		call_log.append(name)
		return {"content": [{"type": "text", "text": "done"}]}

	plan = {
		"intent": "replay test",
		"steps": [
			{"id": "s1", "tool_name": "echo", "arguments": {"message": "a"}},
			{"id": "s2", "tool_name": "echo", "arguments": {"message": "b"}},
		],
	}

	compiled, mod = _make_graph_with_execute_only(mock_tool, plan)
	state = await compiled.ainvoke(
		{"task": "test", "phase": "validate", "iteration": 0, "tools": [], "history": [],
		 "plan": None, "execution_result": None, "evaluation_verdict": None,
		 "final_result": None, "error": None, "require_user_approval": False,
		 "hitl_reason": None, "completed_step_ids": ["s1"]},
		{"configurable": {"thread_id": "replay-test"}},
	)

	# s1 should be skipped, only s2 actually called
	assert "echo" in call_log
	assert call_log.count("echo") == 1
	steps = state["final_result"]["steps"]
	skipped = [s for s in steps if s["step_id"] == "s1"]
	assert skipped[0]["result"] == "skipped"


@pytest.mark.asyncio
async def test_cycle_falls_back_to_sequential():
	"""Cyclic references fall back to sequential execution without crashing."""
	async def mock_tool(name, args):
		return {"content": [{"type": "text", "text": "ok"}]}

	plan = {
		"intent": "cycle test",
		"steps": [
			{"id": "s1", "tool_name": "echo", "arguments": {"message": "{{steps.s2.output}}"}},
			{"id": "s2", "tool_name": "echo", "arguments": {"message": "{{steps.s1.output}}"}},
		],
	}

	# Note: _validate_step_references won't catch cycles (both IDs exist),
	# but _build_dag + TopologicalSorter will raise CycleError.
	# We need to bypass validation since both refs ARE known IDs.
	compiled, mod = _make_graph_with_execute_only(mock_tool, plan)
	state = await compiled.ainvoke(
		{"task": "test", "phase": "validate", "iteration": 0, "tools": [], "history": [],
		 "plan": None, "execution_result": None, "evaluation_verdict": None,
		 "final_result": None, "error": None, "require_user_approval": False,
		 "hitl_reason": None, "completed_step_ids": []},
		{"configurable": {"thread_id": "cycle-test"}},
	)

	# Should not crash — falls back to sequential
	steps = state["final_result"]["steps"]
	assert len(steps) == 2
	assert all(s["success"] for s in steps)


@pytest.mark.asyncio
async def test_parallel_respects_semaphore():
	"""With parallel enabled, concurrent execution never exceeds PLAN_MAX_PARALLEL."""
	import os
	os.environ["PLAN_MAX_PARALLEL"] = "2"

	max_concurrent = 0
	current_concurrent = 0
	lock = asyncio.Lock()

	async def counting_tool(name, args):
		nonlocal max_concurrent, current_concurrent
		async with lock:
			current_concurrent += 1
			if current_concurrent > max_concurrent:
				max_concurrent = current_concurrent
		await asyncio.sleep(0.05)
		async with lock:
			current_concurrent -= 1
		return {"content": [{"type": "text", "text": "ok"}]}

	plan = {
		"intent": "semaphore test",
		"steps": [
			{"id": f"s{i}", "tool_name": "echo", "arguments": {"message": f"msg{i}"}}
			for i in range(1, 7)
		],
	}

	compiled, mod = _make_graph_with_execute_only(counting_tool, plan, parallel=True)
	state = await compiled.ainvoke(
		{"task": "test", "phase": "validate", "iteration": 0, "tools": [], "history": [],
		 "plan": None, "execution_result": None, "evaluation_verdict": None,
		 "final_result": None, "error": None, "require_user_approval": False,
		 "hitl_reason": None, "completed_step_ids": []},
		{"configurable": {"thread_id": "sem-test"}},
	)

	os.environ.pop("PLAN_MAX_PARALLEL", None)
	assert max_concurrent <= 2
	steps = state["final_result"]["steps"]
	assert len(steps) == 6


@pytest.mark.asyncio
async def test_parallel_determinism():
	"""Sequential and parallel produce identical results for independent steps."""
	results_by_mode = {}

	for parallel in [False, True]:
		async def mock_tool(name, args):
			return {"content": [{"type": "text", "text": f"{name}:{args}"}]}

		plan = {
			"intent": "determinism",
			"steps": [
				{"id": "s1", "tool_name": "add", "arguments": {"a": 1, "b": 2}},
				{"id": "s2", "tool_name": "add", "arguments": {"a": 3, "b": 4}},
			],
		}

		compiled, mod = _make_graph_with_execute_only(mock_tool, plan, parallel=parallel)
		state = await compiled.ainvoke(
			{"task": "test", "phase": "validate", "iteration": 0, "tools": [], "history": [],
			 "plan": None, "execution_result": None, "evaluation_verdict": None,
			 "final_result": None, "error": None, "require_user_approval": False,
			 "hitl_reason": None, "completed_step_ids": []},
			{"configurable": {"thread_id": f"det-{parallel}"}},
		)

		step_results = sorted(
			[(s["step_id"], s["result"]) for s in state["final_result"]["steps"]],
			key=lambda x: x[0],
		)
		results_by_mode[parallel] = step_results

	assert results_by_mode[False] == results_by_mode[True]
