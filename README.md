# MCP Agent Factory

A production-grade **Model Context Protocol (MCP)** server ecosystem demonstrating collaborative multi-agent architectures, economic task allocation, async messaging, OAuth 2.1 security, external client connectivity, a vector-backed RAG layer, and a fault-tolerant streaming pipeline — built across six progressive milestones.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     External Clients                         │
│   Cursor / Claude Desktop / MCPGatewayClient + mcp.json      │
└────────────────────────┬─────────────────────────────────────┘
                         │ Bearer JWT (OAuth 2.1 / PKCE S256)
┌────────────────────────▼─────────────────────────────────────┐
│                 MCP API Gateway (FastAPI :8000)               │
│  POST /mcp   POST /sampling   GET /health                     │
│  GET  /sse/v1/events          POST /sse/v1/messages           │
│  ValidationGate · InternalServiceLayer (M006)                │
└──────┬──────────────┬──────────────┬────────────────────────-┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────────┐ ┌▼────────────────────────┐
│  Analyst→   │ │  Knowledge-    │ │    MessageBus +          │
│  Writer     │ │  Augmented     │ │    SSE v1 Transport      │
│  Pipeline   │ │  Auction       │ └─────────────────────────-┘
└──────┬──────┘ └────────────────┘
       │ auto-ingest
┌──────▼──────────────────────────────────────────────────────┐
│         Knowledge Layer (M005)                               │
│  InMemoryVectorStore · StubEmbedder · IngestionWorker        │
│  LibrarianAgent · query_knowledge_base tool                  │
│  knowledge.retrieved SSE event                               │
└─────────────────────────────────────────────────────────────┘
       │
┌──────▼─────────────────────────────────────────────────────┐
│      Streaming / Reliability Layer (M006)                   │
│  StreamWorker (XREADGROUP/ACK/PEL)                          │
│  IdempotencyGuard · DistributedLock · OutboxRelay           │
│  CircuitBreaker (CLOSED→OPEN→HALF_OPEN)                     │
│  EventLog Protocol · InProcessEventLog · KafkaEventLog stub │
└──────┬─────────────────────────────────────────────────────┘
       │
┌──────▼─────────────────────────────────────────────────────┐
│            Redis Session Manager (fakeredis)                │
└────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│              OAuth 2.1 Auth Server (:8001)                   │
│   POST /register   GET /authorize   POST /token              │
│   PKCE S256 only · one-time codes · audience-bound JWTs      │
└──────────────────────────────────────────────────────────────┘
```

## Features

| Layer | Module | What it does |
|-------|--------|--------------|
| **MCP Protocol** | `server.py` (STDIO), `server_http.py` (HTTP) | JSON-RPC 2.0 over STDIO and FastAPI; echo + add + query_knowledge_base tools |
| **Task Scheduler** | `scheduler.py` | Priority queue, retry logic, structured state-transition logging |
| **LLM Adapters** | `adapters.py` | Normalises tool schemas for Claude, OpenAI, and Gemini |
| **ReAct Loop** | `react_loop.py` | Perception → Reasoning → Action agent loop |
| **Agent Pipeline** | `agents/` | `AnalystAgent` → `WriterAgent` coordinated by `MultiAgentOrchestrator`; `LibrarianAgent` for RAG retrieval |
| **Session State** | `session/manager.py` | Redis-backed key/value store for cross-agent handoffs |
| **Economics** | `economics/` | Utility scoring + knowledge-augmented sealed-bid auction |
| **Knowledge (RAG)** | `knowledge/` | `InMemoryVectorStore` (cosine similarity, multi-tenant), `StubEmbedder`, `IngestionWorker`, `query_knowledge_base` |
| **Messaging** | `messaging/` | Async `MessageBus` (fan-out by topic) + SSE v1 router; `knowledge.retrieved` event on every RAG query |
| **Gateway** | `gateway/` | Authenticated MCP API gateway; `ValidationGate` blocks malformed payloads; `InternalServiceLayer` handles tool dispatch; SSE /v1 endpoints |
| **Auth (OAuth 2.1)** | `auth/` | PKCE S256 auth server, JWT resource middleware, audience binding |
| **Bridge** | `bridge/` | `OAuthMiddleware` (token cache + 60s refresh) + `MCPGatewayClient` with SSE stream |
| **Streams (M006)** | `streams/` | `StreamWorker` (XREADGROUP consumer groups, PEL recovery); `IdempotencyGuard` (SET NX pre-check + result cache); `DistributedLock` (single-node SET NX EX); `OutboxRelay` (in-process transactional outbox); `CircuitBreaker` (CLOSED→OPEN→HALF_OPEN); `EventLog` protocol + `InProcessEventLog`; `KafkaEventLog` stub |
| **External Config** | `mcp.json` | IDE config for Cursor / Claude Desktop pointing at localhost gateway |

## Quick Start

```bash
pip install -e .

