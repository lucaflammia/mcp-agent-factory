# MCP Agent Factory

A production-grade **Model Context Protocol (MCP)** server ecosystem demonstrating collaborative multi-agent architectures, economic task allocation, async messaging, OAuth 2.1 security, external client connectivity, a vector-backed RAG layer, and a fault-tolerant streaming pipeline backed by real Kafka and multi-node Redis infrastructure — built across eight progressive milestones.

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
│  ValidationGate · InternalServiceLayer                       │
└──────┬──────────────┬──────────────┬────────────────────────-┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────────┐ ┌▼────────────────────────┐
│  Analyst→   │ │  Knowledge-    │ │    MessageBus +          │
│  Writer     │ │  Augmented     │ │    SSE v1 Transport      │
│  Pipeline   │ │  Auction       │ └─────────────────────────-┘
└──────┬──────┘ └────────────────┘
       │ auto-ingest
┌──────▼──────────────────────────────────────────────────────┐
│         Knowledge Layer                                      │
│  InMemoryVectorStore · StubEmbedder · IngestionWorker        │
│  LibrarianAgent · query_knowledge_base tool                  │
│  knowledge.retrieved SSE event                               │
└─────────────────────────────────────────────────────────────┘
       │
┌──────▼─────────────────────────────────────────────────────┐
│      Streaming / Reliability Layer                          │
│  StreamWorker (XREADGROUP/ACK/PEL)                          │
│  IdempotencyGuard · DistributedLock · OutboxRelay           │
│  CircuitBreaker (CLOSED→OPEN→HALF_OPEN)                     │
│  EventLog Protocol · InProcessEventLog · KafkaEventLog      │
└──────┬─────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│      Real Infrastructure Layer (M007)                        │
│  docker-compose: Kafka + Zookeeper + 4 Redis nodes           │
│  RedlockClient — 3-node quorum acquire / release             │
│  Multi-process StreamWorker — horizontal scaling + PEL rec.  │
└──────┬──────────────────────────────────────────────────────┘
       │
┌──────▼─────────────────────────────────────────────────────┐
│            Redis Session Manager (fakeredis / real)         │
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
| **Streams** | `streams/` | `StreamWorker` (XREADGROUP consumer groups, PEL recovery); `IdempotencyGuard` (SET NX pre-check + result cache); `DistributedLock` (single-node SET NX EX); `OutboxRelay` (in-process transactional outbox); `CircuitBreaker` (CLOSED→OPEN→HALF_OPEN); `EventLog` protocol + `InProcessEventLog`; `KafkaEventLog` |
| **Real Infrastructure** | `docker-compose.yml`, `streams/redlock.py` | 6-service docker-compose stack (Kafka, Zookeeper, 4× Redis); `RedlockClient` 3-node quorum; multi-process `StreamWorker` horizontal scaling; 8 integration tests (skip without Docker) |
| **Env-driven factories** | `gateway/app.py` | `REDIS_URL` → real `redis.asyncio` client; unset → `FakeRedis` fallback (tests need no docker); `KAFKA_BOOTSTRAP_SERVERS` → `KafkaEventLog`; unset → `InProcessEventLog` |
| **External Config** | `mcp.json` | IDE config for Cursor / Claude Desktop pointing at localhost gateway |

## Quick Start

```bash
pip install -e .          # redis>=5 is now a core dependency

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

# Gateway with real Redis (M008)
REDIS_URL=redis://localhost:6379 python -m mcp_agent_factory.gateway.run

# Gateway with a shared JWT secret (required when Bridge or external clients send real tokens)
JWT_SECRET=<same-secret-used-by-auth-server> python -m mcp_agent_factory.gateway.run

# Real infrastructure (Kafka + Redis cluster) — M007
docker-compose up -d
pip install -e ".[infra]"          # aiokafka extra
pytest -m integration -v           # 8 integration tests against live services
```

### JWT_SECRET and the Gateway / Auth Server handshake

The Gateway acts as an OAuth 2.1 Resource Server. To verify incoming Bearer tokens it must
share the same signing key as the Auth Server:

| Scenario | What to do |
|----------|-----------|
| Dev / `MCP_DEV_MODE=1` | No `JWT_SECRET` needed — auth is bypassed |
| Gateway + Auth Server in the same process | Key is set automatically at startup |
| Gateway + Auth Server as separate processes | Set `JWT_SECRET=<random-secret>` for **both** processes |

