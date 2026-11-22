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
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()
from contextlib import asynccontextmanager
from typing import Any

import httpx
from authlib.jose import OctKey
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse as _JSONResponse
from pydantic import BaseModel, ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mcp_agent_factory.agents.models import AgentTask, MCPContext
from mcp_agent_factory.agents.pipeline_orchestrator import MultiAgentOrchestrator
from mcp_agent_factory.auth.resource import make_verify_token, set_jwt_key
from mcp_agent_factory.config.privacy import PrivacyConfig
from mcp_agent_factory.economics.auction import Auction
from mcp_agent_factory.knowledge import (
    InMemoryVectorStore,
    LocalEmbedder,
    PgVectorStore,
    StubEmbedder,
    query_knowledge_base,
)
from mcp_agent_factory.knowledge.generation import GenerationHandler
from mcp_agent_factory.knowledge.query_handler import DefaultFilterResolver, GuardedQueryHandler
from mcp_agent_factory.kv.store import RedisKVStore
from mcp_agent_factory.messaging.bus import AgentMessage, MessageBus
from mcp_agent_factory.messaging.sse_router import create_sse_router
from mcp_agent_factory.messaging.sse_v1_router import create_sse_v1_router
from mcp_agent_factory.server_http import TOOLS, MCPRequest, MCPResponse
from mcp_agent_factory.session.manager import RedisSessionManager

from .fleet import fleet_router, set_fleet_redis, start_fleet_workers, stop_fleet_workers
from .query_management import (
    QueryManager,
    RateLimitConfig,
    TenantConfig,
    calculate_query_cost,
    is_valid_timezone,
)
from .router import AnthropicHandler, OllamaHandler, UnifiedRouter
from .sampling import SamplingHandler, SamplingResult, StubSamplingClient
from .service_layer import InternalServiceLayer
from .telemetry import configure_telemetry, get_tracer

# ---------------------------------------------------------------------------
# Tool scoping — INT-01-C
# Maps tool name → minimum scope required to see/call it via tools/list or tools/call.
# Tools absent from this map are visible to any authenticated caller (tools:call).
# Unauthenticated callers (DEV_MODE or optional auth returning None) only see
# tools whose required scope is "tools:read" or that have no entry here.
# ---------------------------------------------------------------------------
_PUBLIC_TOOLS: frozenset[str] = frozenset({"echo", "add"})

_TOOL_REQUIRED_SCOPE: dict[str, str] = {
    "echo": "tools:read",
    "add": "tools:read",
    "query_knowledge_base": "tools:call",
    "sampling_demo": "tools:call",
    "kv/add_phrase": "tools:call",
    "kv/check_affinity": "tools:call",
    "analyse_and_report": "tools:call",
    "orchestrate": "tools:orchestrate",  # requires explicit higher scope
}

# ---------------------------------------------------------------------------
# Destructive tools — INT-01-D
# Direct tools/call is blocked for tools in this set; callers must route through
# the graph orchestrator (POST /mcp with method=orchestrate or the async fleet
# endpoints) so the human-in-the-loop approval path is exercised.
# ---------------------------------------------------------------------------
_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({"orchestrate"})

# ---------------------------------------------------------------------------
# Provider key validation for agents/* dispatch
# ---------------------------------------------------------------------------

_PROVIDER_KEY_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


