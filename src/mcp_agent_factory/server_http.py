"""
FastAPI HTTP MCP server — JSON-RPC 2.0 over HTTP POST.

Exposes the same MCP protocol as server.py (STDIO) but over TCP/IP via FastAPI.
The STDIO server is intentionally not modified — this is an additive transport.

Endpoints:
  POST /mcp    — JSON-RPC 2.0 MCP endpoint
  GET  /health — liveness probe

Observability: every request/response logged as a JSON line to stderr,
matching the pattern established by the STDIO server.

Usage::

	uvicorn mcp_agent_factory.server_http:app --reload
"""
from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from mcp_agent_factory.config.privacy import PrivacyConfig
from mcp_agent_factory.models import AddInput, EchoInput

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger("mcp_http_server")


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 transport models
# ---------------------------------------------------------------------------

class MCPRequest(BaseModel):
	jsonrpc: str = "2.0"
	method: str
	params: dict[str, Any] | None = None
	id: int | str | None = None


class MCPResponse(BaseModel):
	jsonrpc: str = "2.0"
	id: int | str | None = None
	result: Any | None = None
	error: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Tool registry (mirroring STDIO server)
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


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _call_tool(name: str, arguments: dict) -> dict:
	if name == "echo":
		validated = EchoInput.model_validate(arguments)
		return {"type": "text", "text": validated.message}
	if name == "add":
		validated = AddInput.model_validate(arguments)
		result = validated.a + validated.b
		text = str(int(result)) if result == int(result) else str(result)
		return {"type": "text", "text": text}
	raise ValueError(f"Unknown tool: {name!r}")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> MCPResponse:
	return MCPResponse(id=req_id, result=result)


def _error(req_id: Any, code: int, message: str) -> MCPResponse:
	return MCPResponse(id=req_id, error={"code": code, "message": message})


def _dispatch(request: MCPRequest) -> MCPResponse | None:
	method = request.method
	params = request.params or {}
	req_id = request.id

	if method == "initialize":
		return _ok(req_id, {
			"protocolVersion": "2024-11-05",
			"capabilities": {"tools": {}},
			"serverInfo": {"name": "mcp-http-server", "version": "0.1.0"},
		})

	if method == "initialized":
		return None  # notification — no response

	if method == "ping":
		return _ok(req_id, {})

	if method == "tools/list":
		return _ok(req_id, {"tools": TOOLS})

	if method == "tools/call":
		tool_name = params.get("name", "")
		arguments = params.get("arguments") or {}
		try:
			content = _call_tool(tool_name, arguments)
			return _ok(req_id, {"content": [content], "isError": False})
		except (ValueError, ValidationError) as exc:
			return _ok(req_id, {
				"content": [{"type": "text", "text": str(exc)}],
				"isError": True,
			})

	if req_id is not None:
		return _error(req_id, -32601, f"Method not found: {method!r}")
	return None


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
	# Enforce privacy-first: assert egress is disabled at startup
	cfg = PrivacyConfig()
	cfg.assert_no_egress()
	logger.debug(json.dumps({"event": "startup", "privacy": "egress_disabled"}))
	yield
	logger.debug(json.dumps({"event": "shutdown"}))


app = FastAPI(
	title="MCP HTTP Server",
	description="Model Context Protocol server over HTTP (JSON-RPC 2.0)",
	version="0.1.0",
	lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
	return {"status": "ok"}


@app.post("/mcp", response_model=MCPResponse)
async def mcp_endpoint(request: MCPRequest) -> MCPResponse:
	logger.debug(json.dumps({"direction": "recv", "payload": request.model_dump()}))

	response = _dispatch(request)

	if response is None:
		# Notification — return empty 200 (no JSON-RPC response body needed)
		response = MCPResponse(id=request.id, result={})

	logger.debug(json.dumps({"direction": "send", "payload": response.model_dump()}))
	return response