Without `JWT_SECRET` in a secured multi-process setup, the Gateway raises
`RuntimeError: JWT key not set` on the first authenticated request. The Bridge must
also send a real JWT (not the default `demo-token`) matching `aud: mcp-server`.

## External Client Integration

The gateway implements RFC 8414 OAuth 2.1 auto-discovery. Any compliant MCP client — Cursor, Claude Desktop, a custom Python/Node client — connects using the same protocol: discover → register → PKCE auth → Bearer JWT on every request.

### How it works end-to-end

```
MCP Client (Cursor / Claude Desktop / custom)
  │
  │ 1. GET /.well-known/oauth-authorization-server  (RFC 8414 discovery)
  │    ← {issuer, authorization_endpoint, token_endpoint, registration_endpoint, ...}
  │
  │ 2. POST /register  (dynamic client registration)
  │    ← {client_id}
  │
  │ 3. Redirect to /authorize?code_challenge=<S256>&...
  │    (user approves in browser)
  │    ← ?code=<one-time-code>
  │
  │ 4. POST /token  {code, code_verifier}
  │    ← {access_token, token_type: "bearer"}
  │
  │ 5. POST /mcp   Authorization: Bearer <JWT>
  │    {"jsonrpc":"2.0","method":"tools/call",...}
  │
  ▼
MCP Gateway :8000  →  Auth Server :8001  (same JWT_SECRET)
```

Every 401 response includes `WWW-Authenticate: Bearer resource_metadata=<discovery-url>` (RFC 6750 §3.1), so clients that missed step 1 can self-correct without any hardcoded endpoint config.

---

### Step 1 — Set environment variables

Both processes must share the same `JWT_SECRET`. Generate one and export it in every shell (or add to your secrets manager / `.env`):

```bash
export JWT_SECRET="$(openssl rand -hex 32)"
```

Optional but recommended for production:

```bash
export REDIS_URL="redis://your-redis:6379"        # real Redis for gateway sessions
export AUTH_REDIS_URL="redis://your-redis:6379"   # real Redis for auth codes + client registry
```

Without `REDIS_URL` / `AUTH_REDIS_URL` the servers fall back to an in-process `FakeRedis` — fine for development, not for multi-process or multi-node deployments.

---

### Step 2 — Start the auth server (port 8001)

```bash
JWT_SECRET=$JWT_SECRET uvicorn mcp_agent_factory.auth.server:auth_app \
  --host 0.0.0.0 --port 8001
```

---

### Step 3 — Start the MCP gateway (port 8000)

```bash
JWT_SECRET=$JWT_SECRET python -m mcp_agent_factory.gateway.run
# or
JWT_SECRET=$JWT_SECRET uvicorn mcp_agent_factory.gateway.run:app \
  --host 0.0.0.0 --port 8000
```

Or spin both up together with Docker Compose (already wired):

```bash
docker compose up
```

---

### Step 4 — Verify the stack is healthy

```bash
# Health check
curl http://localhost:8000/health
# {"status": "ok", "service": "mcp-gateway"}

# OAuth discovery document
curl http://localhost:8000/.well-known/oauth-authorization-server | python3 -m json.tool
# {
#   "issuer": "http://localhost:8001",
#   "authorization_endpoint": "http://localhost:8001/authorize",
#   "token_endpoint": "http://localhost:8001/token",
#   "registration_endpoint": "http://localhost:8001/register",
#   ...
# }

# 401 with WWW-Authenticate hint (no auth header)
curl -i http://localhost:8000/mcp
# HTTP/1.1 401
# WWW-Authenticate: Bearer realm="mcp-server",
#   resource_metadata="http://localhost:8000/.well-known/oauth-authorization-server"

# SSE stream (stays open — Ctrl-C to stop)
curl -N "http://localhost:8000/sse/v1/events?topic=agent.events"
# data: {"type":"connected","topic":"agent.events"}
```

---

### Connecting Cursor

Cursor reads `mcp.json` from the project root and runs the full PKCE flow automatically.

**Local development** — the repo ships a ready-to-use `mcp.json`:

