# Architecture

## Layered Overview

MCP Agent Factory is organised in four execution layers, a shared infrastructure
tier, and a standards-compliant security boundary.

```
┌──────────────────────────────────────────────────────────────┐
│                     External Clients                         │
│   Cursor / Claude Desktop / MCPGatewayClient + mcp.json      │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS (Caddy TLS termination → :8000)
                         │ Bearer JWT (OAuth 2.1 / PKCE S256)
┌────────────────────────▼─────────────────────────────────────┐
│                 MCP API Gateway (FastAPI :8000)               │
│  POST /mcp (Streamable HTTP)  POST /sampling   GET /health    │
│  GET  /sse  POST /sse/messages (MCP legacy SSE transport)     │
│  GET  /sse/v1/events          POST /sse/v1/messages           │
│  PIIGate · ValidationGate · InternalServiceLayer             │
│  UnifiedRouter → OpenAI / Anthropic / Ollama (auto-fallback) │
│  ContextPruner (cosine) · AsyncIdempotencyGuard (SHA-256)    │
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
│      Real Infrastructure Layer                               │
│  docker-compose: Kafka + Zookeeper + 4 Redis nodes           │
│  RedlockClient — 3-node quorum acquire / release             │
│  Multi-process StreamWorker — horizontal scaling + PEL rec.  │
└──────┬──────────────────────────────────────────────────────┘
       │
┌──────▼─────────────────────────────────────────────────────┐
│       Redis Storage Layer (fakeredis / real)                │
│  RedisSessionManager — cross-agent session handoffs         │
│  RedisKVStore — topic-namespaced key-value store            │
└────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│              OAuth 2.1 Auth Server (:8001)                   │
│   POST /register   GET /authorize   POST /token              │
│   PKCE S256 only · one-time codes · audience-bound JWTs      │
└──────────────────────────────────────────────────────────────┘
```

## 4-Layer Execution Pipeline

```text
[MCP Resources / Tools]
│
▼
┌────────────────────────────────────────────────────────────────────────┐
│                        MCP-AGENT-FACTORY PIPELINE                      │
│                                                                        │
│  Layer 1: Foundations (PydanticAI)  ──► Validated I/O                   │
│           structured_agent.py · orchestrator.py                        │
│           Schema-gated tool calls · Pydantic I/O contracts             │
│                                                                        │
│  Layer 2: Production (LangGraph)    ──► State Machines                 │
│           graph_orchestrator.py · evaluator.py                         │
│           Deterministic plan→execute · Critic-Actor loop · HITL        │
│                                                                        │
│  Layer 3: Orchestration (CrewAI)    ──► Multi-Agent Workflows          │
│           crew.py                                                      │
│           Role-based MCP tool scoping · PermissionError boundary       │
│           use_langgraph=True → delegates to Layer 2 FSM per agent      │
│                                                                        │
│  Layer 4: Optimization (DSPy+GEPA)  ──► Offline Tuning                │
│           optimizer.py                                                 │
│           Kafka trace ingestion · text-gradient mutation               │
│           Hot-reloadable JSON skill assets                             │
└────────────────────────────────────────────────────────────────────────┘
```

## Request Lifecycle

A typical `POST /mcp` request flows through the following stages:

1. **TLS termination** — Caddy terminates HTTPS and forwards to the gateway on `:8000`.
2. **Authentication** — `make_verify_token()` extracts the Bearer JWT, verifies signature and audience (`aud: mcp-server`). In dev mode (`MCP_DEV_MODE=1`), auth is bypassed. The `/mcp` endpoint uses `optional=True` — a missing or invalid token does not return HTTP 401; the request reaches the handler where tool scoping (and destructive-tool blocking) is applied based on the decoded token claims. Hard auth rejection (`optional=False`) is reserved for endpoints that must never serve unauthenticated callers.
3. **Validation gate** — `ValidationGate` rejects malformed JSON-RPC payloads. `PIIGate` scrubs PII patterns (email, API keys, private IPs, JWTs) from the request body.
4. **Routing** — `InternalServiceLayer` dispatches based on the JSON-RPC `method`:
   - `tools/list` → returns the registered tool catalogue
   - `tools/call` → invokes the named tool via `call_tool()`
   - `agents/analyze` → runs the full analyst pipeline with OTel child spans
