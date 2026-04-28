# M009: Model Agnosticism & Token Economy

**Gathered:** 2026-04-27
**Status:** Ready for planning

## Project Description

Eliminate vendor lock-in and optimize operational costs by implementing a model-agnostic abstraction layer and a "context-first" filtering strategy. Data stays secure (Local-First) and every token sent to an LLM is medically necessary for the task at hand.

## Why This Milestone

The existing `adapters.py` handles schema translation only — no live provider dispatch exists. M009 wires a real dispatch layer, a PII gate, a context pruner, async caching, and TLS. The result is that the ThinkPad functions as a self-sufficient AI workstation: cloud providers are used opportunistically, local Ollama is the fallback, and sensitive data never leaves the local network.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Send a tool call through the gateway and have it routed to OpenAI, Anthropic, or Ollama based on environment config — no code change needed to switch providers
- Observe automatic fallback: when OpenAI returns 429, the system transparently retries via local Ollama and records both events in the EventLog
- Trust that fields not in `MCP_ALLOWED_FIELDS` are scrubbed before leaving the local network — JWT secrets and file paths never reach cloud APIs
- Query knowledge chunks knowing only semantically relevant chunks (by cosine similarity) are passed to the LLM
- See per-user token spend in the EventLog (`token.usage` events with `model`, `input_tokens`, `output_tokens`, `cost_usd`)
- Reach the gateway over HTTPS (`https://localhost`) via Caddy reverse proxy

### Entry point / environment

- Entry point: `docker-compose up` → gateway at `https://localhost` (Caddy → `:8000`)
- Environment: local dev on T480, docker-compose stack
- Live dependencies: Redis, Caddy, Ollama (`llama3.2:1b` or similar small model)

## Completion Class

- Contract complete means: unit tests for `UnifiedRouter`, `PIIGate`, `ContextPruner`, `AsyncIdempotencyGuard` pass with stubs/fakes
- Integration complete means: `UnifiedRouter` → `EventLog` → Redis wired and verified with `fakeredis` / real docker Redis
- Operational complete means: `docker-compose up` brings Caddy + gateway; live Ollama fallback confirmed with real subprocess call recorded in `EventLog`

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Simulated OpenAI 429 → Ollama completion → `token.usage` event in EventLog (live subprocess, not stub)
- Request containing an email address is blocked at `ValidationGate` with `"Request blocked by PII gate"` — no field detail revealed
- HTTPS `curl https://localhost/health` returns 200 with the docker-compose stack running

## Scope

### In Scope

- `UnifiedRouter` with `OpenAIHandler`, `AnthropicHandler`, `OllamaHandler` — replaces `_dispatch` in `gateway/service_layer.py`
- `MCPRequest` internal protocol object
- `ProviderError(retryable: bool)` exception hierarchy
- Automatic fallback: retriable cloud failure → Ollama
- `ValidationGate` extension: negative-permissions PII scrubbing with `MCP_ALLOWED_FIELDS` env var
- Regex PII patterns: email, API key signatures, private IPs, JWT-shaped strings
- `ContextPruner` utility: cosine similarity filtering before handler call; empty-context fallthrough allowed
- `AsyncIdempotencyGuard`: async-native Redis prompt cache; fire-and-forget write failures
- `token.usage` EventLog event type with `model`, `input_tokens`, `output_tokens`, `cost_usd`, `sub`
- Caddy service in `docker-compose.yml` proxying `:443 → gateway:8000`
- Unit + integration + live Ollama acceptance tests

### Out of Scope / Non-Goals