# STDIO server
python -m mcp_agent_factory.server

# HTTP server (unauthenticated)
uvicorn mcp_agent_factory.server_http:app --reload

# HTTP server (OAuth-secured)
uvicorn mcp_agent_factory.server_http_secured:secured_app --reload

# MCP API Gateway (full stack, port 8000)
python -m mcp_agent_factory.gateway.run

# Python client bridge CLI demo
python -m mcp_agent_factory.bridge
```

## External Client Integration (M004)

The gateway is ready for Cursor, Claude Desktop, or any MCP-compatible client:

1. **Start the gateway** on port 8000:
   ```bash
   python -m mcp_agent_factory.gateway.run
   ```

2. **Start the auth server** on port 8001 (for real token issuance):
   ```bash
   uvicorn mcp_agent_factory.auth.server:auth_app --port 8001
   ```

3. **Point your IDE** at `mcp.json` — it contains the server URL, PKCE auth config, and full tool schemas.

4. **SSE stream** (stays open, first event is `connected`):
   ```bash
   curl -N http://localhost:8000/sse/v1/events?topic=agent.events
   ```

5. **Health check**:
   ```bash
   curl http://localhost:8000/health
   # {"status": "ok", "service": "mcp-gateway"}
   ```

## RAG Knowledge Base (M005)

The `query_knowledge_base` tool is registered on the gateway and callable from any MCP client:

```python
# Via gateway (dev mode — no auth required)
MCP_DEV_MODE=1 python -c "
import httpx, json
resp = httpx.post('http://localhost:8000/mcp', json={
    'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
    'params': {'name': 'query_knowledge_base', 'arguments': {'query': 'climate analysis', 'top_k': 3}}
})
print(resp.json())
"
```

Every call emits a `knowledge.retrieved` SSE event with `owner_id`, `chunk_count`, and `source` — observable via `/sse/v1/events`. Data is namespace-isolated by JWT `sub` claim so one user's chunks are never visible to another.

```python
# Direct Python usage
from mcp_agent_factory.knowledge import InMemoryVectorStore, StubEmbedder, query_knowledge_base

store, embedder = InMemoryVectorStore(), StubEmbedder()
store.upsert("alice", "prior climate analysis", embedder.embed("prior climate analysis"))
chunks = query_knowledge_base("climate", "alice", store, embedder, top_k=3)
# [{"text": "prior climate analysis", "score": 0.99...}]
```

## Fault-Tolerant Streaming Pipeline (M006)

All components use `fakeredis` — no external Redis or Kafka process required.

```python
from mcp_agent_factory.streams import (
    StreamWorker, IdempotencyGuard, DistributedLock,
    OutboxRelay, CircuitBreaker, InProcessEventLog,
)

r = fakeredis.FakeRedis()
worker = StreamWorker(r, "tasks.search", "workers", "worker-0")
worker.ensure_group()

guard = IdempotencyGuard(r, ttl=300)
lock  = DistributedLock(r, ttl=10)
cb    = CircuitBreaker(threshold=3, recovery_timeout=1.0)
relay = OutboxRelay()
log   = InProcessEventLog()

# Publish → claim → guard → lock → circuit breaker → outbox → ACK
msg_id = worker.publish(task)
claimed_id, fields = worker.claim_one()