5. **LLM dispatch** — `UnifiedRouter.route()` selects a provider (OpenAI, Anthropic, or Ollama) based on request headers or environment config. On 429 or provider error, falls back to Ollama automatically.
6. **Context pruning** — `ContextPruner.prune()` filters irrelevant RAG chunks by cosine similarity before sending to the LLM.
7. **Idempotency** — `AsyncIdempotencyGuard` caches responses by SHA-256 hash; identical prompts return cached results without re-invoking the LLM.
8. **Telemetry** — `token.usage` events are published to the EventLog (InProcess or Kafka) with model, cost, and token counts. OTel spans are exported to Jaeger via the OTLP/gRPC collector.

## OTel Span Chain

Every `agents/analyze` call produces a parent span with four child spans:

```
gateway → otel-collector:4317 (OTLP/gRPC)
              ├─ spanmetrics connector → prometheus exporter :8889
              └─ otlp/jaeger exporter → jaeger:4317
prometheus scrapes otel-collector:8889
jaeger queries prometheus for SPM data

agents/analyze (parent)
├── pdf_extract     — document ingestion
├── prune           — cosine similarity filtering
├── pii_scrub       — PII pattern removal
└── llm_route       — LLM provider dispatch (with token count attributes)
```

## LangGraph Finite State Machine (Layer 2)

The core of Layer 2 is a cyclic finite state machine in `graph_orchestrator.py`
using LangGraph's `StateGraph`:

```text
              ┌──────────────────────────────────────────┐
              │          LangGraph StateGraph             │
              │                                          │
  task ──►  VALIDATE ──► PLAN ──► EXECUTE ──► EVALUATE   │
              ▲                                  │       │
              │          retry (score < 0.7)      │       │
              └──────────────────────────────────┘       │
                                                  │       │
                                    pass ──► DONE         │
                                    fail ──► FAILED       │
                                    HITL ──► interrupt()   │
              └──────────────────────────────────────────┘
```

| Phase | What happens |
|-------|-------------|
| **VALIDATE** | Checks task is non-empty, tools are available; rejects malformed input before any LLM call |
| **PLAN** | LLM generates an `ExecutionPlan` (Pydantic-validated); structural violations block execution |
| **EXECUTE** | Runs each plan step via the injected `call_tool_fn`; destructive tools trigger `interrupt()` for HITL approval |
| **EVALUATE** | `CriticActorEvaluator` scores the output; score < 0.7 routes back to PLAN; score = 0.0 triggers HITL interrupt |
| **DONE** | Final result emitted; `AsyncRedisSaver` persists the checkpoint |
| **FAILED** | `MAX_ITERATIONS` (default 15) exceeded; graph halts with structured error |

Key properties:

- **Bounded depth** — `MAX_ITERATIONS=15` prevents infinite retry loops.
- **Transactional checkpointing** — `AsyncRedisSaver` persists `GraphState` at every phase transition, enabling crash recovery and cross-process HITL resume.
- **Decoupled I/O** — `GraphOrchestrator.run(task, tools, call_tool_fn, thread_id)` is transport-agnostic.
- **Conditional edges** — LangGraph's `add_conditional_edges` routes EVALUATE output to DONE, FAILED, or back to PLAN based on score and iteration count.

## Human-in-the-Loop (HITL)

1. **Destructive-tool detection** — `execute_node` scans the plan for tools matching destructive patterns (`write`, `delete`, `drop`, `deploy`, …) and calls `interrupt()`.
2. **LangGraph `interrupt()`** — serialises `GraphState` to Redis via `AsyncRedisSaver`, pauses the graph.
3. **External approval** — operator inspects the state (e.g. via Redis Commander at `:8086`) and resumes with `compiled.ainvoke(None, config)`.
4. **Critical-failure escalation** — `evaluate_node` also interrupts on score `0.0` (absolute failure requiring human context).

## Critic-Actor Pattern

`CriticActorEvaluator` (in `evaluator.py`) enforces separation between output
production (Actor) and output evaluation (Critic):

