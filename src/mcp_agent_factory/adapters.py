"""
LLM function-calling adapters.

Translates MCP tool descriptors (tools/list format) into the native
function-calling schema for each major LLM provider.

Providers:
  - claude   → Anthropic tool format (input_schema)
  - openai   → OpenAI tools format  (type='function', function.parameters)
  - gemini   → Google function declarations (parameters.type='OBJECT')

All adapters are schema-translation only — no live API calls are made.

Usage::

	from mcp_agent_factory.adapters import LLMAdapterFactory

	adapter = LLMAdapterFactory.get("claude")
	claude_tools = adapter.adapt(mcp_tools)
"""
from __future__ import annotations

import copy
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class LLMAdapter(ABC):
	"""Translates a list of MCP tool descriptors into a provider-specific format."""

	@abstractmethod
	def adapt(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
		...

	def _log(self, provider: str, result: list) -> None:
		logger.debug(json.dumps({"event": "adapter_output", "provider": provider, "count": len(result)}))


# ---------------------------------------------------------------------------
# Claude (Anthropic)
# ---------------------------------------------------------------------------

class ClaudeAdapter(LLMAdapter):
	"""
	Anthropic Claude function-calling schema.

	Output shape::

		{
			"name": "echo",
			"description": "...",
			"input_schema": {
				"type": "object",
				"properties": {...},
				"required": [...]
			}
		}
	"""

	def adapt(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
		result = []
		for tool in tools:
			schema = copy.deepcopy(tool.get("inputSchema", {}))
			result.append({
				"name": tool["name"],
				"description": tool.get("description", ""),
				"input_schema": schema,
			})
		self._log("claude", result)
		return result


# ---------------------------------------------------------------------------
# OpenAI (GPT)
# ---------------------------------------------------------------------------

class OpenAIAdapter(LLMAdapter):
	"""
	OpenAI function-calling schema (tools format).

	Output shape::

		{
			"type": "function",
			"function": {
				"name": "echo",
				"description": "...",
				"parameters": {
					"type": "object",
					"properties": {...},
					"required": [...]
				}
			}
		}
	"""

	def adapt(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
		result = []
		for tool in tools:
			schema = copy.deepcopy(tool.get("inputSchema", {}))
			result.append({
				"type": "function",
				"function": {
					"name": tool["name"],
					"description": tool.get("description", ""),
					"parameters": schema,
				},
			})
		self._log("openai", result)
		return result


# ---------------------------------------------------------------------------
# Gemini (Google)
# ---------------------------------------------------------------------------

class GeminiAdapter(LLMAdapter):
	"""
	Google Gemini function declarations schema.

	Key difference from OpenAI/Claude: type field uses uppercase 'OBJECT',
	property types use uppercase ('STRING', 'NUMBER', etc.).

	Output shape::

		{
			"name": "echo",
			"description": "...",
			"parameters": {
				"type": "OBJECT",
				"properties": {
					"message": {"type": "STRING", "description": "..."}
				},
				"required": ["message"]
			}
		}
	"""

	_TYPE_MAP = {
		"string": "STRING",
		"number": "NUMBER",
		"integer": "INTEGER",
		"boolean": "BOOLEAN",
		"array": "ARRAY",
		"object": "OBJECT",
	}

	def adapt(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
		result = []
		for tool in tools:
			schema = copy.deepcopy(tool.get("inputSchema", {}))
			result.append({
				"name": tool["name"],
				"description": tool.get("description", ""),
				"parameters": self._convert_schema(schema),
			})
		self._log("gemini", result)
		return result

	def _convert_schema(self, schema: dict) -> dict:
		"""Recursively convert JSON Schema types to Gemini uppercase format."""
		converted = {}
		for key, value in schema.items():
			if key == "type" and isinstance(value, str):
				converted[key] = self._TYPE_MAP.get(value.lower(), value.upper())
			elif key == "properties" and isinstance(value, dict):
				converted[key] = {
					k: self._convert_schema(v) for k, v in value.items()
				}
			else:
				converted[key] = value
		return converted


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class LLMAdapterFactory:
	"""Returns the appropriate adapter for a given LLM provider name."""

	_REGISTRY: dict[str, type[LLMAdapter]] = {
		"claude": ClaudeAdapter,
		"openai": OpenAIAdapter,
		"gemini": GeminiAdapter,
	}

	@classmethod
	def get(cls, provider: str) -> LLMAdapter:
		"""
		Return an adapter instance for *provider*.

		Raises ValueError for unknown providers.
		"""
		provider_key = provider.lower()
		if provider_key not in cls._REGISTRY:
			raise ValueError(
				f"Unknown LLM provider: {provider!r}. "
				f"Supported: {sorted(cls._REGISTRY)}"
			)
		return cls._REGISTRY[provider_key]()