if not guard.already_seen(task.id):          # R008: skip if already processed
    lock.acquire(f"lock:{task.id}")          # R009: prevent double-execution
    result = cb.call(llm_fn, fallback="[Internal Knowledge]")  # R011/R013
    guard.cache_result(task.id, result)      # R014: cache for retry
    relay.add(write_state, dispatch_event)
    relay.flush()                            # R010: atomic state+dispatch
    worker.ack(claimed_id)
```

**Circuit breaker states:**
- `CLOSED` — normal operation; failure count tracked
- `OPEN` — threshold reached; returns `fallback` immediately without calling `fn`
- `HALF_OPEN` — after `recovery_timeout`; one probe call; success → CLOSED, failure → OPEN

## Running Tests

```bash
pytest tests/ -v          # all 231 tests

# By milestone
pytest tests/test_mcp_lifecycle.py tests/test_react_loop.py tests/test_e2e_routing.py   # M001
pytest tests/test_scheduler.py tests/test_auth.py tests/test_server_http.py             # M002
pytest tests/test_pipeline.py tests/test_economics.py tests/test_message_bus.py tests/test_gateway.py tests/test_langchain_bridge.py  # M003
pytest tests/test_m004_sse.py tests/test_m004_auth_pkce.py tests/test_m004_client_bridge.py  # M004
pytest tests/test_vector_store.py tests/test_ingest.py tests/test_knowledge_auction.py tests/test_s04.py  # M005
pytest tests/test_m006_streams.py tests/test_m006_eventlog.py tests/test_m006_gateway.py tests/test_m006_reliability.py tests/test_m006_integration.py  # M006
```

## Code Style

All Python source files use **tab indentation** (1 tab = 1 indent level).

## Project Layout

```
mcp.json                            # External IDE config (Cursor / Claude Desktop)
src/mcp_agent_factory/
├── server.py                       # STDIO MCP server
├── server_http.py                  # FastAPI HTTP MCP server
├── server_http_secured.py          # OAuth-secured variant
├── models.py                       # Pydantic tool input models
├── adapters.py                     # LLM adapter layer
├── react_loop.py                   # ReAct agent loop
├── scheduler.py                    # Task scheduler + priority queue
├── orchestrator.py                 # MCP orchestrator client
├── config/privacy.py               # PrivacyConfig + egress guard
├── agents/                         # Multi-agent pipeline
│   ├── models.py                   # AgentTask, MCPContext, RetrievalResult, shared models
│   ├── analyst.py                  # AnalystAgent
│   ├── writer.py                   # WriterAgent
│   ├── librarian.py                # LibrarianAgent (RAG retrieval synthesis)
│   └── pipeline_orchestrator.py
├── session/manager.py              # Redis session manager
├── economics/
│   ├── utility.py                  # Utility function scoring
│   └── auction.py                  # Knowledge-augmented sealed-bid auction
├── knowledge/                      # RAG layer (M005)
│   ├── __init__.py                 # Public re-exports
│   ├── vector_store.py             # InMemoryVectorStore (cosine, multi-tenant)
│   ├── embedder.py                 # Embedder protocol + StubEmbedder
│   ├── ingest.py                   # IngestionWorker
│   └── tools.py                    # query_knowledge_base function
├── messaging/
│   ├── bus.py                      # Async MessageBus (topic fan-out)
│   ├── sse_router.py               # Legacy SSE router (/sse/legacy)
│   └── sse_v1_router.py            # SSE v1 router (/sse/v1/events + /messages)
├── gateway/
│   ├── app.py                      # MCP API Gateway FastAPI app
│   ├── validation.py               # ValidationGate (Pydantic schema guard)
│   ├── service_layer.py            # InternalServiceLayer (tool dispatch)
│   ├── run.py                      # Production uvicorn entrypoint
│   └── sampling.py                 # Sampling/createMessage handler
├── streams/                        # Fault-tolerant streaming layer (M006)
│   ├── __init__.py                 # Public re-exports
│   ├── worker.py                   # StreamWorker (XREADGROUP/ACK/PEL)
│   ├── eventlog.py                 # EventLog protocol + InProcessEventLog
│   ├── kafka_adapter.py            # KafkaEventLog stub (aiokafka swap-in)
│   ├── idempotency.py              # IdempotencyGuard, DistributedLock, OutboxRelay
│   └── circuit_breaker.py         # CircuitBreaker (CLOSED→OPEN→HALF_OPEN)
├── auth/
│   ├── server.py                   # OAuth 2.1 auth server (PKCE S256)
│   ├── resource.py                 # JWT Bearer middleware
│   └── session.py                  # Session ID utilities
└── bridge/
    ├── __main__.py                 # CLI demo entrypoint
    ├── oauth_middleware.py         # Token-caching OAuth middleware
    └── gateway_client.py           # MCPGatewayClient (httpx + SSE stream)

