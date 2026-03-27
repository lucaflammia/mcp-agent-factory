"""
Tests for the FastAPI HTTP MCP server.

Uses FastAPI's TestClient (sync httpx under the hood) — no live uvicorn needed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mcp_agent_factory.server_http import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
	def test_health(self):
		resp = client.get("/health")
		assert resp.status_code == 200
		assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# MCP lifecycle
# ---------------------------------------------------------------------------

class TestInitialize:
	def test_initialize(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 1,
			"method": "initialize",
			"params": {
				"protocolVersion": "2024-11-05",
				"capabilities": {},
				"clientInfo": {"name": "test-client", "version": "0.1.0"},
			},
		})
		assert resp.status_code == 200
		body = resp.json()
		assert body["result"]["protocolVersion"] == "2024-11-05"
		assert "tools" in body["result"]["capabilities"]
		assert body["result"]["serverInfo"]["name"] == "mcp-http-server"

	def test_initialized_notification(self):
		# Notifications have no id — server returns empty result
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"method": "initialized",
		})
		assert resp.status_code == 200


class TestToolsList:
	def test_tools_list_returns_echo_and_add(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 2,
			"method": "tools/list",
			"params": {},
		})
		assert resp.status_code == 200
		tools = resp.json()["result"]["tools"]
		names = [t["name"] for t in tools]
		assert "echo" in names
		assert "add" in names

	def test_tools_list_has_input_schema(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 3,
			"method": "tools/list",
			"params": {},
		})
		tools = resp.json()["result"]["tools"]
		for tool in tools:
			assert "inputSchema" in tool


class TestCallTool:
	def test_call_echo(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 4,
			"method": "tools/call",
			"params": {"name": "echo", "arguments": {"message": "hello http"}},
		})
		assert resp.status_code == 200
		result = resp.json()["result"]
		assert result["isError"] is False
		assert result["content"][0]["text"] == "hello http"

	def test_call_add(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 5,
			"method": "tools/call",
			"params": {"name": "add", "arguments": {"a": 3, "b": 4}},
		})
		assert resp.status_code == 200
		result = resp.json()["result"]
		assert result["isError"] is False
		assert result["content"][0]["text"] == "7"

	def test_call_unknown_tool_returns_is_error(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 6,
			"method": "tools/call",
			"params": {"name": "nonexistent", "arguments": {}},
		})
		assert resp.status_code == 200
		assert resp.json()["result"]["isError"] is True

	def test_echo_missing_message_returns_is_error(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 7,
			"method": "tools/call",
			"params": {"name": "echo", "arguments": {}},
		})
		assert resp.status_code == 200
		assert resp.json()["result"]["isError"] is True

	def test_add_wrong_type_returns_is_error(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 8,
			"method": "tools/call",
			"params": {"name": "add", "arguments": {"a": "not-a-number", "b": 1}},
		})
		assert resp.status_code == 200
		assert resp.json()["result"]["isError"] is True

	def test_unknown_method_returns_error_object(self):
		resp = client.post("/mcp", json={
			"jsonrpc": "2.0",
			"id": 9,
			"method": "no/such/method",
			"params": {},
		})
		assert resp.status_code == 200
		body = resp.json()
		assert "error" in body
		assert body["error"]["code"] == -32601
