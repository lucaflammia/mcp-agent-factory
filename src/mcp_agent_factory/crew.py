"""
Layer 3: Multi-Agent Orchestration — Powered by CrewAI.

Coordinates complex multi-agent workflows by assigning modular, role-based
tasks to independent agent personas.  Each agent is scoped to an explicit
subset of MCP tools, enforcing strict security boundaries and minimising
context noise.

Architecture:
  [MCPCrew]
    ├── ScopedAgent(role="analyst",  tools=[read_*, search_*])
    ├── ScopedAgent(role="writer",   tools=[write_*, format_*])
    └── ScopedAgent(role="db_agent", tools=[sql_*])

  MCPCrew.kickoff(task) → delegates to CrewAI sequential/hierarchical process
  when the 'crewai' package is installed, otherwise falls back to a native
  sequential runner that respects the same tool scopes and contracts.

Usage::

  from mcp_agent_factory.crew import MCPCrew, ScopedAgent, ROLE_TOOL_PATTERNS

  agents = [
    ScopedAgent(role="analyst",  allowed_patterns=["read", "search", "fetch"]),
    ScopedAgent(role="writer",   allowed_patterns=["write", "format", "publish"]),
  ]
  crew = MCPCrew(agents=agents, all_tools=tool_list)
  result = await crew.kickoff("Summarise Q3 sales and publish to Confluence")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default role → tool-pattern mapping
# Patterns are substring-matched against tool names (case-insensitive).
# ---------------------------------------------------------------------------

ROLE_TOOL_PATTERNS: dict[str, list[str]] = {
  "analyst": ["read", "search", "fetch", "list", "get", "describe"],
  "writer": ["write", "create", "update", "format", "publish", "send"],
  "db_agent": ["sql", "query", "select", "insert", "upsert", "delete"],
  "librarian": ["embed", "ingest", "index", "retrieve", "vector"],
  "orchestrator": [],  # orchestrator sees all tools by convention
}


# ---------------------------------------------------------------------------
# Tool scoping helpers
# ---------------------------------------------------------------------------

def scope_tools(
  role: str,
  tools: list[dict[str, Any]],
  allowed_patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
  """
  Return the subset of *tools* that the *role* is permitted to invoke.

  If *allowed_patterns* is provided it overrides the default ROLE_TOOL_PATTERNS
  for this role.  The orchestrator role always receives every tool.

  Args:
    role: Agent role name (e.g. "analyst").
    tools: Full list of MCP tool descriptors (each has a "name" key).
    allowed_patterns: Optional override; if None uses ROLE_TOOL_PATTERNS[role].

  Returns:
    Filtered list of tool descriptors accessible to the role.
  """
  if role == "orchestrator":
    return list(tools)

  patterns = allowed_patterns if allowed_patterns is not None else ROLE_TOOL_PATTERNS.get(role, [])
  if not patterns:
    logger.warning("scope_tools: role %r has no patterns — returning empty tool set", role)
    return []

  scoped = [
    t for t in tools
    if any(pat.lower() in t.get("name", "").lower() for pat in patterns)
  ]
  logger.debug(
    "scope_tools: role=%r patterns=%r → %d/%d tools",
    role, patterns, len(scoped), len(tools),
  )
  return scoped


def build_scoped_call_fn(
  role: str,
  scoped_tools: list[dict[str, Any]],
  base_call_fn: Callable[[str, dict[str, Any]], Any],
) -> Callable[[str, dict[str, Any]], Any]:
  """
  Wrap *base_call_fn* so that only calls to tools in *scoped_tools* are allowed.

  Any attempt to invoke a tool outside the permitted set raises
  ``PermissionError``, providing a hard security boundary that prevents
  agents from escalating beyond their assigned scope.

  Args:
    role: Agent role label (used in error messages).
    scoped_tools: The filtered tool list returned by ``scope_tools``.
    base_call_fn: The underlying MCP tool-call function.

  Returns:
    A wrapped callable with the same signature as *base_call_fn*.
  """
  allowed_names: set[str] = {t["name"] for t in scoped_tools}

  def scoped_call(tool_name: str, arguments: dict[str, Any]) -> Any:
    if tool_name not in allowed_names:
      raise PermissionError(
        f"Agent role {role!r} is not permitted to call tool {tool_name!r}. "
        f"Allowed tools: {sorted(allowed_names)}"
      )
    return base_call_fn(tool_name, arguments)

  return scoped_call


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

class AgentTask(BaseModel):
  """A unit of work assigned to a single agent in the crew."""
  description: str = Field(..., min_length=1)
  expected_output: str = Field(default="", description="What a successful result looks like")
  role: str = Field(..., description="The agent role responsible for this task")
  context: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
  """Output produced by one agent for one task."""
  role: str
  task_description: str
  output: str | dict[str, Any]
  success: bool
  error: str | None = None


class CrewResult(BaseModel):
  """Aggregated result from the full crew execution."""
  final_output: str | dict[str, Any]
  agent_results: list[AgentResult]
  iterations: int
  passed_validation: bool


# ---------------------------------------------------------------------------
# ScopedAgent
# ---------------------------------------------------------------------------

@dataclass
class ScopedAgent:
  """
  A single agent persona bound to a filtered subset of MCP tools.

  Attributes:
    role: Semantic label (must match a key in ROLE_TOOL_PATTERNS or provide
          allowed_patterns explicitly).
    allowed_patterns: Substring patterns used to filter MCP tools.  If None,
                      falls back to ROLE_TOOL_PATTERNS[role].
    system_prompt: Persona-level system prompt injected at task execution time.
    model_name: The LLM model used by this agent.
  """
  role: str
  allowed_patterns: list[str] | None = None
  system_prompt: str = ""
  model_name: str = field(
    default_factory=lambda: __import__("os").getenv(
      "PYDANTIC_AI_MODEL", "gemini-2.5-flash"
    )
  )

  def get_scoped_tools(self, all_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the filtered tool subset this agent may call."""
    return scope_tools(self.role, all_tools, self.allowed_patterns)

  def get_persona(self) -> str:
    """Return the effective system prompt, including a role preamble."""
    preamble = (
      f"You are the {self.role} agent in a multi-agent pipeline. "
      "Complete your assigned task using ONLY the tools available to you. "
      "Return a concise, structured result."
    )
    if self.system_prompt:
      return f"{preamble}\n\n{self.system_prompt}"
    return preamble


