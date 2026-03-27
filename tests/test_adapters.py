"""
Tests for LLM function-calling adapters.

Verifies that ClaudeAdapter, OpenAIAdapter, and GeminiAdapter produce
correctly-shaped payloads from MCP tool descriptors.
"""
from __future__ import annotations

import pytest

from mcp_agent_factory.adapters import (
	ClaudeAdapter,
	GeminiAdapter,
	LLMAdapterFactory,
	OpenAIAdapter,
)

# Fixture: two MCP tools (same shape as tools/list response)
MCP_TOOLS = [
	{
		"name": "echo",
		"description": "Returns the input message unchanged.",
		"inputSchema": {
			"type": "object",
			"properties": {
				"message": {"type": "string", "description": "Text to echo back"}
			},
			"required": ["message"],
		},
	},
	{
		"name": "add",
		"description": "Returns the sum of two numbers.",
		"inputSchema": {
			"type": "object",
			"properties": {
				"a": {"type": "number", "description": "First operand"},
				"b": {"type": "number", "description": "Second operand"},
			},
			"required": ["a", "b"],
		},
	},
]


# ---------------------------------------------------------------------------
# Claude adapter
# ---------------------------------------------------------------------------

class TestClaudeAdapter:
	def test_claude_adapter_shape(self):
		result = ClaudeAdapter().adapt(MCP_TOOLS)
		assert len(result) == 2
		for tool in result:
			assert "name" in tool
			assert "description" in tool
			assert "input_schema" in tool
			assert tool["input_schema"]["type"] == "object"

	def test_claude_adapter_no_extra_keys(self):
		result = ClaudeAdapter().adapt(MCP_TOOLS)
		for tool in result:
			# Should NOT have 'inputSchema' (MCP key) — only 'input_schema' (Claude key)
			assert "inputSchema" not in tool

	def test_claude_preserves_required(self):
		result = ClaudeAdapter().adapt(MCP_TOOLS)
		echo = next(t for t in result if t["name"] == "echo")
		assert echo["input_schema"]["required"] == ["message"]


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

class TestOpenAIAdapter:
	def test_openai_adapter_shape(self):
		result = OpenAIAdapter().adapt(MCP_TOOLS)
		assert len(result) == 2
		for tool in result:
			assert tool["type"] == "function"
			assert "function" in tool
			fn = tool["function"]
			assert "name" in fn
			assert "description" in fn
			assert "parameters" in fn
			assert fn["parameters"]["type"] == "object"

	def test_openai_preserves_required(self):
		result = OpenAIAdapter().adapt(MCP_TOOLS)
		add = next(t for t in result if t["function"]["name"] == "add")
		assert set(add["function"]["parameters"]["required"]) == {"a", "b"}


# ---------------------------------------------------------------------------
# Gemini adapter
# ---------------------------------------------------------------------------

class TestGeminiAdapter:
	def test_gemini_adapter_shape(self):
		result = GeminiAdapter().adapt(MCP_TOOLS)
		assert len(result) == 2
		for tool in result:
			assert "name" in tool
			assert "description" in tool
			assert "parameters" in tool
			# Gemini uses uppercase type
			assert tool["parameters"]["type"] == "OBJECT"

	def test_gemini_property_types_uppercase(self):
		result = GeminiAdapter().adapt(MCP_TOOLS)
		echo = next(t for t in result if t["name"] == "echo")
		msg_type = echo["parameters"]["properties"]["message"]["type"]
		assert msg_type == "STRING"

	def test_gemini_number_type_uppercase(self):
		result = GeminiAdapter().adapt(MCP_TOOLS)
		add = next(t for t in result if t["name"] == "add")
		a_type = add["parameters"]["properties"]["a"]["type"]
		assert a_type == "NUMBER"

	def test_gemini_preserves_required(self):
		result = GeminiAdapter().adapt(MCP_TOOLS)
		add = next(t for t in result if t["name"] == "add")
		assert set(add["parameters"]["required"]) == {"a", "b"}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestLLMAdapterFactory:
	def test_factory_returns_claude(self):
		assert isinstance(LLMAdapterFactory.get("claude"), ClaudeAdapter)

	def test_factory_returns_openai(self):
		assert isinstance(LLMAdapterFactory.get("openai"), OpenAIAdapter)

	def test_factory_returns_gemini(self):
		assert isinstance(LLMAdapterFactory.get("gemini"), GeminiAdapter)

	def test_factory_case_insensitive(self):
		assert isinstance(LLMAdapterFactory.get("Claude"), ClaudeAdapter)
		assert isinstance(LLMAdapterFactory.get("GEMINI"), GeminiAdapter)

	def test_factory_unknown_raises_value_error(self):
		with pytest.raises(ValueError, match="Unknown LLM provider"):
			LLMAdapterFactory.get("unknown")


# ---------------------------------------------------------------------------
# Cross-adapter: shared invariants
# ---------------------------------------------------------------------------

class TestAdapterInvariants:
	@pytest.mark.parametrize("provider", ["claude", "openai", "gemini"])
	def test_preserves_tool_names(self, provider):
		adapter = LLMAdapterFactory.get(provider)
		result = adapter.adapt(MCP_TOOLS)
		names = {t.get("name") or t.get("function", {}).get("name") for t in result}
		assert "echo" in names
		assert "add" in names

	@pytest.mark.parametrize("provider", ["claude", "openai", "gemini"])
	def test_preserves_descriptions(self, provider):
		adapter = LLMAdapterFactory.get(provider)
		result = adapter.adapt(MCP_TOOLS)
		for tool in result:
			desc = tool.get("description") or tool.get("function", {}).get("description", "")
			assert len(desc) > 0

	@pytest.mark.parametrize("provider", ["claude", "openai", "gemini"])
	def test_does_not_mutate_input(self, provider):
		import copy
		original = copy.deepcopy(MCP_TOOLS)
		adapter = LLMAdapterFactory.get(provider)
		adapter.adapt(MCP_TOOLS)
		assert MCP_TOOLS == original