tests/
├── test_mcp_lifecycle.py           # M001: STDIO protocol lifecycle
├── test_react_loop.py              # M001: ReAct loop unit tests
├── test_e2e_routing.py             # M001: End-to-end routing
├── test_schema_validation.py       # M001: Pydantic validation + privacy
├── test_scheduler.py               # M002: Scheduler + retry logic
├── test_adapters.py                # M002: LLM adapter normalisation
├── test_server_http.py             # M002: HTTP server endpoints
├── test_auth.py                    # M002: OAuth 2.1 full flow
├── test_integration.py             # M002: Scheduler ↔ HTTP integration
├── test_pipeline.py                # M003: Analyst→Writer pipeline
├── test_economics.py               # M003: Utility + auction
├── test_message_bus.py             # M003: MessageBus + SSE
├── test_gateway.py                 # M003: API Gateway
├── test_langchain_bridge.py        # M003: OAuth bridge + client
├── test_m004_sse.py                # M004: SSE /v1 endpoints
├── test_m004_auth_pkce.py          # M004: PKCE hardening + 401 enforcement
├── test_m004_client_bridge.py      # M004: MCPGatewayClient lifecycle
├── test_vector_store.py            # M005: VectorStore cosine search + isolation
├── test_ingest.py                  # M005: IngestionWorker lifecycle
├── test_knowledge_auction.py       # M005: Knowledge-augmented auction
├── test_s04.py                     # M005: LibrarianAgent + gateway tool + SSE event
├── test_m006_streams.py            # M006: StreamWorker XREADGROUP/ACK/PEL
├── test_m006_eventlog.py           # M006: EventLog protocol + topic routing
├── test_m006_gateway.py            # M006: ValidationGate + InternalServiceLayer
├── test_m006_reliability.py        # M006: Idempotency + CircuitBreaker (R008–R014)
└── test_m006_integration.py        # M006: End-to-end pipeline integration
```

## Milestone History

| Milestone | Focus | Tests |
|-----------|-------|-------|
| M001 | STDIO MCP lifecycle, ReAct loop, schema validation, privacy config | 31 |
| M002 | Async TaskScheduler, FastAPI HTTP server, LLM adapters, OAuth 2.1 + PKCE | +69 (100) |
| M003 | Multi-agent pipeline, economic allocation, async message bus, API gateway, LangChain bridge | +61 (161) |
| M004 | SSE /v1 streaming, PKCE hardening, client bridge with token cache, mcp.json IDE config | +37 (198) |
| M005 | Vector RAG layer, multi-tenant isolation, async ingestion, knowledge-augmented auction, LibrarianAgent, SSE events | +7 (205) |
| M006 | Redis Streams consumer groups, EventLog + Kafka stub, ValidationGate, IdempotencyGuard, DistributedLock, OutboxRelay, CircuitBreaker | +26 (231) |

## Security Notes

- JWT tokens use HS256 with a randomly-generated `OctKey` per server start. Rotate to RS256 + JWKS for multi-service deployments.
- `PrivacyConfig.assert_no_egress()` guards against accidental outbound calls — checked at startup via FastAPI lifespan.
- PKCE S256 enforced on all authorization code exchanges; codes are single-use.
- Audience binding (`aud: mcp-server`) prevents confused-deputy attacks.
- Gateway rejects all requests without a valid, non-expired Bearer JWT — 401 on missing/expired/wrong-audience tokens.
- RAG vector store is namespace-isolated by `owner_id` (bound to JWT `sub`) — cross-tenant queries return empty results by design.
- `DistributedLock` uses a UUID token to prevent a worker from releasing another holder's lock after TTL expiry.


## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     External Clients                         │
│   Cursor / Claude Desktop / MCPGatewayClient + mcp.json      │
└────────────────────────┬─────────────────────────────────────┘
                         │ Bearer JWT (OAuth 2.1 / PKCE S256)
┌────────────────────────▼─────────────────────────────────────┐
│                 MCP API Gateway (FastAPI :8000)               │
│  POST /mcp   POST /sampling   GET /health                     │
│  GET  /sse/v1/events          POST /sse/v1/messages           │
└──────┬──────────────┬──────────────┬────────────────────────-┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────────┐ ┌▼────────────────────────┐
│  Analyst→   │ │  Knowledge-    │ │    MessageBus +          │
│  Writer     │ │  Augmented     │ │    SSE v1 Transport      │
│  Pipeline   │ │  Auction       │ └─────────────────────────-┘
└──────┬──────┘ └────────────────┘
       │ auto-ingest
┌──────▼──────────────────────────────────────────────────────┐
│         Knowledge Layer (M005)                               │
│  InMemoryVectorStore · StubEmbedder · IngestionWorker        │
│  LibrarianAgent · query_knowledge_base tool                  │
│  knowledge.retrieved SSE event                               │
└─────────────────────────────────────────────────────────────┘
       │
┌──────▼─────────────────────────────────────────────────────┐
│            Redis Session Manager (fakeredis)                │
└────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│              OAuth 2.1 Auth Server (:8001)                   │
│   POST /register   GET /authorize   POST /token              │
│   PKCE S256 only · one-time codes · audience-bound JWTs      │
└──────────────────────────────────────────────────────────────┘
```

