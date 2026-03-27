"""
MCP API Gateway — FastAPI application.

Integrates:
  - MessageBus + SSE router (S03)
  - MultiAgentOrchestrator (S01)
  - Auction (S02)
  - OAuth token verification (M002 / auth)
  - Sampling handler (this slice)

Endpoints
---------
POST /mcp            — MCP JSON-RPC 2.0, requires Bearer token w/ scope tools:call
POST /sampling       — Sampling/createMessage stub (unauthenticated)
GET  /health         — Liveness probe (unauthenticated)
/sse/*               — SSE event stream (mounted sub-app)
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import fakeredis.aioredis as aioredis
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from mcp_agent_factory.agents.models import AgentTask, MCPContext
from mcp_agent_factory.agents.pipeline_orchestrator import MultiAgentOrchestrator
from mcp_agent_factory.auth.resource import make_verify_token
from mcp_agent_factory.economics.auction import Auction
from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus
from mcp_agent_factory.messaging.sse_router import create_sse_router
from mcp_agent_factory.server_http import MCPRequest, MCPResponse, TOOLS, lifespan
from mcp_agent_factory.session.manager import RedisSessionManager

from .sampling import SamplingHandler, SamplingResult, StubSamplingClient

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger("mcp_gateway")

# ---------------------------------------------------------------------------
# Module-level singletons (replaced in tests via set_* helpers)
# ---------------------------------------------------------------------------

bus: MessageBus = MessageBus()
sampling_handler: SamplingHandler = SamplingHandler(StubSamplingClient())
_redis_client = aioredis.FakeRedis()
session: RedisSessionManager = RedisSessionManager(_redis_client)

# ---------------------------------------------------------------------------
# Test-injection helpers
# ---------------------------------------------------------------------------


def set_sampling_client(client: Any) -> None:
    """Inject a custom SamplingClient for tests."""
    sampling_handler.set_client(client)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

gateway_app = FastAPI(lifespan=lifespan, title="MCP API Gateway")

# Mount SSE router
sse_router = create_sse_router(bus)
gateway_app.mount("/sse", sse_router)


# ---------------------------------------------------------------------------
# Request/response helpers
# ---------------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> MCPResponse:
    return MCPResponse(id=req_id, result=result)


def _err(req_id: Any, code: int, message: str) -> MCPResponse:
    return MCPResponse(id=req_id, error={"code": code, "message": message})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@gateway_app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mcp-gateway"}


class SamplingBody(BaseModel):
    prompt: str


@gateway_app.post("/sampling", response_model=SamplingResult)
async def sampling_endpoint(body: SamplingBody) -> SamplingResult:
    return await sampling_handler.handle(body.prompt)


@gateway_app.post("/mcp", response_model=MCPResponse)
async def mcp_endpoint(
    req: MCPRequest,
    _claims: dict = Depends(make_verify_token("tools:call")),
) -> MCPResponse:
    method = req.method
    params = req.params or {}
    req_id = req.id

    # tools/list
    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})

    # tools/call
    if method == "tools/call":
        tool_name: str = params.get("name", "")
        args: dict = params.get("arguments", {})

        # Publish observability event for every tools/call
        bus.publish("gateway.tool_calls", AgentMessage(
            topic="gateway.tool_calls",
            sender="gateway",
            recipient="*",
            content={"tool": tool_name, "args": args},
        ))

        if tool_name == "echo":
            text = args.get("text", "")
            return _ok(req_id, {"content": [{"type": "text", "text": text}]})

        if tool_name == "analyse_and_report":
            task = AgentTask(
                task_id=str(req_id or "gw"),
                description=args.get("description", ""),
                context=args.get("context", {}),
            )
            ctx = MCPContext(session_id=str(req_id or "gw"))
            orchestrator = MultiAgentOrchestrator(session)
            report = await orchestrator.run_pipeline(task, ctx)
            return _ok(req_id, {"content": [{"type": "text", "text": report.summary}]})

        if tool_name == "sampling_demo":
            prompt = args.get("prompt", "")
            result = await sampling_handler.handle(prompt)
            return _ok(req_id, {"content": [{"type": "text", "text": result.completion}]})

        # Unknown tool
        return _ok(req_id, {
            "isError": True,
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
        })

    return _err(req_id, -32601, f"Method not found: {method}")
