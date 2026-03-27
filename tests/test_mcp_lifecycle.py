"""
Full MCP lifecycle tests — orchestrator ↔ simulation server over STDIO.

Tests prove R001 (orchestration routing) and R002 (JSON-RPC 2.0 communication).
"""
from __future__ import annotations

import pytest
from mcp_agent_factory.orchestrator import MCPOrchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orc() -> MCPOrchestrator:
	"""Yield a connected orchestrator; close after each test."""
	with MCPOrchestrator() as o:
		yield o


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInitialize:
	"""Capability negotiation (initialize handshake)."""

	def test_initialize_returns_protocol_version(self, orc: MCPOrchestrator):
		# connect() already performed initialize; re-verify the class state
		# by doing a fresh connection inside this test to capture the result.
		with MCPOrchestrator() as fresh:
			result = fresh.connect()
			# connect() was called again — but the fixture already called it,
			# so use a fresh instance here (fixture orc is available but
			# connect() already ran; we verify via list_tools round-trip below).
		assert result.get("protocolVersion") == "2024-11-05"

	def test_initialize_server_info(self, orc: MCPOrchestrator):
		"""Smoke-test: orc is live after handshake (list_tools doesn't raise)."""
		tools = orc.list_tools()
		assert isinstance(tools, list)

	def test_initialize_capabilities_present(self):
		"""The initialize response contains a capabilities key with tools."""
		with MCPOrchestrator() as o:
			result = o.connect()
			assert "capabilities" in result
			assert "tools" in result["capabilities"]


class TestListTools:
	"""Tool discovery via tools/list."""

	def test_list_tools_returns_list(self, orc: MCPOrchestrator):
		tools = orc.list_tools()
		assert isinstance(tools, list)
		assert len(tools) > 0

	def test_list_tools_contains_echo(self, orc: MCPOrchestrator):
		names = [t["name"] for t in orc.list_tools()]
		assert "echo" in names

	def test_list_tools_contains_add(self, orc: MCPOrchestrator):
		names = [t["name"] for t in orc.list_tools()]
		assert "add" in names

	def test_list_tools_schema_shape(self, orc: MCPOrchestrator):
		for tool in orc.list_tools():
			assert "name" in tool
			assert "description" in tool
			assert "inputSchema" in tool


class TestCallTool:
	"""Tool invocation via tools/call."""

	def test_call_echo(self, orc: MCPOrchestrator):
		result = orc.call_tool("echo", {"message": "hello"})
		assert result["isError"] is False
		content = result["content"]
		assert len(content) == 1
		assert content[0]["text"] == "hello"

	def test_call_add(self, orc: MCPOrchestrator):
		result = orc.call_tool("add", {"a": 3, "b": 4})
		assert result["isError"] is False
		assert result["content"][0]["text"] == "7"

	def test_call_unknown_tool_returns_is_error(self, orc: MCPOrchestrator):
		result = orc.call_tool("does_not_exist", {})
		assert result["isError"] is True

	def test_call_echo_empty_message(self, orc: MCPOrchestrator):
		result = orc.call_tool("echo", {"message": ""})
		assert result["isError"] is False
		assert result["content"][0]["text"] == ""

	def test_call_add_negative_numbers(self, orc: MCPOrchestrator):
		result = orc.call_tool("add", {"a": -5, "b": 3})
		assert result["isError"] is False
		assert result["content"][0]["text"] == "-2"