# ---------------------------------------------------------------------------
# MCPCrew — orchestrator
# ---------------------------------------------------------------------------

class MCPCrew:
  """
  Multi-agent crew that coordinates specialised agents over a shared task.

  Execution strategy (in priority order):
  1. **CrewAI** — if ``crewai`` is installed, delegates to its sequential or
    hierarchical process, leveraging its built-in memory and delegation.
  2. **LangGraph-backed runner** — when ``use_langgraph=True``, each agent's
    subtask is executed through the ``GraphOrchestrator`` FSM, inheriting
    bounded depth, transactional checkpointing, and critic evaluation.
  3. **Native sequential runner** — falls back to an in-process loop that
    passes each agent's output as context to the next agent in the chain.

  Both paths enforce tool scoping via ``build_scoped_call_fn``.

  Args:
    agents: Ordered list of ScopedAgent instances (execution order matters).
    all_tools: Complete MCP tool descriptor list.
    call_tool_fn: Async or sync callable ``(tool_name, arguments) → Any``.
    process: "sequential" (default) or "hierarchical".
    evaluator: Optional callable that receives the final CrewResult and
      returns ``True`` if the output meets quality requirements.
    use_langgraph: When True, delegate per-agent execution through the
      Layer 2 LangGraph ``GraphOrchestrator`` state machine.
  """

  def __init__(
    self,
    agents: list[ScopedAgent],
    all_tools: list[dict[str, Any]],
    call_tool_fn: Callable[[str, dict[str, Any]], Any] | None = None,
    process: str = "sequential",
    evaluator: Callable[[CrewResult], bool] | None = None,
    use_langgraph: bool = False,
  ) -> None:
    self.agents = agents
    self.all_tools = all_tools
    self.call_tool_fn = call_tool_fn
    self.process = process
    self.evaluator = evaluator
    self.use_langgraph = use_langgraph

  # ------------------------------------------------------------------
  # Public API
  # ------------------------------------------------------------------

  async def kickoff(self, task: str) -> CrewResult:
    """
    Execute the crew on *task*.

    Tries CrewAI first; falls back to the native runner if CrewAI is not
    installed or raises an import error.

    Args:
      task: The high-level task description for the crew.

    Returns:
      CrewResult aggregating all agent outputs.
    """
    try:
      return await self._run_with_crewai(task)
    except ImportError:
      if self.use_langgraph:
        logger.info("crewai not installed — using LangGraph-backed runner")
        return await self._run_with_langgraph(task)
      logger.info("crewai not installed — using native sequential runner")
      return await self._run_native(task)

  # ------------------------------------------------------------------
  # CrewAI backend
  # ------------------------------------------------------------------

  def _get_crewai_llm(self, model_name: str) -> Any:
    """
    Create a CrewAI-compatible LLM instance for Gemini.
    Requires GEMINI_API_KEY environment variable to be set.
    """
    import os
    try:
      from crewai import LLM

      # Check if API key is available
      api_key = os.getenv("GEMINI_API_KEY")
      if not api_key:
        logger.warning("GEMINI_API_KEY not set — CrewAI will use default provider chain")

      # For Gemini models, use the google provider
      if "gemini" in model_name.lower():
        return LLM(model=model_name, provider="google", api_key=api_key if api_key else None)

      # Fallback for other models
      return LLM(model=model_name)
    except ImportError as e:
      logger.error("Could not import CrewAI LLM: %s", e)
      raise
    except Exception as e:
      logger.error("Failed to instantiate LLM: %s", e)
      raise

  async def _run_with_crewai(self, task: str) -> CrewResult:
    """Delegate execution to CrewAI."""
    import asyncio
    from crewai import Agent as CrewAIAgent, Task as CrewAITask, Crew, Process

    crewai_agents = []
    crewai_tasks = []
    agent_results: list[AgentResult] = []

    for i, scoped_agent in enumerate(self.agents):
      scoped = scoped_agent.get_scoped_tools(self.all_tools)
      scoped_call = (
        build_scoped_call_fn(scoped_agent.role, scoped, self.call_tool_fn)
        if self.call_tool_fn else None
      )

      # Wrap MCP tools as CrewAI-compatible tool objects
      crewai_tool_list = self._wrap_tools_for_crewai(scoped, scoped_call)

      ca = CrewAIAgent(
        role=scoped_agent.role,
        goal=f"Complete your portion of: {task}",
        backstory=scoped_agent.get_persona(),
        tools=crewai_tool_list,
        verbose=False,
        allow_delegation=(self.process == "hierarchical" and i == 0),
        llm=self._get_crewai_llm(scoped_agent.model_name),
      )
      crewai_agents.append(ca)

      ct = CrewAITask(
        description=task if i == 0 else f"Process and refine previous agent output for: {task}",
        expected_output="Structured result satisfying the task requirements",
        agent=ca,
      )
      crewai_tasks.append(ct)

    process_type = Process.sequential if self.process == "sequential" else Process.hierarchical
    crew = Crew(
      agents=crewai_agents,
      tasks=crewai_tasks,
      process=process_type,
      verbose=False,
    )

    # CrewAI's kickoff is sync; run in executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    try:
      raw_result = await loop.run_in_executor(None, crew.kickoff)
      final_output = str(raw_result) if raw_result else ""
    except Exception as e:
      logger.error("CrewAI kickoff failed: %s", e)
      raise

    # Build per-agent results (CrewAI rolls up; we synthesise from tasks)
    for i, (scoped_agent, ct) in enumerate(zip(self.agents, crewai_tasks)):
      agent_results.append(AgentResult(
        role=scoped_agent.role,
        task_description=ct.description,
        output=ct.output.raw if hasattr(ct, "output") and ct.output else final_output,
        success=True,
      ))

    result = CrewResult(
      final_output=final_output,
      agent_results=agent_results,
      iterations=1,
      passed_validation=True,
    )

    if self.evaluator:
      result = CrewResult(
        **{**result.model_dump(), "passed_validation": self.evaluator(result)}
      )

    return result

  def _wrap_tools_for_crewai(
    self,
    scoped_tools: list[dict[str, Any]],
    call_fn: Callable[[str, dict[str, Any]], Any] | None,
  ) -> list[Any]:
    """Convert MCP tool descriptors to CrewAI BaseTool instances."""
    if not call_fn:
      return []

    try:
      from crewai.tools import BaseTool as CrewAIBaseTool

      wrapped = []
      for t in scoped_tools:
        tool_name = t["name"]
        tool_desc = t.get("description", "")

        class _MCPTool(CrewAIBaseTool):
          name: str = tool_name
          description: str = tool_desc
          _call_fn: Any = call_fn
          _mcp_tool_name: str = tool_name

          def _run(self, **kwargs: Any) -> Any:
            return self._call_fn(self._mcp_tool_name, kwargs)

        wrapped.append(_MCPTool())
      return wrapped
    except Exception as exc:
      logger.warning("Could not wrap tools for CrewAI: %s", exc)
      return []

  # ------------------------------------------------------------------
  # LangGraph-backed runner (Layer 2 integration)
  # ------------------------------------------------------------------

  async def _run_with_langgraph(self, task: str) -> CrewResult:
    """
    Execute each agent's subtask through the Layer 2 GraphOrchestrator FSM.

    Each agent gets its scoped tool subset passed into the graph, which runs
    the full VALIDATE→PLAN→EXECUTE→EVALUATE loop with bounded depth and
    transactional checkpointing.
    """
    from mcp_agent_factory.graph_orchestrator import GraphOrchestrator

    agent_results: list[AgentResult] = []
    context: str = task

    for i, scoped_agent in enumerate(self.agents):
      scoped = scoped_agent.get_scoped_tools(self.all_tools)
      scoped_call = (
        build_scoped_call_fn(scoped_agent.role, scoped, self.call_tool_fn)
        if self.call_tool_fn else None
      )

      graph = GraphOrchestrator(model_name=scoped_agent.model_name)
      try:
        state = await graph.run(
          task=context,
          tools=scoped,
          call_tool_fn=scoped_call or (lambda n, a: {}),
          thread_id=f"crew-{scoped_agent.role}-{i}",
        )
        phase = state.get("phase", "")
        if phase == "done":
          output = state.get("final_result", {}).get("text", str(state.get("final_result", "")))
          agent_results.append(AgentResult(
            role=scoped_agent.role,
            task_description=context,
            output=output,
            success=True,
          ))
          context = output
        else:
          error = state.get("error", "Graph did not reach DONE")
          agent_results.append(AgentResult(
            role=scoped_agent.role,
            task_description=context,
            output="",
            success=False,
            error=error,
          ))
      except Exception as exc:
        logger.error("langgraph runner: agent %r failed: %s", scoped_agent.role, exc)
        agent_results.append(AgentResult(
          role=scoped_agent.role,
          task_description=context,
          output="",
          success=False,
          error=str(exc),
        ))

    final_output = agent_results[-1].output if agent_results else ""
    result = CrewResult(
      final_output=final_output,
      agent_results=agent_results,
      iterations=len(self.agents),
      passed_validation=all(r.success for r in agent_results),
    )

    if self.evaluator:
      result = CrewResult(
        **{**result.model_dump(), "passed_validation": self.evaluator(result)}
      )

    return result

  # ------------------------------------------------------------------
  # Native sequential runner
  # ------------------------------------------------------------------

  async def _run_native(self, task: str) -> CrewResult:
    """
    Native fallback: run agents sequentially, passing each output as
    context into the next agent's task prompt.
    """
    import asyncio
    from pydantic_ai import Agent as PydanticAgent

    agent_results: list[AgentResult] = []
    context: str = task

    for scoped_agent in self.agents:
      scoped = scoped_agent.get_scoped_tools(self.all_tools)
      scoped_call = (
        build_scoped_call_fn(scoped_agent.role, scoped, self.call_tool_fn)
        if self.call_tool_fn else None
      )

      tool_summary = ", ".join(t["name"] for t in scoped) or "(none)"
      prompt = (
        f"Task: {context}\n\n"
        f"You have access to these tools: {tool_summary}\n"
        "Complete your portion of the task and return a concise result."
      )

      try:
        pa: PydanticAgent[None, str] = PydanticAgent(
          scoped_agent.model_name,
          system_prompt=scoped_agent.get_persona(),
        )
        result = await pa.run(prompt)
        output = result.data if isinstance(result.data, str) else str(result.data)
        agent_results.append(AgentResult(
          role=scoped_agent.role,
          task_description=context,
          output=output,
          success=True,
        ))
        # Feed this agent's output as context for the next
        context = output
      except Exception as exc:
        logger.error("native runner: agent %r failed: %s", scoped_agent.role, exc)
        agent_results.append(AgentResult(
          role=scoped_agent.role,
          task_description=context,
          output="",
          success=False,
          error=str(exc),
        ))

    final_output = agent_results[-1].output if agent_results else ""
    result = CrewResult(
      final_output=final_output,
      agent_results=agent_results,
      iterations=len(self.agents),
      passed_validation=all(r.success for r in agent_results),
    )

    if self.evaluator:
      result = CrewResult(
        **{**result.model_dump(), "passed_validation": self.evaluator(result)}
      )

    return result
