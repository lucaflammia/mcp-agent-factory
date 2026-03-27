"""
FastAPI HTTP MCP server — auth-protected variant.

Identical to server_http.py but POST /mcp requires a valid Bearer token
with scope 'tools:call', validated by the Resource Server middleware.

GET /health is unauthenticated (liveness probe must not require auth).
"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from mcp_agent_factory.auth.resource import make_verify_token
from mcp_agent_factory.server_http import (
	MCPRequest,
	MCPResponse,
	_dispatch,
	lifespan,
)
import json
import logging
import sys

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger("mcp_http_server_secured")

secured_app = FastAPI(
	title="MCP HTTP Server (Secured)",
	description="OAuth 2.1 protected MCP server",
	version="0.1.0",
	lifespan=lifespan,
)


@secured_app.get("/health")
async def health() -> dict:
	return {"status": "ok"}


@secured_app.post("/mcp", response_model=MCPResponse)
async def mcp_endpoint(
	request: MCPRequest,
	claims: dict = Depends(make_verify_token("tools:call")),
) -> MCPResponse:
	logger.debug(json.dumps({"direction": "recv", "payload": request.model_dump(), "sub": claims.get("sub")}))
	response = _dispatch(request)
	if response is None:
		response = MCPResponse(id=request.id, result={})
	logger.debug(json.dumps({"direction": "send", "payload": response.model_dump()}))
	return response