- The `EvaluationContract` is sealed at task creation time, before the actor runs.
- The critic evaluates against `input_constraints` using deterministic heuristics — no shared state with the actor.
- For semantic correctness, the critic can use an independent LLM judge with a *different* provider/model.
- The critic defaults to `needs_revision` — explicit evidence is required to pass.

## DeterministicOrchestrator

Adds a strict two-phase gate between the LLM and execution:

1. **Planning phase** — LLM generates a raw plan dict (probabilistic, creative).
2. **Validation gate** — `OrchestratorPlan` (Pydantic model) validates structure. Malformed plans raise `ValidationError` and block execution.
3. **Execution phase** — accepts only validated `OrchestratorPlan` instances. Every field is typed, every constraint satisfied.

## Multi-Agent Crew (Layer 3)

`MCPCrew` coordinates specialised `ScopedAgent` personas with per-role tool filtering:

| Role | Allowed tool patterns |
|------|----------------------|
| `analyst` | `read`, `search`, `fetch`, `list`, `get`, `describe` |
| `writer` | `write`, `create`, `update`, `format`, `publish`, `send` |
| `db_agent` | `sql`, `query`, `select`, `insert`, `upsert`, `delete` |
| `librarian` | `embed`, `ingest`, `index`, `retrieve`, `vector` |
| `orchestrator` | *(all tools)* |

`build_scoped_call_fn` wraps the MCP call function with a hard `PermissionError`
boundary — agents cannot escalate beyond their assigned scope.

## Offline Prompt Optimization (Layer 4)

```
Kafka topic (mcp-traces)
   │ AIOKafkaConsumer
   ▼
TraceRecord list (filtered to failure_rate > 10%)
   │
   ▼ per (role, phase) pair
DSPy BootstrapFewShot
   │ compiles few-shot examples from passing traces
   ▼
GEPAEvolver (genetic mutation)
   │ scores candidates by keyword coverage
   ▼
SkillAsset → SkillCompiler.compile_all()
   ├── {skill_id}.json     ← one file per (role, phase)
   └── index.json          ← manifest for runtime hot-reload
```

The offline boundary is enforced: DSPy compilation and GEPA evolution never run
in the request path. Results are written as hot-reloadable JSON skill assets.

## Async Fleet Runtime

The async fleet runtime runs alongside the synchronous pipeline without changing any existing routes.

```
Client
  │
  ├── POST /mcp/tools/call    → synchronous pipeline (unchanged)
  │
  └── POST /mcp/jobs          → FleetWorker (Redis Stream: mcp-fleet-jobs)
      POST /mcp/jobs/batch           │
      GET  /mcp/jobs/{job_id}        ▼
      GET  /mcp/jobs/batch/{id}
                               Worker Pool (FLEET_CONCURRENCY workers, default 4)
                                     │
                                     ▼
                               4-layer pipeline (unchanged)
                               Foundations → Production → Orchestration → Optimization
                                     │
                               Provider registry (adapters.py)
                               ├── Anthropic
                               ├── OpenAI
                               ├── Ollama
                               └── Bedrock  ← new (boto3, IAM auth)
```

**Job lifecycle:**

```
POST /mcp/jobs  →  job stored in Redis (status: pending)
                →  task_id pushed to Stream mcp-fleet-jobs
                      │
                FleetWorker.claim_job() via XREADGROUP
                      │
                status: running  →  _execute_job()  →  status: done | failed
                      │
GET /mcp/jobs/{id}  ←  result read from Redis key fleet:job:{id}
```

**Batch endpoint:**

`POST /mcp/jobs/batch` accepts up to N tasks, submits each as an independent job, and returns a `batch_id` plus all `job_ids`. `GET /mcp/jobs/batch/{batch_id}` aggregates statuses in one round-trip. A single failing job does not affect others.

**Jaeger spans:** each job emits a `fleet.job` parent span with `fleet.job_id`, `fleet.method`, and `fleet.status` attributes. Sub-spans are inherited from the pipeline layers.

## Hermes Agent → Gateway Integration (INT-01 A–D)

Validated 2026-11-08 against gateway at `http://localhost:8000/mcp` using
`hermes mcp test`, `hermes mcp call`, and direct HTTP.  Model: `llama3.2:3b`
(tool-call-incapable; connectivity and auth layers exercised via CLI).

### Component A — Connectivity

