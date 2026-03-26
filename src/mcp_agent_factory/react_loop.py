"""
ReActAgent — Perception → Reasoning → Action → Observation → Synthesis cycle.

Observability: each step is logged at DEBUG level with type, tool_name, and
content so callers can reconstruct the full reasoning trace post-mortem.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel

from mcp_agent_factory.orchestrator import MCPOrchestrator

logger = logging.getLogger(__name__)


class ReActStep(BaseModel):
    type: str  # 'thought' | 'action' | 'observation'
    content: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None


class ReActResult(BaseModel):
    task: str
    steps: list[ReActStep]
    answer: str
    success: bool


class ReActAgent:
    """Wraps MCPOrchestrator and executes the full ReAct loop."""

    def __init__(self, orchestrator: MCPOrchestrator) -> None:
        self.orc = orchestrator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str) -> ReActResult:
        steps: list[ReActStep] = []

        # 1. Perception
        tools = self.orc.list_tools()
        tool_names = [t["name"] for t in tools]
        logger.debug("perception: available tools=%s", tool_names)

        # 2. Reasoning
        selected = self._select_tool(task, tool_names)
        thought_content = (
            f"Selected tool: {selected}" if selected else "No suitable tool found"
        )
        steps.append(ReActStep(type="thought", content=thought_content))
        logger.debug("reasoning: %s", thought_content)

        if selected is None:
            return ReActResult(
                task=task,
                steps=steps,
                answer="No suitable tool found",
                success=False,
            )

        # 3. Action
        args = self._extract_args(task, selected)
        steps.append(
            ReActStep(
                type="action",
                content=f"call {selected}",
                tool_name=selected,
                tool_args=args,
            )
        )
        logger.debug("action: call %s args=%s", selected, args)
        result = self.orc.call_tool(selected, args)

        # 4. Observation
        try:
            obs = result["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            obs = str(result)
        success = not result.get("isError", False)
        steps.append(ReActStep(type="observation", content=obs))
        logger.debug("observation: %s success=%s", obs, success)

        # 5. Synthesis
        return ReActResult(task=task, steps=steps, answer=obs, success=success)

    # ------------------------------------------------------------------
    # Rule-based tool selector
    # ------------------------------------------------------------------

    @staticmethod
    def _select_tool(task: str, tool_names: list[str]) -> str | None:
        lower = task.lower()
        # echo: explicit keyword or quoted string present
        if "echo" in lower or re.search(r'"[^"]+"', task):
            if "echo" in tool_names:
                return "echo"
        # add: digits + arithmetic keyword
        if re.search(r"\d", task) and re.search(
            r"\badd\b|\bsum\b|\bplus\b|\+", lower
        ):
            if "add" in tool_names:
                return "add"
        return None

    # ------------------------------------------------------------------
    # Arg extraction per tool
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_args(task: str, tool_name: str) -> dict[str, Any]:
        if tool_name == "echo":
            m = re.search(r'"([^"]+)"', task)
            if m:
                return {"message": m.group(1)}
            return {"message": task.split()[-1]}
        if tool_name == "add":
            nums = re.findall(r"[-+]?\d+\.?\d*", task)
            a = float(nums[0]) if len(nums) > 0 else 0.0
            b = float(nums[1]) if len(nums) > 1 else 0.0
            return {"a": a, "b": b}
        return {}