class ProviderNotConfiguredError(Exception):
    """Raised when a provider is explicitly requested but its API key is absent."""

    def __init__(self, provider: str, env_var: str) -> None:
        self.provider = provider
        self.env_var = env_var
        super().__init__(f"{env_var} not set for provider '{provider}'")

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
	_startup_jobs_disabled = os.getenv("ASYNC_JOBS_ENABLED", "true").lower() in ("false", "0", "no")
	if os.getenv("REDIS_URL") and not _startup_jobs_disabled:
		try:
			await _redis_client.ping()
		except Exception as exc:
			raise RuntimeError(
				f"Redis unreachable at {os.getenv('REDIS_URL')!r}: {exc}"
			) from exc
	# Start Kafka producer if configured
	if os.getenv("KAFKA_BOOTSTRAP_SERVERS") and hasattr(_event_log, "start"):
		await _event_log.start()
	# Wire fleet worker. Async jobs are enabled when both a real Redis URL is
	# configured AND ASYNC_JOBS_ENABLED is not explicitly set to "false".
	# In the cloud demo (ECS without Redis), ASYNC_JOBS_ENABLED=false disables
	# the endpoints immediately so callers get a 503 instead of a timeout.
	_async_jobs_env = os.getenv("ASYNC_JOBS_ENABLED", "true").lower()
	_jobs_explicitly_disabled = _async_jobs_env in ("false", "0", "no")
	_has_redis = bool(os.getenv("REDIS_URL")) and not _jobs_explicitly_disabled
	_jobs_enabled = _has_redis
	set_fleet_redis(_redis_client, enabled=_jobs_enabled)
	if _has_redis:
		await start_fleet_workers()
	# Populate chunk-count gauge — runs inside lifespan so DB is confirmed ready.
	try:
		from mcp_agent_factory.knowledge.query_handler import _chunk_count as _cg
		if hasattr(_vector_store, "status"):
			_cg.set(_vector_store.status().get("chunk_count", 0))
		elif hasattr(_vector_store, "_store"):
			_cg.set(len(_vector_store._store))
	except Exception as _exc:
		logger.warning('{"event":"chunk_gauge_init_failed","detail":"%s"}', _exc)
	# Start async audit writer (RAG-09 S1) — create asyncpg pool if configured
	_audit_db_url = os.getenv("AUDIT_DB_URL")
	if _audit_db_url:
		try:
			import asyncpg  # type: ignore[import]
			_pg_pool = await asyncpg.create_pool(_audit_db_url)
			_query_manager.set_pg_pool(_pg_pool)
			logger.debug(json.dumps({"event": "audit_pg_pool_created"}))
		except Exception as _pg_exc:
			logger.warning(json.dumps({"event": "audit_pg_pool_failed", "detail": str(_pg_exc)}))
	_query_manager.start()
	logger.debug(json.dumps({"event": "startup", "privacy": "egress_disabled"}))
	yield
	if _has_redis:
		await stop_fleet_workers()
	if os.getenv("KAFKA_BOOTSTRAP_SERVERS") and hasattr(_event_log, "stop"):
		await _event_log.stop()
	# Flush remaining audit entries (RAG-09 S1)
	await _query_manager.stop()
	if _audit_db_url and _query_manager._pg_writer._pool is not None:
		await _query_manager._pg_writer._pool.close()
	logger.debug(json.dumps({"event": "shutdown"}))


# ---------------------------------------------------------------------------
# Module-level singletons (replaced in tests via set_* helpers)
# ---------------------------------------------------------------------------

bus: MessageBus = MessageBus()
sampling_handler: SamplingHandler = SamplingHandler(StubSamplingClient())
_redis_client = _make_redis_client()
session: RedisSessionManager = RedisSessionManager(_redis_client)
def _make_vector_store():
	dsn = os.getenv("DATABASE_URL")
	if dsn:
		try:
			return PgVectorStore(dsn)
		except Exception as exc:
			logger.warning('{"event":"pg_vector_store_init_failed","detail":"%s","fallback":"InMemoryVectorStore"}', exc)
	return InMemoryVectorStore()

_vector_store = _make_vector_store()
_embedder: LocalEmbedder = LocalEmbedder()
_event_log = _make_event_log()

# KV topics: comma-separated KV_TOPICS env var, defaults to "default", always includes "audit"
_kv_topics: list[str] = [
    t.strip() for t in os.getenv("KV_TOPICS", "default").split(",") if t.strip()
]
if "audit" not in _kv_topics:
    _kv_topics.append("audit")
_kv_store: RedisKVStore = RedisKVStore(_redis_client, topics=_kv_topics)

_unified_router: UnifiedRouter = UnifiedRouter(
    handlers=[AnthropicHandler(), OllamaHandler()],
    event_log=_event_log,
)