`hermes mcp test mcp-gateway` connects in ~5.8 s and discovers **6 tools**:
`echo`, `add`, `query_knowledge_base`, `kv/add_phrase`, `kv/check_affinity`,
`orchestrate`.  `echo` round-trip returns expected result.

### Component B — Auth Modes

Three auth modes are configured in `examples/hermes-mcp-server.json`:

| Mode | Grant | Result |
|------|-------|--------|
| 1 — dev bypass | `MCP_DEV_MODE=1`, no token | ✅ All tools reachable |
| 2 — machine-to-machine | `client_credentials` | ✅ Token issued; expired token blocked on `tools/call` with `-32001`; wrong `aud` → 401 |
| 3 — PKCE (browser) | `authorization_code` | ⚠️ Server endpoints functional; Hermes CLI has no browser flow — not exercisable from CLI |

**RFC deviations noted** (documented in `examples/hermes-mcp-server.json`):
- `/register` requires caller-supplied `client_id`/`client_secret` (not RFC 7591 auto-assign).
- `/token` expects JSON body, not `application/x-www-form-urlencoded` (RFC 6749 §4.4).

### Component C — Tool Scoping

Role-based scoping is enforced server-side in `gateway/app.py` via
`_TOOL_REQUIRED_SCOPE` (line ~76).  Rules verified end-to-end:

| Scenario | Tools visible | Expected |
|----------|--------------|---------|
| Token with `scope: tools:call` | 5 (orchestrate hidden) | ✅ |
| Token with empty `grants` | 0 | ✅ |
| Token without `tools:call` scope | `tools/list` returns error | ✅ |

The gateway is **authoritative** — scope enforcement happens before the tool
catalogue is returned, not in the client.

### Component D — Destructive Tool Blocking

`orchestrate` is tagged destructive.  Direct `tools/call orchestrate` with a
valid admin token returns error `-32003` (destructive tools blocked) and is
**never silently executed**.

**Gap:** `orchestrate` is blocked but not yet routed through the LangGraph
`interrupt()`-based approval loop.  A follow-up issue is needed to wire the
block into the HITL resume flow (see [Human-in-the-Loop](#human-in-the-loop-hitl)).

### Regression Tests (INT-01 A–D)

11 pytest tests in `tests/test_int01_gateway_hermes.py` lock the validated
invariants against future regressions.  All run in-process against
`gateway_app` (no live Hermes, Redis, or Postgres required):

| Test | Component | Verifies |
|------|-----------|---------|
| `test_tools_list_dev_mode` | A | Dev mode returns ≥ 1 tool |
| `test_echo_call_dev_mode` | A | `echo` returns expected value |
| `test_missing_token_rejected` | B | No `Authorization` → `-32001` |
| `test_expired_token_rejected` | B | Expired JWT → error code |
| `test_wrong_aud_rejected` | B | Wrong `aud` → 401 |
| `test_scoped_token_hides_tools` | C | No `tools:call` scope → 403 |
| `test_full_scope_shows_tools` | C | `tools:call` scope → ≥ 5 tools |
| `test_orchestrate_blocked_without_approval` | D | `orchestrate` → `-32003`, never executed |

Additional edge-case tests cover empty-grant tokens, missing scopes on
`tools/call`, and the interaction between scope middleware and the tool
catalogue handler.

## Infrastructure Stack

`docker compose --profile full up --build` starts 12 services:

| Service | Port | Purpose |
|---------|------|---------|
| Gateway | 8000 | MCP API gateway (FastAPI) |
| Auth Server | 8001 | OAuth 2.1 (PKCE S256) |
| Redis | 6379 | Session, KV, idempotency, checkpoints |
| Redis nodes ×3 | 6381–6383 | Redlock quorum |
| Kafka | 29092 | Telemetry stream, trace ingestion |
| Zookeeper | 2181 | Kafka coordination |
| Jaeger | 16686 | Distributed trace visualisation |
| OTel Collector | 4317 | OTLP/gRPC receiver + spanmetrics |
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3000 | Dashboards (admin/admin) |
| Kafka UI | 8085 | Topic/consumer inspection |
| Redis Commander | 8086 | Redis key browser |
| MCP Inspector | 6274 | MCP protocol debugger |
| Caddy | 443 | TLS termination |