## Features

| Layer | Module | What it does |
|-------|--------|--------------|
| **MCP Protocol** | `server.py` (STDIO), `server_http.py` (HTTP) | JSON-RPC 2.0 over STDIO and FastAPI; echo + add + query_knowledge_base tools |
| **Task Scheduler** | `scheduler.py` | Priority queue, retry logic, structured state-transition logging |
| **LLM Adapters** | `adapters.py` | Normalises tool schemas for Claude, OpenAI, and Gemini |
| **ReAct Loop** | `react_loop.py` | Perception → Reasoning → Action agent loop |
| **Agent Pipeline** | `agents/` | `AnalystAgent` → `WriterAgent` coordinated by `MultiAgentOrchestrator`; `LibrarianAgent` for RAG retrieval |
| **Session State** | `session/manager.py` | Redis-backed key/value store for cross-agent handoffs |
| **Economics** | `economics/` | Utility scoring + knowledge-augmented sealed-bid auction |
| **Knowledge (RAG)** | `knowledge/` | `InMemoryVectorStore` (cosine similarity, multi-tenant), `StubEmbedder`, `IngestionWorker`, `query_knowledge_base` |
| **Messaging** | `messaging/` | Async `MessageBus` (fan-out by topic) + SSE v1 router; `knowledge.retrieved` event on every RAG query |
| **Gateway** | `gateway/` | Authenticated MCP API gateway; SSE /v1 endpoints; stub sampling handler; RAG tool dispatch |
| **Auth (OAuth 2.1)** | `auth/` | PKCE S256 auth server, JWT resource middleware, audience binding |
| **Bridge** | `bridge/` | `OAuthMiddleware` (token cache + 60s refresh) + `MCPGatewayClient` with SSE stream |
| **External Config** | `mcp.json` | IDE config for Cursor / Claude Desktop pointing at localhost gateway |

## Quick Start

```bash
pip install -e .

# STDIO server
python -m mcp_agent_factory.server

# HTTP server (unauthenticated)
uvicorn mcp_agent_factory.server_http:app --reload

# HTTP server (OAuth-secured)
uvicorn mcp_agent_factory.server_http_secured:secured_app --reload

# MCP API Gateway (full stack, port 8000)
python -m mcp_agent_factory.gateway.run

# Python client bridge CLI demo
python -m mcp_agent_factory.bridge
```