```json
{
  "mcpServers": {
    "mcp-agent-factory": {
      "serverUrl": "http://localhost:8000",
      "transport": "sse",
      "discoveryUrl": "http://localhost:8000/.well-known/oauth-authorization-server",
      "auth": {
        "type": "oauth2",
        "pkce": true,
        "codeChallengeMethod": "S256",
        "scopes": ["tools:call"]
      }
    }
  }
}
```

Open the project in Cursor. On first use Cursor fetches the discovery document, registers itself, opens a browser tab for the authorization redirect, exchanges the code for a JWT, and then attaches `Authorization: Bearer <token>` to every tool call — no manual configuration beyond placing `mcp.json` in the project root.

**Remote/production deployment** — replace `localhost` with your host. TLS is strongly recommended:

```json
{
  "mcpServers": {
    "mcp-agent-factory": {
      "serverUrl": "https://mcp.example.com",
      "transport": "sse",
      "discoveryUrl": "https://mcp.example.com/.well-known/oauth-authorization-server",
      "auth": {
        "type": "oauth2",
        "pkce": true,
        "codeChallengeMethod": "S256",
        "scopes": ["tools:call"]
      }
    }
  }
}
```

Cursor re-reads `mcp.json` on project reload (or after a "Reconnect MCP server" from the Command Palette).

---

### Connecting Claude Desktop

Claude Desktop uses the same `mcp.json` format. Place it (or merge it into your global `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS) with the same fields shown above. Claude Desktop performs the same PKCE flow; a browser tab will open once to authorise the connection.

---

### Connecting any MCP client (Python example)

The repo ships `bridge/gateway_client.py` — a minimal reference client you can copy into any project:

```python
import asyncio
from mcp_agent_factory.bridge.gateway_client import MCPGatewayClient
from mcp_agent_factory.bridge.oauth_middleware import OAuthMiddleware

# 1. Obtain a Bearer JWT (e.g. from your auth server's /token endpoint)
#    In production this is handled by OAuthMiddleware (token cache + auto-refresh).
token = "eyJ..."

# 2. Instantiate the client
client = MCPGatewayClient(
    base_url="http://localhost:8000",
    token=token,
)

async def main():
    # 3. List available tools
    tools = await client.list_tools()
    print(tools)

    # 4. Call a tool
    result = await client.call_tool("echo", {"text": "hello"})
    print(result)

    # 5. Stream SSE events
    async for event in client.stream_events(topic="agent.events"):
        print(event)

asyncio.run(main())
```

For a self-contained demo that handles token acquisition automatically:

```bash
JWT_SECRET=$JWT_SECRET python -m mcp_agent_factory.bridge
```

---

### Connecting via raw HTTP (curl / any HTTP client)

All MCP calls are plain JSON-RPC 2.0 over HTTPS. Once you have a Bearer token:

```bash
TOKEN="eyJ..."   # JWT from POST /token

# List tools
curl -s -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -m json.tool

# Call a tool
curl -s -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": "echo", "arguments": {"text": "hello"}}
  }' | python3 -m json.tool

# Query the knowledge base
curl -s -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {"name": "query_knowledge_base", "arguments": {"query": "climate", "top_k": 3}}
  }' | python3 -m json.tool
```

**Dev mode (no auth)** — set `MCP_DEV_MODE=1` to disable token verification. Useful for local scripting:

```bash
MCP_DEV_MODE=1 python -m mcp_agent_factory.gateway.run &

curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

> Never run `MCP_DEV_MODE=1` in production — it disables all authentication.

---

### Gateway endpoint reference

| Method | Path | Auth required | Purpose |
|--------|------|---------------|---------|
| `GET` | `/health` | No | Liveness probe |
| `GET` | `/.well-known/oauth-authorization-server` | No | RFC 8414 discovery (proxies `:8001`) |
| `POST` | `/mcp` | Bearer JWT | JSON-RPC 2.0 tool calls (`tools/list`, `tools/call`) |
| `POST` | `/sampling` | Bearer JWT | `sampling/createMessage` |
| `GET` | `/sse/v1/events` | No | SSE event stream (`?topic=<name>`) |
| `POST` | `/sse/v1/messages` | Bearer JWT | Publish to SSE bus |