_query_manager: QueryManager = QueryManager(
    kv_store=_kv_store,
    redis_client=_redis_client,
    config=RateLimitConfig(
        tokens_per_second=float(os.getenv("RATE_LIMIT_QPS", "10.0")),
        burst_size=int(os.getenv("RATE_LIMIT_BURST", "20")),
        daily_quota=int(os.getenv("QUOTA_DAILY", "100000")),
        hourly_quota=int(os.getenv("QUOTA_HOURLY", "10000")),
        cost_top_k_per_unit=float(os.getenv("COST_TOP_K_PER_UNIT", "0.1")),
        cost_latency_ms_per_100=float(os.getenv("COST_LATENCY_MS_PER_100", "0.1")),
        cost_refusal_penalty=float(os.getenv("COST_REFUSAL_PENALTY", "0.5")),
        cost_retry_penalty=float(os.getenv("COST_RETRY_PENALTY", "0.25")),
    ),
    audit_flush_interval=float(os.getenv("AUDIT_FLUSH_INTERVAL", "10.0")),
    audit_max_buffer=int(os.getenv("AUDIT_MAX_BUFFER", "1000")),
)

_service_layer: InternalServiceLayer = InternalServiceLayer(
	bus, session, sampling_handler, _vector_store, _embedder, _event_log,
	router=_unified_router,
	kv_store=_kv_store,
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


def set_kv_store(store: Any) -> None:
	"""Inject a custom RedisKVStore for tests."""
	global _kv_store
	_kv_store = store
	_service_layer._kv_store = store


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

# OTel — configure tracer provider and instrument FastAPI at module level so
# SERVER spans are generated for every inbound request (Jaeger Monitor requires them).
configure_telemetry()
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(gateway_app)
except ImportError:
    pass

# Prometheus — must be wired before app starts (adds middleware)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(gateway_app).expose(gateway_app, endpoint="/metrics")
except ImportError:
    pass


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

# Async fleet runtime (/mcp/jobs, /mcp/jobs/batch)
gateway_app.include_router(fleet_router)


# ---------------------------------------------------------------------------
# Request/response helpers
# ---------------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> MCPResponse:
	return MCPResponse(id=req_id, result=result)


def _err(req_id: Any, code: int, message: str) -> MCPResponse:
	return MCPResponse(id=req_id, error={"code": code, "message": message})


def _tool_visible(tool_name: str, granted_scopes: set[str]) -> bool:
	"""Return True if the tool should appear in tools/list for the given granted scopes."""
	required = _TOOL_REQUIRED_SCOPE.get(tool_name, "tools:call")
	# Scope hierarchy: tools:orchestrate > tools:call > tools:read
	# A higher scope implicitly grants lower ones.
	if "tools:orchestrate" in granted_scopes:
		return True
	if "tools:call" in granted_scopes and required in ("tools:call", "tools:read"):
		return True
	if "tools:read" in granted_scopes and required == "tools:read":
		return True
	return False


def _validate_provider(provider: str | None = None) -> None:
    """Raise ProviderNotConfiguredError if the requested provider lacks its API key.

    When provider is None, falls back to the LLM_PROVIDER env var.
    ollama never raises (no key required).
    """
    resolved = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    env_var = _PROVIDER_KEY_MAP.get(resolved)
    if env_var and not os.getenv(env_var):
        raise ProviderNotConfiguredError(resolved, env_var)


async def _agents_dispatch(req: MCPRequest, _claims: dict | None) -> MCPResponse:
    """Handle all agents/* JSON-RPC methods."""
    from mcp_agent_factory.agents.analyst import AnalystAgent, DocumentAnalysisTask

    method = req.method
    params = req.params or {}
    req_id = req.id

    if method == "agents/analyze":
        pdf_path: str = params.get("pdf_path", "")
        query: str = params.get("query", "Identify key KPIs and risk areas")
        max_pages: int = int(params.get("max_pages", 20))
        provider: str | None = params.get("provider") or None

        if not pdf_path:
            return _err(req_id, -32602, "Invalid params: pdf_path is required")

        # In DEV_MODE, skip the full pipeline and return a stub result so the
        # fleet demo works without any cloud API keys.
        if DEV_MODE:
            return _ok(req_id, {
                "summary": f"[DEV_MODE stub] {query}",
                "provider": "stub",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.0,
                "pages_read": 1,
                "total_pages": 1,
                "chunks_before_pruning": 4,
                "chunks_after_pruning": 3,
            })

        # Validate provider key when auth is enforced (DEV_MODE off).
        if not DEV_MODE:
            try:
                _validate_provider(provider)
            except ProviderNotConfiguredError as exc:
                return _err(req_id, -32602, str(exc))

        try:
            from mcp_agent_factory.agents.models import AgentTask
            from mcp_agent_factory.economics.utility import AgentProfile

            auction_task = AgentTask(
                name="document_analysis",
                complexity=0.6,
                required_capability="document_analysis",
            )
            _profiles = [
                AgentProfile(agent_id="analyst", capabilities=["document_analysis", "knowledge_retrieval"], expertise_score=0.9, cost_per_unit=1.2),
                AgentProfile(agent_id="summarizer", capabilities=["summarization"], expertise_score=0.7, cost_per_unit=0.8),
                AgentProfile(agent_id="extractor", capabilities=["document_analysis", "extraction"], expertise_score=0.75, cost_per_unit=1.0),
            ]
            Auction().run(auction_task, _profiles)

            task = DocumentAnalysisTask(pdf_path=pdf_path, query=query, max_pages=max_pages, provider=provider)
            result = await AnalystAgent().analyze_document(task)
            # Publish telemetry to Kafka (fire-and-forget — never blocks the response)
            import time as _time
            try:
                await _event_log.append("agents.analyze", {
                    "type": "agents.analyze",
                    "provider": result.provider,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": result.cost_usd,
                    "pages_read": result.pages_read,
                    "ts": int(_time.time()),
                })
                await _event_log.append("token.usage", {
                    "type": "token.usage",
                    "model": result.provider,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": result.cost_usd,
                    "ts": int(_time.time()),
                })
            except Exception as _log_exc:
                logger.warning('{"event":"event_log_failure","detail":"%s"}', _log_exc)
            return _ok(req_id, {
                "summary": result.summary,
                "provider": result.provider,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "pages_read": result.pages_read,
                "total_pages": result.total_pages,
                "chunks_before_pruning": result.chunks_before_pruning,
                "chunks_after_pruning": result.chunks_after_pruning,
            })
        except Exception as exc:
            return _err(req_id, -32603, f"agents/analyze failed: {exc}")

    return _err(req_id, -32601, f"Method not found: {method}")


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


class QueryBody(BaseModel):
	question: str
	tenant: str
	top_k: int = 5


class QueryResponse(BaseModel):
	answer: str
	refused: bool
	refusal_reason: str | None = None
	citations: list[str] = []


@gateway_app.post("/query", response_model=QueryResponse)
async def query_endpoint(body: QueryBody) -> QueryResponse:
	"""RAG query endpoint — retrieves chunks then generates a cited answer.

	Enforces rate limiting and quotas, then logs to audit trail.
	"""
	# Pre-compute estimated cost from top_k (retrieval latency not yet known)
	# Full cost is recalculated after retrieval and used for the audit log.
	_estimated_cost = calculate_query_cost(
		top_k=body.top_k,
		retrieval_ms=0.0,  # unknown pre-retrieval
		refused=False,
		cfg=_query_manager.config,
	)

	# Rate limit check (deducts estimated cost — RAG-09 S3)
	rate_limit = await _query_manager.check_rate_limit(body.tenant, cost=_estimated_cost)
	if not rate_limit["allowed"]:
		raise HTTPException(
			status_code=429,
			detail=f"Rate limit exceeded. Retry after {rate_limit['retry_after_seconds']:.1f}s",
			headers={"Retry-After": str(int(rate_limit["retry_after_seconds"]))},
		)

	# Daily quota check
	quota = await _query_manager.check_quota(body.tenant, quota_type="daily")
	if not quota["allowed"]:
		raise HTTPException(
			status_code=429,
			detail=f"Daily quota exceeded ({quota['used']}/{quota['limit']}). Resets in {quota['reset_in_seconds']:.0f}s",
		)

	if _vector_store is None or _embedder is None:
		raise HTTPException(status_code=503, detail="Vector store or embedder not initialised")
	vector_store = _vector_store
	embedder = _embedder

	handler = GuardedQueryHandler(
		vector_store=vector_store,
		embedder=embedder,
		filter_resolver=DefaultFilterResolver(),
	)
	auth_context = {"tenant": body.tenant, "acl": [], "embedder_id": None}

	# Measure retrieval latency
	retrieval_start = time.time()
	try:
		chunks = handler.retrieve(query_text=body.question, auth_context=auth_context, top_k=body.top_k)
	except Exception as exc:
		logger.warning('{"event":"rag_retrieval_error","detail":"%s"}', exc)
		chunks = []
	retrieval_latency = (time.time() - retrieval_start) * 1000  # ms

	gen = GenerationHandler()

	async def _llm_call(prompt: str) -> str:  # noqa: RUF029
		# No LLM configured — synthesise a minimal valid answer from retrieved chunks.
		import json as _json
		_MIN_SCORE = 0.3
		if not chunks:
			return '{"answer":"","cited_chunk_ids":[],"refused":true,"refusal_reason":"No relevant information found."}'
		top = chunks[0]
		# Extract score — tuples are (text, score), objects may have .score
		if isinstance(top, tuple):
			score = top[1] if len(top) > 1 else 0.0
			text = top[0]
			chunk_id = "chunk-1"
		else:
			score = getattr(top, "score", 1.0)
			text = getattr(top, "text", str(top))
			chunk_id = getattr(top, "chunk_id", "chunk-1")
		if score < _MIN_SCORE:
			return '{"answer":"","cited_chunk_ids":[],"refused":true,"refusal_reason":"No relevant information found."}'
		return _json.dumps({
			"answer": text[:500],
			"cited_chunk_ids": [chunk_id],
			"refused": False,
			"refusal_reason": None,
		})

	# Measure generation latency
	generation_start = time.time()
	answer = await gen.generate(
		query=body.question,
		retrieved_chunks=chunks,
		llm_call=_llm_call,
		provider="internal",
	)
	generation_latency = (time.time() - generation_start) * 1000  # ms

	# Extract top score for logging
	top_score = None
	if chunks:
		top = chunks[0]
		if isinstance(top, tuple):
			top_score = top[1] if len(top) > 1 else None
		else:
			top_score = getattr(top, "score", None)

	# Calculate actual query cost post-retrieval (RAG-09 S3)
	actual_cost = calculate_query_cost(
		top_k=body.top_k,
		retrieval_ms=retrieval_latency,
		refused=answer.refused,
		cfg=_query_manager.config,
	)

	# Prometheus cost histogram (RAG-09 S3)
	try:
		from mcp_agent_factory.knowledge.query_handler import _query_cost_histogram as _qch
		_qch.observe(actual_cost)
	except Exception:
		pass

	# Log to audit trail
	await _query_manager.log_query(
		tenant=body.tenant,
		question=body.question,
		top_k=body.top_k,
		result_count=len(chunks),
		top_score=top_score,
		refused=answer.refused,
		refusal_reason=answer.refusal_reason,
		retrieval_latency_ms=retrieval_latency,
		generation_latency_ms=generation_latency,
		cost_tokens=actual_cost,
	)

	return QueryResponse(
		answer=answer.answer,
		refused=answer.refused,
		refusal_reason=answer.refusal_reason,
		citations=answer.cited_chunk_ids,
	)


# ---------------------------------------------------------------------------
# Query Management Endpoints — monitoring and quota administration
# ---------------------------------------------------------------------------


@gateway_app.get("/query/stats/{tenant}")
async def get_query_stats(tenant: str) -> dict:
	"""Get aggregated query stats for a tenant (last 24h)."""
	stats = await _query_manager.get_tenant_stats(tenant)
	return stats


class QuotaUpdate(BaseModel):
	"""Update quota for a tenant (RAG-08 + RAG-09 S2 timezone field)."""

	daily_limit: int | None = None
	hourly_limit: int | None = None
	tokens_per_second: float | None = None
	timezone: str | None = None  # RAG-09 S2


@gateway_app.post("/admin/quota/{tenant}")
async def update_quota(
	tenant: str,
	update: QuotaUpdate,
	_claims: dict | None = Depends(make_verify_token("tools:orchestrate", optional=False)),
) -> dict:
	"""Update rate limiting, quota, and timezone for a tenant (requires tools:orchestrate scope)."""
	# RAG-09 S2: validate and store timezone
	if update.timezone is not None:
		if not is_valid_timezone(update.timezone):
			raise HTTPException(status_code=400, detail=f"Invalid timezone: {update.timezone!r}")
		cfg = _query_manager.get_tenant_config(tenant)
		cfg = TenantConfig(
			tenant=tenant,
			timezone=update.timezone,
			daily_quota=update.daily_limit or cfg.daily_quota,
			hourly_quota=update.hourly_limit or cfg.hourly_quota,
			tokens_per_second=update.tokens_per_second or cfg.tokens_per_second,
			burst_size=cfg.burst_size,
		)
		_query_manager.set_tenant_config(cfg)
	else:
		if update.daily_limit is not None:
			_query_manager.config.daily_quota = update.daily_limit
		if update.hourly_limit is not None:
			_query_manager.config.hourly_quota = update.hourly_limit
		if update.tokens_per_second is not None:
			_query_manager.config.tokens_per_second = update.tokens_per_second

	tz = _query_manager.get_tenant_config(tenant).timezone
	# Calculate reset time for display
	from .query_management import _quota_reset_seconds
	reset_in = _quota_reset_seconds("daily", tz)
	hours_until_reset = round(reset_in / 3600, 1)

	return {
		"tenant": tenant,
		"daily_quota": _query_manager.config.daily_quota,
		"hourly_quota": _query_manager.config.hourly_quota,
		"tokens_per_second": _query_manager.config.tokens_per_second,
		"timezone": tz,
		"resets_in_hours": hours_until_reset,
	}


@gateway_app.get("/admin/quotas")
async def list_quotas(
	_claims: dict | None = Depends(make_verify_token("tools:orchestrate", optional=False)),
) -> dict:
	"""List current rate limiting and quota configuration (requires tools:orchestrate scope)."""
	from .query_management import _quota_reset_seconds
	tenants_info = {}
	for tenant, cfg in _query_manager._tenant_configs.items():
		reset_in = _quota_reset_seconds("daily", cfg.timezone)
		tenants_info[tenant] = {
			"timezone": cfg.timezone,
			"daily_quota": cfg.daily_quota,
			"hourly_quota": cfg.hourly_quota,
			"resets_in_hours": round(reset_in / 3600, 1),
		}
	return {
		"default": {
			"daily_quota": _query_manager.config.daily_quota,
			"hourly_quota": _query_manager.config.hourly_quota,
			"tokens_per_second": _query_manager.config.tokens_per_second,
			"burst_size": _query_manager.config.burst_size,
		},
		"tenants": tenants_info,
	}


@gateway_app.get("/query/audit/{tenant}")
async def export_audit_log(
	tenant: str,
	start: str = Query(..., description="Start date YYYY-MM-DD"),
	end: str = Query(..., description="End date YYYY-MM-DD (exclusive)"),
	fmt: str = Query("json", description="Export format: json or csv"),
) -> Any:
	"""Export durable audit logs from PostgreSQL for a date range (RAG-09 S1).

	Requires bearer token with tools:orchestrate scope.
	"""
	from datetime import timezone as _tz

	try:  # noqa: SIM105
		start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=_tz.utc)
		end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=_tz.utc)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=f"Invalid date format: {exc}") from exc

	if fmt not in ("json", "csv"):
		raise HTTPException(status_code=400, detail="fmt must be 'json' or 'csv'")

	data = await _query_manager.export_audit(tenant, start_dt, end_dt, fmt=fmt)  # type: ignore[arg-type]

	if fmt == "csv":
		from fastapi.responses import PlainTextResponse
		return PlainTextResponse(content=data, media_type="text/csv")
	return _JSONResponse(content=json.loads(data))