## External Client Integration (M004)

The gateway is ready for Cursor, Claude Desktop, or any MCP-compatible client:

1. **Start the gateway** on port 8000:
   ```bash
   python -m mcp_agent_factory.gateway.run
   ```

2. **Start the auth server** on port 8001 (for real token issuance):
   ```bash
   uvicorn mcp_agent_factory.auth.server:auth_app --port 8001
   ```

3. **Point your IDE** at `mcp.json` — it contains the server URL, PKCE auth config, and full tool schemas.

4. **SSE stream** (stays open, first event is `connected`):
   ```bash
   curl -N http://localhost:8000/sse/v1/events?topic=agent.events
   ```

5. **Health check**:
   ```bash
   curl http://localhost:8000/health
   # {"status": "ok", "service": "mcp-gateway"}
   ```

## RAG Knowledge Base (M005)

The `query_knowledge_base` tool is registered on the gateway and callable from any MCP client:

```python
# Via gateway (dev mode — no auth required)
MCP_DEV_MODE=1 python -c "
import httpx, json
resp = httpx.post('http://localhost:8000/mcp', json={
    'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
    'params': {'name': 'query_knowledge_base', 'arguments': {'query': 'climate analysis', 'top_k': 3}}
})
print(resp.json())
"
```

Every call emits a `knowledge.retrieved` SSE event with `owner_id`, `chunk_count`, and `source` — observable via `/sse/v1/events`. Data is namespace-isolated by JWT `sub` claim so one user's chunks are never visible to another.

```python
# Direct Python usage
from mcp_agent_factory.knowledge import InMemoryVectorStore, StubEmbedder, query_knowledge_base

store, embedder = InMemoryVectorStore(), StubEmbedder()
store.upsert("alice", "prior climate analysis", embedder.embed("prior climate analysis"))
chunks = query_knowledge_base("climate", "alice", store, embedder, top_k=3)
# [{"text": "prior climate analysis", "score": 0.99...}]
```

## Running Tests

```bash
pytest tests/ -v          # all tests

# By milestone
pytest tests/test_mcp_lifecycle.py tests/test_react_loop.py tests/test_e2e_routing.py   # M001
pytest tests/test_scheduler.py tests/test_auth.py tests/test_server_http.py             # M002
pytest tests/test_pipeline.py tests/test_economics.py tests/test_message_bus.py tests/test_gateway.py tests/test_langchain_bridge.py  # M003
pytest tests/test_m004_sse.py tests/test_m004_auth_pkce.py tests/test_m004_client_bridge.py  # M004
pytest tests/test_vector_store.py tests/test_ingest.py tests/test_knowledge_auction.py tests/test_s04.py  # M005
```

## Code Style

All Python source files use **tab indentation** (1 tab = 1 indent level).

## Project Layout

