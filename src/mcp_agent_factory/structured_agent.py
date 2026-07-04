"""
PydanticAI Structured Agent — LLM-driven tool selection with validated I/O.

Replaces the regex-based ReActAgent with a PydanticAI agent that uses
Gemini (or any supported provider) to select tools and extract arguments
via native structured outputs. Every LLM response is type-validated
before execution — malformed outputs trigger retries, never execution.

Gate: set ORCHESTRATOR_MODE=pydantic_ai to use this path.
Legacy ReActAgent remains available at ORCHESTRATOR_MODE=legacy.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_additional_properties(schema: dict) -> None:
	"""Remove additionalProperties recursively — Gemini rejects it."""
	schema.pop("additionalProperties", None)
	for value in schema.get("properties", {}).values():
		if isinstance(value, dict):
			_strip_additional_properties(value)
	for sub in schema.get("$defs", {}).values():
		if isinstance(sub, dict):
			_strip_additional_properties(sub)


# ---------------------------------------------------------------------------
# Structured output contracts
# ---------------------------------------------------------------------------

class ToolArgument(BaseModel):
	"""A single key-value argument for a tool call."""
	model_config = ConfigDict(extra="ignore")

	key: str = Field(..., description="Argument name")
	value: str = Field(..., description="Argument value (serialize non-strings as JSON)")


class ToolSelection(BaseModel):
	"""LLM's validated decision on which tool to call and with what args."""
	model_config = ConfigDict(extra="ignore")

	tool_name: str = Field(..., min_length=1, description="Name of the tool to invoke")
	arguments: list[ToolArgument] = Field(
		default_factory=list,
		description="List of key-value argument pairs for the tool",
	)
	reasoning: str = Field(
		..., description="One-line explanation of why this tool was selected",
	)

	def arguments_as_dict(self) -> dict[str, Any]:
		"""Convert argument list to a dict, attempting numeric coercion."""
		result: dict[str, Any] = {}
		for arg in self.arguments:
			v: Any = arg.value
			for cast in (int, float):
				try:
					v = cast(arg.value)
					break
				except (ValueError, TypeError):
					pass
			result[arg.key] = v
		return result


class AgentResponse(BaseModel):
	"""Final structured response from the agent after tool execution."""
	task: str
	tool_used: str
	tool_args: dict[str, Any]
	result: str
	success: bool
	reasoning: str


# ---------------------------------------------------------------------------
# PydanticAI structured agent
# ---------------------------------------------------------------------------

@dataclass
class StructuredAgent:
	"""
	Uses PydanticAI + Gemini to select and invoke tools with validated I/O.

	The agent receives a task description and available tool schemas,
	asks the LLM to pick a tool and extract arguments (returned as a
	ToolSelection model), then executes the selected tool via the
	MCPOrchestrator.
	"""
	model_name: str = field(
		default_factory=lambda: os.getenv("PYDANTIC_AI_MODEL", "google-gla:gemini-2.5-flash")
	)
	max_retries: int = 2

	async def run(
		self,
		task: str,
		tools: list[dict[str, Any]],
		call_tool_fn,
	) -> AgentResponse:
		"""
		Select a tool via LLM structured output, then execute it.

		Args:
			task: Natural language task description.
			tools: List of MCP tool descriptors (name, description, inputSchema).
			call_tool_fn: Async or sync callable(name, args) -> result dict.

		Returns:
			AgentResponse with validated execution result.
		"""
		from pydantic_ai import Agent

		tool_descriptions = "\n".join(
			f"- {t['name']}: {t.get('description', 'no description')} "
			f"(schema: {t.get('inputSchema', {})})"
			for t in tools
		)

		system_prompt = (
			"You are a tool-selection agent. Given a user task and available tools, "
			"select the single best tool and extract ALL required arguments from the task.\n\n"
			f"Available tools:\n{tool_descriptions}\n\n"
			"IMPORTANT: Populate the 'arguments' field with the exact key-value pairs "
			"matching the tool's inputSchema. Do not leave arguments empty if the tool requires them."
		)

		agent: Agent[None, ToolSelection] = Agent(
			self.model_name,
			system_prompt=system_prompt,
			result_type=ToolSelection,
			retries=self.max_retries,
		)

		try:
			result = await agent.run(task)
			selection: ToolSelection = result.data
		except Exception as exc:
			logger.error("LLM tool selection failed: %s", exc)
			return AgentResponse(
				task=task,
				tool_used="",
				tool_args={},
				result=f"Tool selection failed: {exc}",
				success=False,
				reasoning="LLM structured output failed",
			)

		logger.debug(
			"tool_selection tool=%s args=%s reasoning=%s",
			selection.tool_name, selection.arguments_as_dict(), selection.reasoning,
		)

		# Validate selected tool exists
		available_names = {t["name"] for t in tools}
		if selection.tool_name not in available_names:
			return AgentResponse(
				task=task,
				tool_used=selection.tool_name,
				tool_args=selection.arguments_as_dict(),
				result=f"Tool {selection.tool_name!r} not in available tools: {available_names}",
				success=False,
				reasoning=selection.reasoning,
			)

		# Execute the selected tool
		import asyncio
		try:
			if asyncio.iscoroutinefunction(call_tool_fn):
				tool_result = await call_tool_fn(selection.tool_name, selection.arguments_as_dict())
			else:
				tool_result = call_tool_fn(selection.tool_name, selection.arguments_as_dict())
		except Exception as exc:
			logger.error("tool execution failed: %s", exc)
			return AgentResponse(
				task=task,
				tool_used=selection.tool_name,
				tool_args=selection.arguments_as_dict(),
				result=f"Execution error: {exc}",
				success=False,
				reasoning=selection.reasoning,
			)

		# Extract text result
		try:
			text = tool_result["content"][0]["text"]
		except (KeyError, IndexError, TypeError):
			text = str(tool_result)
		is_error = tool_result.get("isError", False)

		return AgentResponse(
			task=task,
			tool_used=selection.tool_name,
			tool_args=selection.arguments_as_dict(),
			result=text,
			success=not is_error,
			reasoning=selection.reasoning,
		)