# ---------------------------------------------------------------------------
# SSE session store — maps session_id → asyncio.Queue for response push-back
# ---------------------------------------------------------------------------
_sse_sessions: dict[str, asyncio.Queue] = {}


@gateway_app.get("/sse")
async def mcp_legacy_sse_endpoint(
	request: Request,
	_claims: dict | None = Depends(make_verify_token("tools:call", optional=True)),
) -> Any:
	"""MCP legacy SSE transport (2024-11-05).

	Opens a persistent SSE stream. Sends an ``endpoint`` event with the
	absolute URL clients should POST JSON-RPC messages to. Each POST returns
	202 immediately; the response arrives back through this stream.
	"""
	session_id = str(uuid.uuid4())
	queue: asyncio.Queue = asyncio.Queue()
	_sse_sessions[session_id] = queue

	# Build the post-back URL using the request's base URL so it works behind
	# reverse proxies that rewrite the host header.
	base = str(request.base_url).rstrip("/")
	post_url = f"{base}/sse/messages?sessionId={session_id}"

	async def _events():
		try:
			yield {"event": "endpoint", "data": post_url}
			while True:
				try:
					message = await asyncio.wait_for(queue.get(), timeout=15.0)
					yield {"event": "message", "data": json.dumps(message)}
				except asyncio.TimeoutError:
					yield {"event": "ping", "data": ""}
		finally:
			_sse_sessions.pop(session_id, None)

	return EventSourceResponse(_events())