```
mcp.json                            # External IDE config (Cursor / Claude Desktop)
src/mcp_agent_factory/
├── server.py                       # STDIO MCP server
├── server_http.py                  # FastAPI HTTP MCP server
├── server_http_secured.py          # OAuth-secured variant
├── models.py                       # Pydantic tool input models
├── adapters.py                     # LLM adapter layer
├── react_loop.py                   # ReAct agent loop
├── scheduler.py                    # Task scheduler + priority queue
├── orchestrator.py                 # MCP orchestrator client
├── config/privacy.py               # PrivacyConfig + egress guard
├── agents/                         # Multi-agent pipeline
│   ├── models.py                   # AgentTask, MCPContext, RetrievalResult, shared models
│   ├── analyst.py                  # AnalystAgent
│   ├── writer.py                   # WriterAgent
│   ├── librarian.py                # LibrarianAgent (RAG retrieval synthesis)
│   └── pipeline_orchestrator.py
├── session/manager.py              # Redis session manager
├── economics/
│   ├── utility.py                  # Utility function scoring
│   └── auction.py                  # Knowledge-augmented sealed-bid auction
├── knowledge/                      # RAG layer (M005)
│   ├── __init__.py                 # Public re-exports
│   ├── vector_store.py             # InMemoryVectorStore (cosine, multi-tenant)
│   ├── embedder.py                 # Embedder protocol + StubEmbedder
│   ├── ingest.py                   # IngestionWorker
│   └── tools.py                   # query_knowledge_base function
├── messaging/
│   ├── bus.py                      # Async MessageBus (topic fan-out)
│   ├── sse_router.py               # Legacy SSE router (/sse/legacy)
│   └── sse_v1_router.py            # SSE v1 router (/sse/v1/events + /messages)
├── gateway/
│   ├── app.py                      # MCP API Gateway FastAPI app
│   ├── run.py                      # Production uvicorn entrypoint
│   └── sampling.py                 # Sampling/createMessage handler
├── auth/
│   ├── server.py                   # OAuth 2.1 auth server (PKCE S256)
│   ├── resource.py                 # JWT Bearer middleware
│   └── session.py                  # Session ID utilities
└── bridge/
    ├── __main__.py                 # CLI demo entrypoint
    ├── oauth_middleware.py         # Token-caching OAuth middleware
    └── gateway_client.py           # MCPGatewayClient (httpx + SSE stream)

tests/
├── test_mcp_lifecycle.py           # M001: STDIO protocol lifecycle
├── test_react_loop.py              # M001: ReAct loop unit tests
├── test_e2e_routing.py             # M001: End-to-end routing
├── test_schema_validation.py       # M001: Pydantic validation + privacy
├── test_scheduler.py               # M002: Scheduler + retry logic
├── test_adapters.py                # M002: LLM adapter normalisation
├── test_server_http.py             # M002: HTTP server endpoints
├── test_auth.py                    # M002: OAuth 2.1 full flow
├── test_integration.py             # M002: Scheduler ↔ HTTP integration
├── test_pipeline.py                # M003: Analyst→Writer pipeline
├── test_economics.py               # M003: Utility + auction
├── test_message_bus.py             # M003: MessageBus + SSE
├── test_gateway.py                 # M003: API Gateway
├── test_langchain_bridge.py        # M003: OAuth bridge + client
├── test_m004_sse.py                # M004: SSE /v1 endpoints
├── test_m004_auth_pkce.py          # M004: PKCE hardening + 401 enforcement
├── test_m004_client_bridge.py      # M004: MCPGatewayClient lifecycle
├── test_vector_store.py            # M005: VectorStore cosine search + isolation
├── test_ingest.py                  # M005: IngestionWorker lifecycle
├── test_knowledge_auction.py       # M005: Knowledge-augmented auction
└── test_s04.py                     # M005: LibrarianAgent + gateway tool + SSE event
```

## Milestone History

| Milestone | Focus | Tests |
|-----------|-------|-------|
| M001 | STDIO MCP lifecycle, ReAct loop, schema validation, privacy config | 31 |
| M002 | Async TaskScheduler, FastAPI HTTP server, LLM adapters, OAuth 2.1 + PKCE | +69 (100) |
| M003 | Multi-agent pipeline, economic allocation, async message bus, API gateway, LangChain bridge | +61 (161) |
| M004 | SSE /v1 streaming, PKCE hardening, client bridge with token cache, mcp.json IDE config | +37 (198) |
| M005 | Vector RAG layer, multi-tenant isolation, async ingestion, knowledge-augmented auction, LibrarianAgent, SSE events | +7 (205+) |

## Security Notes

- JWT tokens use HS256 with a randomly-generated `OctKey` per server start. Rotate to RS256 + JWKS for multi-service deployments.
- `PrivacyConfig.assert_no_egress()` guards against accidental outbound calls — checked at startup via FastAPI lifespan.
- PKCE S256 enforced on all authorization code exchanges; codes are single-use.
- Audience binding (`aud: mcp-server`) prevents confused-deputy attacks.
- Gateway rejects all requests without a valid, non-expired Bearer JWT — 401 on missing/expired/wrong-audience tokens.
- RAG vector store is namespace-isolated by `owner_id` (bound to JWT `sub`) — cross-tenant queries return empty results by design.
