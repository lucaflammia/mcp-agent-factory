"""
Cross-layer integration test: exercises all 4 layers of the execution pipeline.

Layer 1 (PydanticAI) → Layer 2 (LangGraph FSM) → Layer 3 (CrewAI/scoped agents)
→ Layer 4 (DSPy+GEPA offline optimization).

All LLM calls are mocked. No external services required.
"""
from __future__ import annotations

import json
import unittest.mock as mock

import pytest

from mcp_agent_factory.crew import MCPCrew, ScopedAgent, scope_tools, build_scoped_call_fn
from mcp_agent_factory.optimizer import PromptOptimizer, SkillCompiler, TraceRecord


SAMPLE_TOOLS = [
  {"name": "read_file", "description": "Read a file", "inputSchema": {"properties": {"path": {}}}},
  {"name": "search_web", "description": "Search the web", "inputSchema": {"properties": {"q": {}}}},
  {"name": "write_report", "description": "Write a report", "inputSchema": {"properties": {"text": {}}}},
  {"name": "sql_query", "description": "Run SQL query", "inputSchema": {"properties": {"sql": {}}}},
]


class TestCrossLayerPipeline:
  """End-to-end pipeline: Layer 1 validation → Layer 2 FSM → Layer 3 crew → Layer 4 optimization."""

  @pytest.mark.asyncio
  async def test_layer1_pydantic_validation_feeds_layer2_graph(self):
    """Layer 1 (PydanticAI structured output) is used inside Layer 2 (GraphOrchestrator) nodes."""
    from mcp_agent_factory.graph_orchestrator import GraphOrchestrator, ExecutionPlan, EvaluationResult

    plan = ExecutionPlan(intent="test", steps=[{"tool_name": "read_file", "arguments": {"path": "/tmp"}}])
    evaluation = EvaluationResult(passed=True, score=0.95, findings=[], revision_notes="")

    plan_response = mock.MagicMock()
    plan_response.data = plan
    eval_response = mock.MagicMock()
    eval_response.data = evaluation

    call_count = {"n": 0}

    def mock_agent_factory(*args, **kwargs):
      agent = mock.MagicMock()
      async def fake_run(prompt):
        call_count["n"] += 1
        if kwargs.get("result_type") == ExecutionPlan:
          return plan_response
        return eval_response
      agent.run = fake_run
      return agent

    def call_tool(name, args):
      return {"content": [{"text": f"result of {name}"}]}

    with mock.patch("pydantic_ai.Agent", side_effect=mock_agent_factory):
      graph = GraphOrchestrator(max_iterations=3)
      state = await graph.run("Summarise file", SAMPLE_TOOLS, call_tool)

    assert state["phase"] == "done"
    assert state["iteration"] == 1

  @pytest.mark.asyncio
  async def test_layer3_crew_scoping_enforced(self):
    """Layer 3 tool scoping raises PermissionError for out-of-scope calls."""
    analyst_tools = scope_tools("analyst", SAMPLE_TOOLS)
    fn = build_scoped_call_fn("analyst", analyst_tools, lambda n, a: "ok")

    assert fn("read_file", {}) == "ok"
    with pytest.raises(PermissionError):
      fn("sql_query", {})

  @pytest.mark.asyncio
  async def test_layer3_crew_with_langgraph_flag(self):
    """Layer 3 MCPCrew with use_langgraph=True delegates to Layer 2 GraphOrchestrator."""
    from mcp_agent_factory.graph_orchestrator import ExecutionPlan, EvaluationResult

    plan = ExecutionPlan(intent="test", steps=[{"tool_name": "read_file", "arguments": {"path": "/"}}])
    eval_pass = EvaluationResult(passed=True, score=0.9, findings=[], revision_notes="")

    def mock_agent_factory(*args, **kwargs):
      agent = mock.MagicMock()
      async def fake_run(prompt):
        if kwargs.get("result_type") == ExecutionPlan:
          r = mock.MagicMock(); r.data = plan; return r
        r = mock.MagicMock(); r.data = eval_pass; return r
      agent.run = fake_run
      return agent

    agents = [ScopedAgent(role="analyst")]
    crew = MCPCrew(
      agents=agents,
      all_tools=SAMPLE_TOOLS,
      call_tool_fn=lambda n, a: {"content": [{"text": "ok"}]},
      use_langgraph=True,
    )

    with mock.patch("pydantic_ai.Agent", side_effect=mock_agent_factory):
      result = await crew._run_with_langgraph("Analyse data")

    assert len(result.agent_results) == 1
    assert result.agent_results[0].role == "analyst"
    assert result.agent_results[0].success is True

  @pytest.mark.asyncio
  async def test_layer4_optimizer_compiles_from_traces(self, tmp_path):
    """Layer 4 ingests traces, compiles skills via GEPA, and writes JSON assets."""
    opt = PromptOptimizer(dry_run=True, skills_dir=str(tmp_path))
    traces = await opt.ingest_traces(limit=10)
    assets = await opt.compile(traces)

    assert len(assets) >= 1

    compiler = SkillCompiler(output_dir=str(tmp_path))
    paths = compiler.compile_all(assets)

    assert len(paths) >= 1
    for p in paths:
      data = json.loads(p.read_text())
      assert "system_prompt" in data
      assert "performance_score" in data

    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["skills"]) == len(assets)

  @pytest.mark.asyncio
  async def test_full_pipeline_layer1_through_layer4(self, tmp_path):
    """
    Full 4-layer integration:
    1. PydanticAI validates plan structure (Layer 1)
    2. GraphOrchestrator runs FSM (Layer 2)
    3. MCPCrew scopes tools per agent (Layer 3)
    4. PromptOptimizer compiles skills from traces (Layer 4)
    """
    from mcp_agent_factory.graph_orchestrator import ExecutionPlan, EvaluationResult

    # Layers 1+2: Graph produces structured output
    plan = ExecutionPlan(intent="analyse", steps=[{"tool_name": "read_file", "arguments": {"path": "/data"}}])
    eval_pass = EvaluationResult(passed=True, score=0.92, findings=[], revision_notes="")

    def mock_agent_factory(*args, **kwargs):
      agent = mock.MagicMock()
      async def fake_run(prompt):
        if kwargs.get("result_type") == ExecutionPlan:
          r = mock.MagicMock(); r.data = plan; return r
        r = mock.MagicMock(); r.data = eval_pass; return r
      agent.run = fake_run
      return agent

    # Layer 3: Crew with scoped agents
    agents = [ScopedAgent(role="analyst"), ScopedAgent(role="writer")]
    crew = MCPCrew(
      agents=agents,
      all_tools=SAMPLE_TOOLS,
      call_tool_fn=lambda n, a: {"content": [{"text": "tool result"}]},
      use_langgraph=True,
    )

    with mock.patch("pydantic_ai.Agent", side_effect=mock_agent_factory):
      crew_result = await crew._run_with_langgraph("Analyse and write report")

    assert len(crew_result.agent_results) == 2

    # Layer 4: Optimize prompts from traces
    opt = PromptOptimizer(dry_run=True, skills_dir=str(tmp_path))
    traces = await opt.ingest_traces(limit=10)
    assets = await opt.compile(traces)
    compiler = SkillCompiler(output_dir=str(tmp_path))
    paths = compiler.compile_all(assets)

    assert len(paths) >= 1
    assert (tmp_path / "index.json").exists()