Auth server endpoints (`:8001`):

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/register` | Dynamic client registration (RFC 7591) |
| `GET` | `/authorize` | Authorization code + PKCE challenge |
| `POST` | `/token` | Code exchange → JWT |

---

### Production checklist

| Item | Notes |
|------|-------|
| `JWT_SECRET` set on both processes | Same secret required — gateway can't verify tokens without it |
| `MCP_DEV_MODE` unset or `0` | Never `1` in production |
| Real Redis (`REDIS_URL`, `AUTH_REDIS_URL`) | In-process FakeRedis doesn't survive restarts |
| TLS termination | Put a reverse proxy (nginx, Caddy) in front; JWT tokens must not travel over plain HTTP |
| Token rotation | HS256 is fine for a single gateway+auth pair; switch to RS256 + JWKS for multi-service deployments |
| Port exposure | Auth server (`:8001`) should not be public-facing; only the gateway (`:8000`) needs external access |

## RAG Knowledge Base       

The `query_knowledge_base` tool is registered on the gateway and callable from any MCP client:

If you want to test right now without modifying files, please restart the gateway connection with the use of this one-liner that injects the override into the running process (using a temporary wrapper):

```python
# Via gateway (dev mode — no auth required)
MCP_DEV_MODE=1 python -c "
import os
from mcp_agent_factory.gateway.app import gateway_app, make_verify_token
import uvicorn
import httpx
import threading
import time

# 1. Apply the override dynamically
async def mock_verify():
	return {'sub': 'dev-user', 'scope': 'tools:call'}

gateway_app.dependency_overrides[make_verify_token('tools:call', optional=True)] = mock_verify

# 2. Run server in a thread or just use uvicorn to start it properly
# For a quick check, let's just use uvicorn directly:
if __name__ == '__main__':
	uvicorn.run(gateway_app, host='127.0.0.1', port=8000)
"
```
Once that server is running in Terminal A, run this in Terminal B:

```bash
curl -X POST http://localhost:8000/mcp \
	-H "Content-Type: application/json" \
	-d '{
		"jsonrpc": "2.0",
		"id": 1,
		"method": "tools/call",
		"params": {"name": "query_knowledge_base", "arguments": {"query": "test", "top_k": 1}}
	}'
```

Every call emits a `knowledge.retrieved` SSE event with `owner_id`, `chunk_count`, and `source` — observable via `/sse/v1/events`. Data is namespace-isolated by JWT `sub` claim so one user's chunks are never visible to another.

```python
python -c '
# Direct Python usage
from mcp_agent_factory.knowledge import InMemoryVectorStore, StubEmbedder, query_knowledge_base

store, embedder = InMemoryVectorStore(), StubEmbedder()
store.upsert("alice", "prior climate analysis", embedder.embed("prior climate analysis"))
chunks = query_knowledge_base("climate", "alice", store, embedder, top_k=3)
print(chunks)
' 
# [{"text": "prior climate analysis", "score": 0.99...}]
```

## Fault-Tolerant Streaming Pipeline

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

if not guard.already_seen(task.id):        # Skip if already processed
	lock.acquire(f"lock:{task.id}")          # Prevent double-execution
	result = cb.call(llm_fn, fallback="[Internal Knowledge]")
	guard.cache_result(task.id, result)      # Cache for retry
	relay.add(write_state, dispatch_event)
	relay.flush()                            # Atomic state+dispatch
	worker.ack(claimed_id)
```

**Circuit breaker states:**
- `CLOSED` — normal operation; failure count tracked
- `OPEN` — threshold reached; returns `fallback` immediately without calling `fn`
- `HALF_OPEN` — after `recovery_timeout`; one probe call; success → CLOSED, failure → OPEN

## Running Tests

```bash
pytest tests/ -v          # 236 unit tests (11 skipped without Docker) — no external services required

# By milestone
pytest tests/test_mcp_lifecycle.py tests/test_react_loop.py tests/test_e2e_routing.py   # M001
pytest tests/test_scheduler.py tests/test_auth.py tests/test_server_http.py             # M002
pytest tests/test_pipeline.py tests/test_economics.py tests/test_message_bus.py tests/test_gateway.py tests/test_langchain_bridge.py  # M003
pytest tests/test_m004_sse.py tests/test_m004_auth_pkce.py tests/test_m004_client_bridge.py  # M004
pytest tests/test_vector_store.py tests/test_ingest.py tests/test_knowledge_auction.py tests/test_s04.py  # M005
pytest tests/test_m006_streams.py tests/test_m006_eventlog.py tests/test_m006_gateway.py tests/test_m006_reliability.py tests/test_m006_integration.py  # M006
pytest tests/test_m007_kafka.py tests/test_m007_redlock.py tests/test_m007_scaling.py   # M007 (unit)
pytest tests/test_m008_integration.py                                                   # M008

# Integration tests — requires docker-compose up -d
pytest -m integration -v  # 8 tests: KafkaEventLog, Redlock quorum, multi-process scaling
```

