"""Tests for LangGraph GraphOrchestrator — validates state machine contracts."""
from __future__ import annotations

import pytest

from mcp_agent_factory.graph_orchestrator import (
	ExecutionPlan,
	EvaluationResult,
	GraphOrchestrator,
	GraphState,
	Phase,
)


# ---------------------------------------------------------------------------
# Unit: Phase enum
# ---------------------------------------------------------------------------

def test_phase_values():
	assert Phase.VALIDATE.value == "validate"
	assert Phase.DONE.value == "done"
	assert Phase.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# Unit: ExecutionPlan model
# ---------------------------------------------------------------------------

def test_execution_plan_valid():
	plan = ExecutionPlan(
		intent="echo a message",
		steps=[{"tool_name": "echo", "arguments": {"message": "hi"}}],
	)
	assert plan.intent == "echo a message"
	assert len(plan.steps) == 1


def test_execution_plan_rejects_empty_steps():
	with pytest.raises(Exception):
		ExecutionPlan(intent="do something", steps=[])


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

	async def noop(name, args):
		return {}

	orchestrator = GraphOrchestrator()
	state = await orchestrator.run(task="", tools=MOCK_TOOLS, call_tool_fn=noop)
	assert state["phase"] == Phase.FAILED.value
	assert "Empty task" in (state.get("error") or "")