@gateway_app.post("/sse/messages")
async def mcp_sse_post(
	req: MCPRequest,
	session_id: str = Query(..., alias="sessionId"),
	_claims: dict | None = Depends(make_verify_token("tools:call", optional=True)),
) -> Response:
	"""Receive a JSON-RPC request from the SSE client, push response to its stream."""
	queue = _sse_sessions.get(session_id)
	if queue is None:
		return Response(status_code=404, content=b"Unknown session")
	resp = await _mcp_dispatch(req, _claims)
	await queue.put(resp.model_dump(exclude_none=True))
	return Response(status_code=202)


@gateway_app.get("/mcp")
async def mcp_streamable_sse_get(
	request: Request,
	_claims: dict | None = Depends(make_verify_token("tools:call", optional=True)),
) -> Any:
	"""Streamable HTTP SSE channel (server→client notifications, kept for compat)."""
	base = str(request.base_url).rstrip("/")
	post_url = f"{base}/mcp"

	async def _events():
		yield {"event": "endpoint", "data": post_url}
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
	_tracer = get_tracer()
	method = req.method
	params = req.params or {}
	req_id = req.id

	with _tracer.start_as_current_span(f"mcp.{method}") as span:
		span.set_attribute("mcp.method", method)
		if method == "tools/call":
			span.set_attribute("mcp.tool", params.get("name", ""))
		try:
			return await _mcp_dispatch_inner(req, _claims, span)
		except Exception as exc:
			span.record_exception(exc)
			try:
				from opentelemetry.trace import StatusCode
				span.set_status(StatusCode.ERROR, str(exc))
			except ImportError:
				pass
			raise