## Project Layout

```
mcp.json                            # External IDE config (Cursor / Claude Desktop)
docker-compose.yml                  # Real infrastructure: Kafka + Zookeeper + 4× Redis
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
├── streams/                        # Fault-tolerant streaming layer (M006–M007)
│   ├── __init__.py                 # Public re-exports (incl. RedlockClient)
│   ├── worker.py                   # StreamWorker (XREADGROUP/ACK/PEL)
│   ├── eventlog.py                 # EventLog protocol + InProcessEventLog
│   ├── kafka_adapter.py            # KafkaEventLog (aiokafka, real Kafka)
│   ├── idempotency.py              # IdempotencyGuard, DistributedLock, OutboxRelay
│   ├── circuit_breaker.py         # CircuitBreaker (CLOSED→OPEN→HALF_OPEN)
│   └── redlock.py                  # RedlockClient — 3-node quorum acquire/release
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
├── test_m006_integration.py        # M006: End-to-end pipeline integration
├── test_m007_kafka.py              # M007: KafkaEventLog integration (real Kafka)
├── test_m007_redlock.py            # M007: RedlockClient 3-node quorum
├── test_m007_scaling.py            # M007: Multi-process StreamWorker scaling
└── conftest_integration.py         # M007: Docker-aware fixtures (real_redis, real_kafka)
```

## Milestone History

| Milestone | Focus | Tests |
|-----------|-------|-------|
| M001 | STDIO MCP lifecycle, ReAct loop, schema validation, privacy config | 31 |
| M002 | Async TaskScheduler, FastAPI HTTP server, LLM adapters, OAuth 2.1 + PKCE | +69 (100) |
| M003 | Multi-agent pipeline, economic allocation, async message bus, API gateway, LangChain bridge | +61 (161) |
| M004 | SSE /v1 streaming, PKCE hardening, client bridge with token cache, mcp.json IDE config | +37 (198) |
| M005 | Vector RAG layer, multi-tenant isolation, async ingestion, knowledge-augmented auction, LibrarianAgent, SSE events | +7 (205) |
| M006 | Redis Streams consumer groups, EventLog + KafkaEventLog, ValidationGate, IdempotencyGuard, DistributedLock, OutboxRelay, CircuitBreaker | +26 (231) |
| M007 | docker-compose stack, real KafkaEventLog integration tests, RedlockClient 3-node quorum, multi-process StreamWorker scaling | +15 unit / +8 integration (246 unit) |
| M008 | Production wiring: env-driven Redis/Kafka factories, Redis-backed OAuth state, EventLog on every tool call; `redis>=5` promoted to core dep | +5 (236 unit) |

## Security Notes

- JWT tokens use HS256. Set `JWT_SECRET` to share the signing key between the Gateway and Auth Server processes; without it the Gateway cannot verify tokens and raises `RuntimeError: JWT key not set`. Rotate to RS256 + JWKS for multi-service deployments.
- All 401 responses carry a `WWW-Authenticate` header with `resource_metadata` pointing at the gateway's `/.well-known/oauth-authorization-server` endpoint — compliant clients (Cursor, Claude Desktop) use this to auto-discover auth endpoints without hardcoded URLs.
- Gateway proxies the Auth Server's RFC 8414 discovery document at `GET /.well-known/oauth-authorization-server`. Clients need only the gateway URL; all auth endpoints are discovered at runtime.
- `PrivacyConfig.assert_no_egress()` guards against accidental outbound calls — checked at startup via FastAPI lifespan.
- PKCE S256 enforced on all authorization code exchanges; codes are single-use.
- Audience binding (`aud: mcp-server`) prevents confused-deputy attacks.
- Gateway rejects all requests without a valid, non-expired Bearer JWT — 401 on missing/expired/wrong-audience tokens.
- RAG vector store is namespace-isolated by `owner_id` (bound to JWT `sub`) — cross-tenant queries return empty results by design.
- `DistributedLock` uses a UUID token to prevent a worker from releasing another holder's lock after TTL expiry.
