"""
Simulation MCP server — JSON-RPC 2.0 over STDIO.

Handles:
  - initialize / initialized  (MCP lifecycle)
  - tools/list                (capability advertisement)
  - tools/call                (tool execution)

Observability: every request received and every response sent is logged as a
single JSON line to stderr, enabling post-mortem replay of any failing exchange.

Usage:
	python -m mcp_agent_factory.server
	mcp-sim-server              # if installed via pip
"""
from __future__ import annotations

import json
import sys
import logging
from typing import Any

from pydantic import ValidationError
from mcp_agent_factory.models import EchoInput, AddInput

# ---------------------------------------------------------------------------
# Logging — one JSON line per event to stderr so tests can grep/replay
# ---------------------------------------------------------------------------
logging.basicConfig(
	stream=sys.stderr,
	level=logging.DEBUG,
	format="%(message)s",
)
logger = logging.getLogger("mcp_sim_server")


def _log(direction: str, payload: Any) -> None:
	"""Emit one JSON log line to stderr."""
	logger.debug(json.dumps({"direction": direction, "payload": payload}))


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
TOOLS: list[dict] = [
	{
		"name": "echo",
		"description": "Returns the input message unchanged. Useful for testing connectivity.",
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


def _call_tool(name: str, arguments: dict) -> dict:
	"""Execute a tool and return an MCP content block."""
	if name == "echo":
		validated = EchoInput.model_validate(arguments)
		return {"type": "text", "text": validated.message}
	if name == "add":
		validated = AddInput.model_validate(arguments)
		result = validated.a + validated.b
		# Return integer string when result is whole number
		text = str(int(result)) if result == int(result) else str(result)
		return {"type": "text", "text": text}
	raise ValueError(f"Unknown tool: {name!r}")


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> dict:
	return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict:
	return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _notification(method: str, params: Any = None) -> dict:
	msg: dict = {"jsonrpc": "2.0", "method": method}
	if params is not None:
		msg["params"] = params
	return msg


# ---------------------------------------------------------------------------
# Request dispatcher
# ---------------------------------------------------------------------------

def _dispatch(request: dict) -> dict | None:
	"""
	Process one JSON-RPC request/notification.
	Returns a response dict, or None for notifications that need no reply.
	"""
	method = request.get("method", "")
	params = request.get("params") or {}
	req_id = request.get("id")  # None for notifications

	# --- MCP lifecycle ---
	if method == "initialize":
		result = {
			"protocolVersion": "2024-11-05",
			"capabilities": {"tools": {}},
			"serverInfo": {"name": "mcp-sim-server", "version": "0.1.0"},
		}
		return _ok(req_id, result)

	if method == "initialized":
		# Notification — no response
		return None

	if method == "ping":
		return _ok(req_id, {})

	# --- Tool operations ---
	if method == "tools/list":
		return _ok(req_id, {"tools": TOOLS})

	if method == "tools/call":
		tool_name = params.get("name", "")
		arguments = params.get("arguments") or {}
		try:
			content = _call_tool(tool_name, arguments)
			return _ok(req_id, {"content": [content], "isError": False})
		except (ValueError, ValidationError) as exc:
			return _ok(
				req_id,
				{"content": [{"type": "text", "text": str(exc)}], "isError": True},
			)

	# --- Unknown method ---
	if req_id is not None:
		return _error(req_id, -32601, f"Method not found: {method!r}")
	return None  # unknown notification — silently ignore


# ---------------------------------------------------------------------------
# STDIO transport
# ---------------------------------------------------------------------------

def _read_message(stream) -> dict | None:
	"""Read one newline-delimited JSON message from *stream*. Returns None on EOF."""
	line = stream.readline()
	if not line:
		return None
	return json.loads(line)


def _write_message(msg: dict, stream) -> None:
	"""Write one newline-delimited JSON message to *stream* and flush."""
	stream.write(json.dumps(msg) + "\n")
	stream.flush()


def serve(stdin=None, stdout=None) -> None:
	"""
	Run the server loop, reading from *stdin* and writing to *stdout*.
	Defaults to sys.stdin / sys.stdout.
	"""
	if stdin is None:
		stdin = sys.stdin
	if stdout is None:
		stdout = sys.stdout

	logger.info(json.dumps({"event": "server_start", "tools": [t["name"] for t in TOOLS]}))

	while True:
		try:
			request = _read_message(stdin)
		except json.JSONDecodeError as exc:
			_write_message(_error(None, -32700, f"Parse error: {exc}"), stdout)
			continue

		if request is None:
			logger.info(json.dumps({"event": "stdin_eof"}))
			break

		_log("recv", request)

		response = _dispatch(request)

		if response is not None:
			_log("send", response)
			_write_message(response, stdout)


def main() -> None:
	"""Entry point — run the STDIO server."""
	serve()


if __name__ == "__main__":
	main()
