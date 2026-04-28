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
GET  /mcp            — MCP Streamable HTTP SSE channel (server→client)
POST /mcp            — MCP JSON-RPC 2.0, requires Bearer token w/ scope tools:call
POST /sampling       — Sampling/createMessage stub (unauthenticated)
GET  /health         — Liveness probe (unauthenticated)
/sse/*               — SSE event stream (mounted sub-app)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
load_dotenv()
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse as _JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from mcp_agent_factory.agents.models import AgentTask, MCPContext
from mcp_agent_factory.agents.pipeline_orchestrator import MultiAgentOrchestrator
from authlib.jose import OctKey
from mcp_agent_factory.auth.resource import make_verify_token, set_jwt_key
from mcp_agent_factory.config.privacy import PrivacyConfig
from mcp_agent_factory.economics.auction import Auction
from mcp_agent_factory.knowledge import InMemoryVectorStore, LocalEmbedder, StubEmbedder, query_knowledge_base
from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus
from mcp_agent_factory.messaging.sse_router import create_sse_router
from mcp_agent_factory.messaging.sse_v1_router import create_sse_v1_router
from mcp_agent_factory.server_http import MCPRequest, MCPResponse, TOOLS
from mcp_agent_factory.session.manager import RedisSessionManager

from .router import AnthropicHandler, OllamaHandler, UnifiedRouter
from .sampling import SamplingHandler, SamplingResult, StubSamplingClient
from .service_layer import InternalServiceLayer

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger("mcp_gateway")

# ---------------------------------------------------------------------------
# Dev mode — set MCP_DEV_MODE=1 to bypass JWT auth for local testing.
# Never use in production.
# ---------------------------------------------------------------------------
DEV_MODE: bool = os.getenv("MCP_DEV_MODE", "0") == "1"


# ---------------------------------------------------------------------------
# Redis factory — real client when REDIS_URL is set, FakeRedis otherwise
# ---------------------------------------------------------------------------

def _make_redis_client():
	url = os.getenv("REDIS_URL")
	if url:
		import redis.asyncio as _real_redis
		return _real_redis.from_url(url, decode_responses=False)
	import fakeredis.aioredis as _fakeredis
	return _fakeredis.FakeRedis()


# ---------------------------------------------------------------------------
# EventLog factory — Kafka when KAFKA_BOOTSTRAP_SERVERS is set, InProcess otherwise
# ---------------------------------------------------------------------------

def _make_event_log():
	bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
	if bootstrap:
		from mcp_agent_factory.streams.kafka_adapter import KafkaEventLog
		return KafkaEventLog(bootstrap_servers=bootstrap)
	from mcp_agent_factory.streams.eventlog import InProcessEventLog
	return InProcessEventLog()


# ---------------------------------------------------------------------------
# Gateway lifespan — privacy check + Redis liveness gate
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _gateway_lifespan(app: FastAPI):
	PrivacyConfig().assert_no_egress()
	secret = os.getenv("JWT_SECRET")
	if secret:
		set_jwt_key(OctKey.import_key(secret.encode()))
	if os.getenv("REDIS_URL"):
		try:
			await _redis_client.ping()
		except Exception as exc:
			raise RuntimeError(
				f"Redis unreachable at {os.getenv('REDIS_URL')!r}: {exc}"
			) from exc
	# Start Kafka producer if configured
	if os.getenv("KAFKA_BOOTSTRAP_SERVERS") and hasattr(_event_log, "start"):
		await _event_log.start()
	logger.debug(json.dumps({"event": "startup", "privacy": "egress_disabled"}))
	yield
	if os.getenv("KAFKA_BOOTSTRAP_SERVERS") and hasattr(_event_log, "stop"):
		await _event_log.stop()
	logger.debug(json.dumps({"event": "shutdown"}))


# ---------------------------------------------------------------------------
# Module-level singletons (replaced in tests via set_* helpers)
# ---------------------------------------------------------------------------

bus: MessageBus = MessageBus()
sampling_handler: SamplingHandler = SamplingHandler(StubSamplingClient())
_redis_client = _make_redis_client()
session: RedisSessionManager = RedisSessionManager(_redis_client)
_vector_store: InMemoryVectorStore = InMemoryVectorStore()
_embedder: LocalEmbedder = LocalEmbedder()
_event_log = _make_event_log()

_unified_router: UnifiedRouter = UnifiedRouter(
    handlers=[AnthropicHandler(), OllamaHandler()],
    event_log=_event_log,
)

_service_layer: InternalServiceLayer = InternalServiceLayer(
	bus, session, sampling_handler, _vector_store, _embedder, _event_log,
	router=_unified_router,
)

# ---------------------------------------------------------------------------
# Test-injection helpers
# ---------------------------------------------------------------------------


def set_sampling_client(client: Any) -> None:
	"""Inject a custom SamplingClient for tests."""
	sampling_handler.set_client(client)


def set_vector_store(store: Any) -> None:
	"""Inject a custom VectorStore for tests."""
	global _vector_store
	_vector_store = store
	_service_layer._vector_store = store


def set_embedder(embedder: Any) -> None:
	"""Inject a custom Embedder for tests."""
	global _embedder
	_embedder = embedder
	_service_layer._embedder = embedder


def set_pruner(pruner: Any) -> None:
	"""Inject a custom ContextPruner for tests (e.g. threshold=0.0 with StubEmbedder)."""
	_service_layer._pruner = pruner


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

_AUTH_SERVER_URL = os.getenv("AUTH_SERVER_URL", "http://localhost:8001")
_DISCOVERY_PATH = "/.well-known/oauth-authorization-server"
_WWW_AUTH_VALUE = (
    f'Bearer realm="mcp-server",'
    f' resource_metadata="http://localhost:8000{_DISCOVERY_PATH}"'
)

gateway_app = FastAPI(lifespan=_gateway_lifespan, title="MCP API Gateway")


@gateway_app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    headers = {}
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = _WWW_AUTH_VALUE
    return _JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@gateway_app.get(_DISCOVERY_PATH)
async def oauth_discovery_proxy() -> _JSONResponse:
    """Proxy RFC 8414 discovery from the auth server so clients need only one base URL."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{_AUTH_SERVER_URL}{_DISCOVERY_PATH}")
            resp.raise_for_status()
            return _JSONResponse(content=resp.json())
    except Exception:
        return _JSONResponse(content={
            "issuer": _AUTH_SERVER_URL,
            "authorization_endpoint": f"{_AUTH_SERVER_URL}/authorize",
            "token_endpoint": f"{_AUTH_SERVER_URL}/token",
            "registration_endpoint": f"{_AUTH_SERVER_URL}/register",
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
        })


# Mount SSE router (legacy /sse/events)
sse_router = create_sse_router(bus)
gateway_app.mount("/sse/legacy", sse_router)

# Mount SSE v1 router (/sse/v1/events, /sse/v1/messages)
sse_v1_router = create_sse_v1_router(bus)
gateway_app.include_router(sse_v1_router, prefix="/sse/v1")


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


@gateway_app.get("/mcp")
async def mcp_sse_endpoint(
	_claims: dict | None = Depends(make_verify_token("tools:call", optional=True)),
) -> Any:
	"""MCP Streamable HTTP — GET /mcp opens the server→client SSE channel."""
	async def _events():
		yield {"event": "endpoint", "data": json.dumps({"path": "/mcp"})}
		while True:
			await asyncio.sleep(15)
			yield {"event": "ping", "data": ""}

	return EventSourceResponse(_events())


@gateway_app.post("/mcp")
@gateway_app.post("/sse/v1")
async def mcp_endpoint(
	req: MCPRequest,
	_claims: dict | None = Depends(make_verify_token("tools:call", optional=True)),
) -> Any:
	from fastapi.responses import JSONResponse
	resp = await _mcp_dispatch(req, _claims)
	# Emit only non-None fields so strict MCP clients don't reject null result/error
	return JSONResponse(content=resp.model_dump(exclude_none=True))


async def _mcp_dispatch(req: MCPRequest, _claims: dict | None) -> MCPResponse:
	method = req.method
	params = req.params or {}
	req_id = req.id

	# Discovery methods — no auth required
	if method == "initialize":
		return _ok(req_id, {
			"protocolVersion": "2024-11-05",
			"capabilities": {"tools": {}},
			"serverInfo": {"name": "mcp-agent-factory", "version": "1.0.0"},
		})

	if method == "notifications/initialized":
		return _ok(req_id, {})

	# tools/list — public (read-only discovery)
	if method == "tools/list":
		return _ok(req_id, {"tools": TOOLS})

	# tools/call — requires valid Bearer token (bypassed in DEV_MODE)
	if method == "tools/call":
		if _claims is None and not DEV_MODE:
			return _err(req_id, -32001, "Authentication required for tools/call")
		tool_name: str = params.get("name", "")
		args: dict = params.get("arguments", {})

		# Publish observability event for every tools/call
		bus.publish("gateway.tool_calls", AgentMessage(
			topic="gateway.tool_calls",
			sender="gateway",
			recipient="*",
			content={"tool": tool_name, "args": args},
		))

		try:
			result = await _service_layer.handle(tool_name, args, _claims)
			return _ok(req_id, result)
		except (ValidationError, ValueError) as e:
			return _ok(req_id, {"isError": True, "content": [{"type": "text", "text": str(e)}]})
		except Exception as e:
			return _err(req_id, -32603, str(e))

	return _err(req_id, -32601, f"Method not found: {method}")