async def _mcp_dispatch_inner(req: MCPRequest, _claims: dict | None, _span) -> MCPResponse:
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

	# tools/list — filtered by caller's granted scopes (INT-01-C)
	if method == "tools/list":
		granted: set[str] = set()
		if _claims is not None:
			granted = set((_claims.get("scope") or "").split())
		elif DEV_MODE:
			# DEV_MODE grants all scopes so local testing sees every tool
			granted = {"tools:read", "tools:call", "tools:orchestrate"}
		visible_tools = [
			t for t in TOOLS
			if _tool_visible(t["name"], granted)
		]
		return _ok(req_id, {"tools": visible_tools})

	# agents/* — requires valid Bearer token (bypassed in DEV_MODE)
	if method.startswith("agents/"):
		if _claims is None and not DEV_MODE:
			return _err(req_id, -32001, "Authentication required for agents/*")
		return await _agents_dispatch(req, _claims)

	# tools/call — requires valid Bearer token (bypassed in DEV_MODE) + scope + not destructive (INT-01-C, INT-01-D)
	if method == "tools/call":
		if _claims is None and not DEV_MODE:
			return _err(req_id, -32001, "Authentication required for tools/call")
		tool_name: str = params.get("name", "")
		args: dict = params.get("arguments", {})

		# Destructive-tool guard: block direct tools/call for tools that require
		# graph-level approval (INT-01-D). DEV_MODE bypasses this so local testing works.
		if tool_name in _DESTRUCTIVE_TOOLS and not DEV_MODE:
			return _err(
				req_id,
				-32003,
				f"Tool '{tool_name}' requires graph-level execution. "
				"Submit via POST /mcp with agents/analyze or use the async fleet "
				"endpoints (POST /mcp/jobs) to allow human-in-the-loop approval.",
			)

		# Scope check for the specific tool (INT-01-C)
		if _claims is not None and not DEV_MODE:
			granted_scopes: set[str] = set((_claims.get("scope") or "").split())
			if not _tool_visible(tool_name, granted_scopes):
				required_scope = _TOOL_REQUIRED_SCOPE.get(tool_name, "tools:call")
				return _err(
					req_id,
					-32003,
					f"Insufficient scope for tool '{tool_name}': "
					f"'{required_scope}' required, granted: {sorted(granted_scopes)}",
				)

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
