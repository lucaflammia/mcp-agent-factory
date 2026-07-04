"""Tests for PydanticAI StructuredAgent — validates structured output contracts."""
from __future__ import annotations

import pytest

from mcp_agent_factory.structured_agent import AgentResponse, StructuredAgent, ToolArgument, ToolSelection


# ---------------------------------------------------------------------------
# Unit: ToolSelection model validation
# ---------------------------------------------------------------------------

def test_tool_selection_valid():
	ts = ToolSelection(
		tool_name="echo",
		arguments=[ToolArgument(key="message", value="hi")],
		reasoning="User wants to echo a message",
	)
	assert ts.tool_name == "echo"
	assert ts.arguments_as_dict() == {"message": "hi"}


def test_tool_selection_rejects_empty_name():
	with pytest.raises(Exception):
		ToolSelection(tool_name="", arguments=[], reasoning="no tool")


# ---------------------------------------------------------------------------
# Unit: AgentResponse model
# ---------------------------------------------------------------------------

def test_agent_response_model():
	r = AgentResponse(
		task="echo hello",
		tool_used="echo",
		tool_args={"message": "hello"},
		result="hello",
		success=True,
		reasoning="echo matches",
	)
	assert r.success
	assert r.tool_used == "echo"


# ---------------------------------------------------------------------------
# Integration: StructuredAgent with mock call_tool
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
	{
		"name": "add",
		"description": "Returns sum of two numbers",
		"inputSchema": {
			"type": "object",
			"properties": {
				"a": {"type": "number"},
				"b": {"type": "number"},
			},
			"required": ["a", "b"],
		},
	},
]


@pytest.mark.integration
async def test_structured_agent_echo():
	"""Run the full PydanticAI agent against a mock tool executor.
	Requires GEMINI_API_KEY or a running Ollama instance.
	"""
	import os
	if not os.getenv("GEMINI_API_KEY") and not os.getenv("OLLAMA_BASE_URL"):
		pytest.skip("No LLM provider configured")

	async def mock_call_tool(name: str, args: dict) -> dict:
		if name == "echo":
			return {"content": [{"type": "text", "text": args.get("message", "")}]}
		if name == "add":
			return {"content": [{"type": "text", "text": str(args.get("a", 0) + args.get("b", 0))}]}
		return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}

	agent = StructuredAgent()
	result = await agent.run('echo "hello world"', MOCK_TOOLS, mock_call_tool)
	assert result.success
	assert result.tool_used == "echo"
	assert "hello" in result.result.lower()