- Gemini handler (live dispatch — schema translation already exists in `adapters.py`)
- Per-request model selection by calling agent
- Multi-tenant cost dashboards or aggregated spend reporting
- PII allow-list management UI or admin endpoint
- Multi-node or production TLS cert management (Let's Encrypt, cert rotation)

## Architectural Decisions

### Router replaces `_dispatch` — single central dispatch point

**Decision:** `InternalServiceLayer.handle()` calls `UnifiedRouter`; `_dispatch` is removed.

**Rationale:** Keeping `_dispatch` alongside a router creates a split-brain architecture. All circuit-breaking and fallback logic lives in one place — the Service Layer asks for a result and the Router handles the how.

**Alternatives Considered:**
- Keep `_dispatch` and add a side-path router — creates two code paths that can diverge; rejected

### `MCPRequest` as the router's internal protocol

**Decision:** Single `MCPRequest(tool_name, args, claims)` object; all handlers consume it.

**Rationale:** The `InternalServiceLayer` already receives exactly these three inputs. A typed protocol object makes the boundary explicit and testable.

**Alternatives Considered:**
- Pass `(tool_name, args, claims)` as positional args to router — no type safety, harder to extend; rejected

### Negative-permissions PII gate via `MCP_ALLOWED_FIELDS` env var

**Decision:** `MCP_ALLOWED_FIELDS=query,task_id,limit` (default). Everything not in the list is scrubbed. Managed via env var, not code or YAML.

**Rationale:** Static code is too rigid to tune during debugging. A YAML file is another file to track on disk. Env var matches the existing `.env` infrastructure on the T480 and allows per-deployment tuning without code changes.

**Alternatives Considered:**
- Static allow-list in code — inflexible for debugging; rejected
- YAML config file — extra file management; rejected

### Cosine similarity as the context pruning signal

**Decision:** `ContextPruner` embeds the query via `StubEmbedder`/`LocalEmbedder`, computes cosine similarity against chunk embeddings, drops below-threshold chunks.

**Rationale:** `task_name` as signal is too coarse; agent-tagged topics add LLM overhead. `InMemoryVectorStore.search()` already returns numpy arrays — cosine similarity is free.

**Alternatives Considered:**
- `task_name` field as topic filter — too coarse; "Research" covers anything; rejected
- Agent-tagged context topics — extra work for the LLM at call time; rejected

### `AsyncIdempotencyGuard` — new async-native class

**Decision:** Write a new `AsyncIdempotencyGuard` using `redis.asyncio`; do not modify existing sync `IdempotencyGuard`.

**Rationale:** Existing `IdempotencyGuard` uses sync Redis; the gateway is fully async. Wrapping with `asyncio.to_thread` introduces thread overhead for a hot path. A clean async-native class is the right boundary.

**Alternatives Considered:**
- `asyncio.to_thread` wrapper around existing guard — works but adds thread-pool overhead on every cache check; rejected

### `token.usage` events on EventLog (fire-and-forget)

**Decision:** Every handler call appends a `token.usage` event. Write failures are logged but non-fatal — never block the primary response.

**Rationale:** Caching and cost tracking are off the critical path. A user should never see a 500 because a Redis write failed. `EventLog.append()` is already async — natural fit.

### TLS via Caddy in docker-compose (not uvicorn ssl)

**Decision:** `caddy` service in `docker-compose.yml` proxies `:443 → gateway:8000`. Gateway listens plain HTTP internally.

**Rationale:** Cleanest ops boundary. No uvicorn ssl complexity. If Caddy is down, the service is down — no app-level fallback is appropriate.

**Alternatives Considered:**
- `uvicorn --ssl-certfile/keyfile` — mixes TLS into the application process; harder to rotate certs; rejected
- Enforce-only in FastAPI — still requires TLS termination somewhere; rejected

## Error Handling Strategy

- **Retriable cloud failure** (429, 5xx): `ProviderError(retryable=True)` → router retries once → falls back to `OllamaHandler` → if Ollama also fails, `ProviderError(retryable=False)` propagates as `isError:true` MCP response.
- **Non-retriable cloud failure** (400, 401): `ProviderError(retryable=False)` propagates immediately as `isError:true` — no fallback.
- **PII gate block**: `isError:true` with message `"Request blocked by PII gate"` — no detail about which fields were scrubbed.
- **All chunks pruned**: Proceed with empty context. LLM answers from weights alone.
- **Cache write failure**: Log the error, continue with live LLM call. Never surface to caller.
- **`token.usage` EventLog write failure**: Fire-and-forget. Never fail the primary response.
- **Caddy/TLS failure**: Gateway is unreachable. No application-level fallback.

## Risks and Unknowns

- Ollama API compatibility with `httpx` async — verify endpoint shape before implementing `OllamaHandler`
- `MCP_ALLOWED_FIELDS` default may be too narrow or too broad for real workloads — calibrate during integration testing
- Cosine similarity threshold for pruning needs empirical tuning — too aggressive prunes useful context, too loose lets noise through
- `AsyncIdempotencyGuard` hash stability — prompt hash must be deterministic across requests (JSON key order, encoding)

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/gateway/service_layer.py` — `InternalServiceLayer` + `_dispatch`; this is what the router replaces
- `src/mcp_agent_factory/gateway/validation.py` — `ValidationGate`; PII gate extends this
- `src/mcp_agent_factory/streams/idempotency.py` — sync `IdempotencyGuard`; async version mirrors its interface
- `src/mcp_agent_factory/streams/eventlog.py` — `EventLog.append()` async; `token.usage` event appended here
- `src/mcp_agent_factory/adapters.py` — schema translation (OpenAI/Anthropic/Gemini formats); router handlers use these
- `src/mcp_agent_factory/knowledge/embedder.py` — `Embedder` protocol + `StubEmbedder`; `ContextPruner` uses this
- `src/mcp_agent_factory/knowledge/vector_store.py` — `InMemoryVectorStore.search()` returns numpy arrays; similarity scores available
- `docker-compose.yml` — existing stack (Redis, Kafka, Redlock nodes); Caddy service appended here

## Relevant Requirements

- R033 — Unified provider router
- R034 — Automatic fallback to local Ollama
- R035 — Gateway-level PII scrubbing with negative-permissions model
- R036 — Context pruning via cosine similarity
- R037 — Async prompt response caching
- R038 — `token.usage` EventLog event with per-user cost tracking
- R039 — TLS via Caddy reverse proxy
- R040 — Live Ollama fallback verified end-to-end

## Testing Requirements

- Unit: `ContextPruner` (similarity filtering, empty-context fallthrough), `ValidationGate` PII extension (block + pass cases), `UnifiedRouter` fallback logic (stubbed handlers), `AsyncIdempotencyGuard` (cache hit/miss/write-failure)
- Integration: `UnifiedRouter` → `EventLog` → Redis with `fakeredis` or docker Redis; `token.usage` events readable per `sub`
- Live acceptance: real Ollama subprocess call following simulated OpenAI 429; `token.usage` event present in EventLog

## Acceptance Criteria

- **S01**: `UnifiedRouter.dispatch(MCPRequest)` routes to correct handler based on env config; simulated 429 triggers Ollama fallback; both events in EventLog
- **S02**: Request with email in `args` → blocked at `ValidationGate` with generic message; request with only `query` passes through; `MCP_ALLOWED_FIELDS` override works
- **S03**: Vector chunk with cosine similarity below threshold is dropped; on-topic chunk passes; empty-context request proceeds without error
- **S04**: Identical prompt → cache hit in under 1ms; cache miss → live call; `token.usage` events in EventLog with correct `sub`
- **S05**: `docker-compose up` → `https://localhost` reachable; live OpenAI 429 fallback chain confirmed with `token.usage` in EventLog

## Open Questions

- Ollama API base URL: `http://localhost:11434` — confirm this is the default on T480 before coding `OllamaHandler`
- Cosine similarity threshold: start at 0.3; tune during S03 integration testing
