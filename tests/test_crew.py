"""
Tests for Layer 3: Multi-Agent Orchestration (crew.py).

All tests are offline — no LLM calls, no CrewAI install required.
"""
from __future__ import annotations

import pytest

from mcp_agent_factory.crew import (
  MCPCrew,
  ROLE_TOOL_PATTERNS,
  ScopedAgent,
  build_scoped_call_fn,
  scope_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_tools() -> list[dict]:
  return [
    {"name": "read_file",    "description": "Read a file"},
    {"name": "search_web",   "description": "Search the web"},
    {"name": "write_report", "description": "Write a report"},
    {"name": "sql_query",    "description": "Run SQL query"},
    {"name": "fetch_url",    "description": "Fetch a URL"},
    {"name": "publish_doc",  "description": "Publish a document"},
  ]


# ---------------------------------------------------------------------------
# scope_tools
# ---------------------------------------------------------------------------

class TestScopeTools:
  def test_analyst_gets_read_and_search(self, sample_tools):
    scoped = scope_tools("analyst", sample_tools)
    names = {t["name"] for t in scoped}
    assert "read_file" in names
    assert "search_web" in names
    assert "sql_query" not in names
    assert "write_report" not in names

  def test_writer_gets_write_and_publish(self, sample_tools):
    scoped = scope_tools("writer", sample_tools)
    names = {t["name"] for t in scoped}
    assert "write_report" in names
    assert "publish_doc" in names
    assert "read_file" not in names

  def test_db_agent_gets_sql(self, sample_tools):
    scoped = scope_tools("db_agent", sample_tools)
    names = {t["name"] for t in scoped}
    assert "sql_query" in names
    assert "read_file" not in names

  def test_orchestrator_gets_all_tools(self, sample_tools):
    scoped = scope_tools("orchestrator", sample_tools)
    assert len(scoped) == len(sample_tools)

  def test_custom_patterns_override_defaults(self, sample_tools):
    scoped = scope_tools("analyst", sample_tools, allowed_patterns=["sql"])
    names = {t["name"] for t in scoped}
    assert "sql_query" in names
    assert "read_file" not in names

  def test_unknown_role_returns_empty(self, sample_tools):
    scoped = scope_tools("unknown_role", sample_tools)
    assert scoped == []

  def test_empty_tools_returns_empty(self):
    assert scope_tools("analyst", []) == []


# ---------------------------------------------------------------------------
# build_scoped_call_fn
# ---------------------------------------------------------------------------

class TestBuildScopedCallFn:
  def test_allowed_tool_passes_through(self, sample_tools):
    analyst_tools = scope_tools("analyst", sample_tools)
    calls: list[tuple] = []

    def base_call(name, args):
      calls.append((name, args))
      return {"result": "ok"}

    fn = build_scoped_call_fn("analyst", analyst_tools, base_call)
    result = fn("read_file", {"path": "/tmp/x"})
    assert result == {"result": "ok"}
    assert calls[0] == ("read_file", {"path": "/tmp/x"})

  def test_forbidden_tool_raises_permission_error(self, sample_tools):
    analyst_tools = scope_tools("analyst", sample_tools)

    def base_call(name, args):
      return {}

    fn = build_scoped_call_fn("analyst", analyst_tools, base_call)
    with pytest.raises(PermissionError, match="analyst"):
      fn("sql_query", {})

  def test_permission_error_contains_tool_name(self, sample_tools):
    tools = scope_tools("writer", sample_tools)
    fn = build_scoped_call_fn("writer", tools, lambda n, a: {})
    with pytest.raises(PermissionError, match="read_file"):
      fn("read_file", {})


# ---------------------------------------------------------------------------
# ScopedAgent
# ---------------------------------------------------------------------------

class TestScopedAgent:
  def test_get_scoped_tools_delegates_to_scope_tools(self, sample_tools):
    agent = ScopedAgent(role="analyst")
    scoped = agent.get_scoped_tools(sample_tools)
    assert all(
      any(p in t["name"] for p in ROLE_TOOL_PATTERNS["analyst"])
      for t in scoped
    )

  def test_get_persona_includes_role(self):
    agent = ScopedAgent(role="analyst")
    persona = agent.get_persona()
    assert "analyst" in persona

  def test_get_persona_includes_custom_system_prompt(self):
    agent = ScopedAgent(role="writer", system_prompt="Always write in Markdown.")
    persona = agent.get_persona()
    assert "Markdown" in persona

  def test_custom_patterns_applied(self, sample_tools):
    agent = ScopedAgent(role="writer", allowed_patterns=["sql"])
    scoped = agent.get_scoped_tools(sample_tools)
    assert all("sql" in t["name"] for t in scoped)


# ---------------------------------------------------------------------------
# MCPCrew — construction and scoping checks (no LLM)
# ---------------------------------------------------------------------------

class TestMCPCrewConstruction:
  def test_crew_builds_without_error(self, sample_tools):
    agents = [
      ScopedAgent(role="analyst"),
      ScopedAgent(role="writer"),
    ]
    crew = MCPCrew(agents=agents, all_tools=sample_tools)
    assert len(crew.agents) == 2

  def test_scoped_tools_per_agent_are_disjoint(self, sample_tools):
    analyst = ScopedAgent(role="analyst")
    writer = ScopedAgent(role="writer")
    crew = MCPCrew(agents=[analyst, writer], all_tools=sample_tools)

    analyst_names = {t["name"] for t in analyst.get_scoped_tools(sample_tools)}
    writer_names = {t["name"] for t in writer.get_scoped_tools(sample_tools)}
    # No overlap between analyst and writer tool sets for this fixture
    assert analyst_names.isdisjoint(writer_names)

  def test_orchestrator_sees_all_tools(self, sample_tools):
    orch = ScopedAgent(role="orchestrator")
    crew = MCPCrew(agents=[orch], all_tools=sample_tools)
    assert len(orch.get_scoped_tools(sample_tools)) == len(sample_tools)


# ---------------------------------------------------------------------------
# MCPCrew — native runner (mocked LLM)
# ---------------------------------------------------------------------------

class TestMCPCrewNativeRunner:
  @pytest.mark.asyncio
  async def test_native_runner_calls_each_agent(self, sample_tools):
    """Native runner should invoke an agent per ScopedAgent in order."""
    import unittest.mock as mock

    mock_result = mock.MagicMock()
    mock_result.data = "mocked llm output"
    mock_agent_instance = mock.AsyncMock()
    mock_agent_instance.run = mock.AsyncMock(return_value=mock_result)

    agents = [ScopedAgent(role="analyst"), ScopedAgent(role="writer")]
    crew = MCPCrew(agents=agents, all_tools=sample_tools)

    with mock.patch("pydantic_ai.Agent", return_value=mock_agent_instance):
      result = await crew._run_native("Test task")

    assert result.iterations == 2  # one per agent
    assert len(result.agent_results) == 2
    assert result.agent_results[0].role == "analyst"
    assert result.agent_results[1].role == "writer"

  @pytest.mark.asyncio
  async def test_native_runner_chains_output_as_context(self, sample_tools):
    """Each agent's output should become the next agent's task prompt."""
    import unittest.mock as mock

    call_prompts: list[str] = []

    async def fake_run(prompt: str):
      call_prompts.append(prompt)
      r = mock.MagicMock()
      r.data = f"output_for_{len(call_prompts)}"
      return r

    mock_agent = mock.MagicMock()
    mock_agent.run = fake_run

    agents = [ScopedAgent(role="analyst"), ScopedAgent(role="writer")]
    crew = MCPCrew(agents=agents, all_tools=sample_tools)

    with mock.patch("pydantic_ai.Agent", return_value=mock_agent):
      result = await crew._run_native("Initial task")

    # Second agent's prompt should contain the first agent's output
    assert "output_for_1" in call_prompts[1]

  @pytest.mark.asyncio
  async def test_native_runner_handles_agent_failure_gracefully(self, sample_tools):
    """A single agent failure should not crash the crew run."""
    import unittest.mock as mock

    mock_agent = mock.MagicMock()
    mock_agent.run = mock.AsyncMock(side_effect=RuntimeError("LLM timeout"))

    agents = [ScopedAgent(role="analyst")]
    crew = MCPCrew(agents=agents, all_tools=sample_tools)

    with mock.patch("pydantic_ai.Agent", return_value=mock_agent):
      result = await crew._run_native("Test task")

    assert result.agent_results[0].success is False
    assert "LLM timeout" in result.agent_results[0].error

  @pytest.mark.asyncio
  async def test_evaluator_callback_invoked(self, sample_tools):
    """Custom evaluator should be called on the final CrewResult."""
    import unittest.mock as mock

    evaluator_calls: list = []

    def my_evaluator(result):
      evaluator_calls.append(result)
      return True

    mock_result = mock.MagicMock()
    mock_result.data = "done"
    mock_agent = mock.MagicMock()
    mock_agent.run = mock.AsyncMock(return_value=mock_result)

    agents = [ScopedAgent(role="analyst")]
    crew = MCPCrew(agents=agents, all_tools=sample_tools, evaluator=my_evaluator)

    with mock.patch("pydantic_ai.Agent", return_value=mock_agent):
      result = await crew._run_native("Test")

    assert len(evaluator_calls) == 1
    assert result.passed_validation is True
