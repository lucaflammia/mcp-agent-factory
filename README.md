# MCP Agent Factory

[![CI](https://github.com/lucaflammia/mcp-agent-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/lucaflammia/mcp-agent-factory/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/lucaflammia/mcp-agent-factory/branch/main/graph/badge.svg)](https://codecov.io/gh/lucaflammia/mcp-agent-factory)

A **Model Context Protocol (MCP)** server ecosystem for collaborative multi-agent
architectures — with privacy-first design, full-stack observability, fault-tolerant
streaming, and standards-compliant security.

## Live Deployment

| | |
|---|---|
| **Public endpoint** | `https://<app_runner_url>/health` — run `make demo-up` then `terraform output gateway_url` |
| **Platform** | AWS App Runner (eu-west-1) — TLS, scale-to-zero, OIDC CI |
| **Idle cost** | **<€0.10/month** (ECR storage only; nothing runs at rest) |
| **Demo-day cost** | **~€1** (App Runner instance time) |
| **IaC** | [`terraform/`](terraform/) — `make demo-up` / `make demo-down` |
| **Deployment notes** | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — what broke and why |

> The environment is ephemeral by design: `make demo-up` takes ~8 minutes, `make demo-down`
> destroys everything. The cost at rest is zero because nothing is running.

## What It Does

**Privacy-first design** — `PIIGate` scrubs PII (emails, API keys, private IPs,
JWTs) at the gateway before any LLM call. `UnifiedRouter` dispatches to OpenAI,
Anthropic, or a local Ollama instance with automatic 429 fallback, so sensitive
payloads need not leave the host.

**Observability** — `EventLog` protocol with pluggable backends (in-process or
Kafka). OpenTelemetry span chain across gateway and agents, exported via
OTLP/gRPC to Jaeger. Prometheus counters for token usage and cost per provider.
Grafana dashboards included.

**Reliability** — `CircuitBreaker` (CLOSED → OPEN → HALF_OPEN), `IdempotencyGuard`
(SET NX + result cache), `DistributedLock` (single-node SET NX EX),
`OutboxRelay` (transactional outbox), `RedlockClient` (3-node quorum).

**Multi-tenant isolation** — `InMemoryVectorStore` namespaced by JWT `sub` claim.
Cross-tenant queries return empty results by design.

**Standards compliance** — MCP over STDIO and Streamable HTTP, OAuth 2.1 with
PKCE S256, RFC 8414 discovery, RFC 7591 dynamic client registration.

> **Note on defaults:** The knowledge layer ships with `StubEmbedder` and
> `InMemoryVectorStore` for zero-dependency startup. For production use, swap in
> a persistent vector store and a real embedder (e.g. `LocalEmbedder` with
> sentence-transformers via `pip install -e ".[ml]"`). The `Embedder` protocol in
> `knowledge/embedder.py` defines the interface.

## RAG Pipeline

### Before/after retrieval benchmark (EVAL-02 dataset, 32 labelled queries)

| Configuration | recall@5 | MRR | p95 latency | Cost/query |
|---|---|---|---|---|
| Dense only (baseline, InMemory) | 0.44 [0.28–0.61] | 0.31 | 1.2 s | $0.0004 |
| + pgvector (persistent, cosine) | 0.47 [0.30–0.64] | 0.33 | 0.8 s | $0.0004 |
| + hybrid RRF (dense + full-text) | 0.59 [0.42–0.75] | 0.42 | 0.9 s | $0.0004 |
| + cross-encoder reranking | 0.66 [0.49–0.80] | 0.51 | 2.1 s | $0.0004 |
| + structure-aware chunking | 0.63 [0.46–0.78] | 0.49 | 2.2 s | $0.0004 |

> The reranking row improves, but adding structure-aware chunking *alone* (without reranking on) slightly
> regressed recall@5 vs reranking. Chunking helps MRR but not recall at this corpus size — included for
> honest reporting.

Intervals are 95% Wilson CIs. k=60 used for RRF. Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`.

### Migration path (InMemory → pgvector)

1. Start the pgvector service: `docker compose --profile full up pgvector -d`
2. Apply the schema: `psql $DATABASE_URL -f migrations/001_pgvector_init.sql`
3. Configure the store:

```python
from mcp_agent_factory.knowledge import PgVectorStore, LocalEmbedder

store = PgVectorStore(dsn=os.environ["DATABASE_URL"])
embedder = LocalEmbedder()  # all-MiniLM-L6-v2, 384-dim
```

4. `InMemoryVectorStore` remains available for unit tests — no test changes needed.

## 4-Layer Execution Pipeline

| Layer | Framework | Module | Purpose |
|-------|-----------|--------|---------|
| 1 | PydanticAI | `structured_agent.py`, `orchestrator.py` | Schema-gated tool calls, Pydantic I/O contracts |
| 2 | LangGraph | `graph_orchestrator.py`, `evaluator.py` | Cyclic FSM (validate → plan → execute → evaluate), critic-actor loop, HITL |
| 3 | CrewAI | `crew.py` | Per-role MCP tool scoping, multi-agent coordination |
| 4 | DSPy + GEPA | `optimizer.py` | Offline trace-driven prompt optimization, hot-reloadable skill assets |

See [docs/architecture.md](docs/architecture.md) for detailed diagrams, request
lifecycle, and the LangGraph state machine specification.

## Quick Start

### Install

```bash
pip install -e .                   # core: fastapi, uvicorn, pydantic, authlib, redis, numpy
pip install -e ".[ml]"            # sentence-transformers for real RAG embeddings (~500 MB)
pip install -e ".[crew]"          # Layer 3: CrewAI multi-agent orchestration
pip install -e ".[optimizer]"     # Layer 4: DSPy + GEPA offline optimization
```

### Run the gateway

```bash
# In-memory mode — no Redis, auth bypassed
MCP_DEV_MODE=1 python -m mcp_agent_factory.gateway.run

# With real Redis
MCP_DEV_MODE=1 REDIS_URL=redis://localhost:6379 python -m mcp_agent_factory.gateway.run
```

### Connect with MCP Inspector

| Transport | URL | Notes |
|-----------|-----|-------|
| **Streamable HTTP** (recommended) | `http://localhost:8000/mcp` | Modern MCP spec; full duplex |
| **Legacy SSE** | `http://localhost:8000/sse` | MCP 2024-11-05 spec |

### Run the bridge smoke test

```bash
MCP_DEV_MODE=1 python -m mcp_agent_factory.bridge
# Lists 5 tools, prints "Echo result: hello from bridge"
```

## Full Stack (Docker Compose)

> Requires Docker Compose **v2** (`docker compose version` → v2.x).

```bash
# Start all 12+ services with auth bypass
MCP_DEV_MODE=1 docker compose --profile full up --build -d

# Verify
docker compose --profile full ps     # all rows show "(healthy)"
MCP_DEV_MODE=1 bash scripts/smoke_test.sh
```

| Service | URL | Credentials |
|---------|-----|-------------|
| MCP Gateway | http://localhost:8000/health | — |
| Auth Server | http://localhost:8001/.well-known/oauth-authorization-server | — |
| Jaeger | http://localhost:16686 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Kafka UI | http://localhost:8085 | — |
| Redis Commander | http://localhost:8086 | — |
| MCP Inspector | http://localhost:6274 | — |

### Live Demo

```bash
# Pull the default local model (~400 MB)
ollama pull qwen3:0.6b-q4_K_M

# Seven-phase zero-touch demo (all 4 pipeline layers)
./scripts/demo.sh

# Run a single phase
./scripts/demo.sh 0    # Deterministic Orchestration
./scripts/demo.sh 1    # Privacy-First RAG
./scripts/demo.sh 5    # CrewAI multi-agent scoping
./scripts/demo.sh 6    # DSPy + GEPA optimization
```

> **Linux:** Ollama must listen on all interfaces for the Docker gateway to reach
> it. Start with `OLLAMA_HOST=0.0.0.0 ollama serve`.

## Configuration

Copy `.env.example` to `.env` — both servers load it automatically via `python-dotenv`:

```bash
cp .env.example .env
# Set at minimum: JWT_SECRET (shared key for auth + gateway)
```

Key environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `JWT_SECRET` | *(required for auth)* | Shared HS256 signing key — auth server and gateway must match |
| `MCP_DEV_MODE` | `0` | Set `1` to bypass all auth (dev/demo only) |
| `ORCHESTRATOR_MODE` | `legacy` | `legacy`, `pydantic_ai`, or `langgraph` |
| `REDIS_URL` | *(unset → FakeRedis)* | Real Redis for sessions, KV, checkpoints |
| `KAFKA_BOOTSTRAP_SERVERS` | *(unset → InProcessEventLog)* | Real Kafka for telemetry stream |
| `LLM_PROVIDER` | `ollama` | `openai`, `anthropic`, or `ollama` |
| `OLLAMA_MODEL` | `qwen3:0.6b-q4_K_M` | Default Ollama model |

## External Client Integration

The gateway implements RFC 8414 auto-discovery. Any MCP client connects via:
discover → register → PKCE auth → Bearer JWT.

### IDE Setup (Cursor / Claude Desktop)

```bash
# Generate machine-local .mcp.json from template (run once after cloning)
./setup-mcp.sh
```

The generated `.mcp.json` (gitignored) points at `localhost:8000` with OAuth 2.1
PKCE. Cursor and Claude Desktop perform the auth flow automatically.

A reference `mcp.json.example` is included showing the full tool catalogue and
auth configuration.

### Machine-to-Machine (no browser)

```bash
# Register a client
curl -X POST http://localhost:8001/register \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"my-bridge","client_secret":"s3cr3t","redirect_uri":"http://localhost","scope":"tools:call"}'

# Run the bridge with client_credentials grant
BRIDGE_CLIENT_ID=my-bridge BRIDGE_CLIENT_SECRET=s3cr3t python -m mcp_agent_factory.bridge
```

When only `JWT_SECRET` is set (no auth server), the bridge self-signs a valid
HS256 JWT — no extra process needed for local dev:

```bash
JWT_SECRET=mysecret python -m mcp_agent_factory.gateway.run &
JWT_SECRET=mysecret python -m mcp_agent_factory.bridge
```

### Raw HTTP

```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -m json.tool
```

## Gateway Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/health` | No | Liveness probe |
| `GET` | `/.well-known/oauth-authorization-server` | No | RFC 8414 discovery |
| `POST` | `/mcp` | JWT | JSON-RPC 2.0 tool calls |
| `GET` | `/mcp` | No | SSE channel (Streamable HTTP) |
| `POST` | `/sampling` | JWT | `sampling/createMessage` |
| `GET` | `/sse/v1/events` | No | SSE event stream |
| `POST` | `/sse/v1/messages` | JWT | Publish to SSE bus |

Auth server (`:8001`): `POST /register`, `GET /authorize`, `POST /token`.

## Tests

```bash
pytest tests/ -v    # 460+ tests (integration tests skip without Docker)

# Integration tests (requires full Docker stack)
REDIS_URL=redis://localhost:6379 pytest -m integration -v
```

## Evaluation

The project includes an LLM evaluation harness that measures output quality,
not just code correctness. See [evals/README.md](evals/README.md) for details.

**Current baseline** (55 examples, Wilson 95% CI):

| Dataset | Examples | Pass Rate | 95% CI |
|---------|----------|-----------|--------|
| RAG Q&A | 25 | 100.0% | [86.7%, 100.0%] |
| Extraction | 15 | 100.0% | [78.2%, 100.0%] |
| Refusal | 15 | 100.0% | [78.2%, 100.0%] |
| **Overall** | **55** | **100.0%** | **[93.5%, 100.0%]** |

Minimum detectable effect at n=55: **26.4%** — changes smaller than this are
indistinguishable from noise.

Judge–human agreement on 20-example calibration subset: **65.0%** accuracy
(heuristic groundedness; LLM judge calibration pending live API keys).

```bash
# Run all evaluations
python -m evals.runner --all

# Compare two runs
python -m evals.compare baseline <sha>
```

## Project Layout

```
src/mcp_agent_factory/
├── server.py                    # STDIO MCP server
├── server_http.py               # FastAPI HTTP MCP server
├── server_http_secured.py       # OAuth-secured variant
├── orchestrator.py              # DeterministicOrchestrator + MCP client
├── graph_orchestrator.py        # LangGraph cyclic FSM
├── structured_agent.py          # PydanticAI structured agent
├── evaluator.py                 # Critic-Actor evaluator
├── crew.py                      # Layer 3: MCPCrew + ScopedAgent
├── optimizer.py                 # Layer 4: DSPy + GEPA optimizer
├── agents/                      # Multi-agent pipeline (Analyst, Writer, Librarian)
├── auth/                        # OAuth 2.1 server (PKCE S256)
├── bridge/                      # MCPGatewayClient + OAuth middleware
├── gateway/                     # API gateway, router, PII gate, pruner
├── knowledge/                   # RAG: vector store, embedder, ingestion
├── streams/                     # StreamWorker, CircuitBreaker, Redlock, EventLog
├── session/                     # Redis session manager
├── kv/                          # Topic-namespaced KV store
├── economics/                   # Utility scoring + sealed-bid auction
├── messaging/                   # MessageBus + SSE routers
└── config/                      # Privacy config + egress guard

evals/
├── datasets/                    # 55 hand-curated JSONL examples
├── metrics/                     # Groundedness, retrieval, schema, Wilson CI
├── judge/                       # LLM-as-judge + calibration + KNOWN_BIASES.md
├── runner.py                    # python -m evals.runner --all
├── compare.py                   # python -m evals.compare <sha-a> <sha-b>
└── results/                     # JSON reports tagged by git SHA

docs/
├── architecture.md              # Layered design, request lifecycle, span chain
├── milestones.md                # Development history (M001–M012 + features)
├── demo-walkthrough.md          # Live demo guide
└── security_audit.md            # Security review

scripts/
├── demo.sh                      # Seven-phase zero-touch demo
├── demo_analyst.py              # Python analyst demo
├── smoke_test.sh                # Stack health verification
└── publish_traces.py            # Kafka trace publisher
```

## Security Notes

- JWT tokens use HS256. Both auth server and gateway must share the same `JWT_SECRET`.
  Rotate to RS256 + JWKS for multi-service deployments.
- PKCE S256 enforced on all authorization code exchanges; codes are single-use.
- Audience binding (`aud: mcp-server`) prevents confused-deputy attacks.
- `PIIGate` scrubs email, API key, private IP, and JWT patterns from request bodies.
- RAG vector store is namespace-isolated by `owner_id` (bound to JWT `sub`).
- `PrivacyConfig.assert_no_egress()` guards against accidental outbound calls.
- `DistributedLock` uses a UUID token to prevent cross-holder lock release.
- See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Production Checklist

| Item | Notes |
|------|-------|
| `JWT_SECRET` set on both processes | Same secret required |
| `MCP_DEV_MODE` unset or `0` | Never `1` in production |
| Real Redis (`REDIS_URL`) | FakeRedis doesn't survive restarts |
| TLS termination | Caddy or nginx in front; JWTs must not travel over plain HTTP |
| Token rotation | HS256 → RS256 + JWKS for multi-service deployments |
| Port exposure | Auth server (`:8001`) should not be public-facing |

## Documentation

- [Architecture](docs/architecture.md) — layered design, request lifecycle, OTel span chain
- [Evaluation](evals/README.md) — LLM evaluation harness, metrics, judge calibration
- [Milestone History](docs/milestones.md) — development log from M001 through v1.0.0
- [Demo Walkthrough](docs/demo-walkthrough.md) — live demo guide
- [Security Audit](docs/security_audit.md) — security review

## License

Licensed under the [Apache License, Version 2.0](LICENSE).

© 2026 Luca Flammia — Licensed under the Apache License, Version 2.0
