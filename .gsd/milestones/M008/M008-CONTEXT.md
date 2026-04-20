# M008: Production-Grade Infrastructure Wiring

**Gathered:** 2026-04-20
**Status:** Ready for planning

## Project Description

Systematic wiring pass that replaces every in-memory/fake default with a real, env-driven production implementation. The infrastructure already exists in docker-compose.yml. The protocols already exist (EventLog, VectorStore, Embedder). What's missing is the env-driven factory logic that selects the real implementation when infrastructure is available, and falls back to fakes when it isn't (for tests).

## Why This Milestone

The codebase built up all the right abstractions across M001–M007 but the application-level defaults still use fake/in-memory implementations:
- `gateway/app.py` imports and instantiates `fakeredis.aioredis.FakeRedis()` at module level — not just in tests
- `auth/server.py` uses Python dicts `_clients` and `_codes` (the comment literally says "replace with Redis in production")
- `InternalServiceLayer` has no EventLog — tool calls are observable only via ephemeral bus events
- `redis>=5` is an optional `[infra]` extra, not a core dependency

The system cannot be deployed to production in this state. M008 fixes all of it without adding new features.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Set `REDIS_URL=redis://localhost:6379` and start the gateway — session state is real and persists across restarts
- Register an OAuth client, restart the auth server, and the client registration survives
- Set `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` and call a tool — the call produces a durable Kafka event
- Run `pytest tests/` with no docker stack running and all 32 existing tests pass (FakeRedis fallback)
- Run `pytest -m integration` with docker-compose up and all integration tests pass

### Entry point / environment

- Entry point: `python -m mcp_agent_factory.gateway.run`
- Environment: local docker-compose (`docker-compose up`)
- Live dependencies: Redis (`:6379`), Kafka (`:9092`), 3 Redlock nodes (`:6381–6383`)

## Completion Class

- Contract complete means: all module-level FakeRedis() and in-memory dict state removed from production paths; env-driven factories in place; `pytest tests/` passes
- Integration complete means: `pytest -m integration` passes against running docker-compose stack
- Operational complete means: `python -m mcp_agent_factory.gateway.run` boots without error when `REDIS_URL` and `KAFKA_BOOTSTRAP_SERVERS` are set

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Gateway starts against real Redis and `/health` returns ok
- OAuth PKCE flow completes after auth server restart (Redis-backed state survives)
- A `tools/call` request produces a Kafka event visible via `kafka-console-consumer`
- `pytest tests/` (no docker) all pass — FakeRedis fallback untouched
- `pytest -m integration` all pass — real infra wired correctly

## Architectural Decisions

### Env-driven factory pattern with FakeRedis fallback

**Decision:** When `REDIS_URL` is set, instantiate `redis.asyncio.from_url(REDIS_URL)`. When unset, instantiate `fakeredis.aioredis.FakeRedis()`. Same pattern for Kafka: `KAFKA_BOOTSTRAP_SERVERS` → `KafkaEventLog`, else `InProcessEventLog`.

**Rationale:** This pattern is already established by `MCP_DEV_MODE` and `session/manager.py`. Extending it consistently means zero test changes — existing tests run with no env vars set and get the fake/in-process fallback automatically.

**Alternatives Considered:**
- `set_redis_client()` injection helper — requires all tests to call setup/teardown; more fragile
- Real Redis required for all tests — breaks test isolation, requires docker for unit tests

### VectorStore and Embedder out of scope

**Decision:** `InMemoryVectorStore` and `StubEmbedder` remain as-is for M008.

**Rationale:** No persistent VectorStore implementation exists yet; building one is a separate feature. The stub embedder produces wrong vectors but consistent ones — functionally correct for the current use case. Out of scope per user direction.

### aiokafka stays as optional extra

**Decision:** `aiokafka` remains in `[project.optional-dependencies].infra`; `redis>=5` is promoted to core.

**Rationale:** Kafka is not required for deployment — the `InProcessEventLog` fallback is production-acceptable for single-process deployments. Redis is required for session management and OAuth state persistence, so it must be a core dep.

### MessageBus stays in-process

**Decision:** `asyncio.Queue`-based `MessageBus` is not replaced with Redis Pub/Sub in M008.

**Rationale:** Cross-process fan-out is out of scope per user direction. Single-process assumption holds for this milestone.

## Error Handling Strategy

All env-driven factory switches use the existing exception-on-missing pattern. If `REDIS_URL` is set but Redis is unreachable, `redis.asyncio` raises `ConnectionError` at startup (via the lifespan hook) — fail fast, never silently fall back to FakeRedis when a real Redis was intended. The FakeRedis fallback only triggers when `REDIS_URL` is absent, not when it's set but broken.

## Risks and Unknowns

- Auth server Redis TTL semantics — authorization codes need short TTL (minutes); client registrations need long/no TTL. Redis `EXPIRE` is straightforward but the right TTL values need to be chosen.
- EventLog wiring point — `InternalServiceLayer.handle()` is the natural place but it's not currently async-aware for EventLog append. `KafkaEventLog.append()` is `async`; `InProcessEventLog.append()` is `async`. The service layer is already `async def`, so this should be clean.
- Existing integration tests (M007) already use real Redis/Kafka — M008 integration tests extend that pattern, not replace it.

## Existing Codebase / Prior Art

- `src/mcp_agent_factory/gateway/app.py:59` — `_redis_client = aioredis.FakeRedis()` — the primary replacement target
- `src/mcp_agent_factory/auth/server.py:65–66` — `_clients`, `_codes` dict stores — replace with Redis hashes
- `src/mcp_agent_factory/streams/kafka_adapter.py` — `KafkaEventLog` already implemented, just not wired
- `src/mcp_agent_factory/streams/eventlog.py` — `InProcessEventLog` is the fallback
- `src/mcp_agent_factory/gateway/service_layer.py` — `InternalServiceLayer.handle()` is where EventLog append goes
- `src/mcp_agent_factory/session/manager.py:12–13` — already shows the FakeRedis import pattern; the factory switch goes at module init time instead
- `docker-compose.yml` — Redis (`:6379`), Kafka (`:9092`), Redlock nodes (`:6381–6383`) all defined
- `tests/conftest.py` — existing injection helpers (`set_vector_store`, `set_embedder`); no new helpers needed

## Relevant Requirements

- R027 — Env-driven Redis client (this milestone's primary deliverable)
- R028 — OAuth state persistence (S02)
- R029 — Durable EventLog wiring (S03)
- R030 — `redis>=5` core dep (S01)
- R031 — Integration proof (S04)

## Scope

### In Scope

- Replace `FakeRedis()` default in `gateway/app.py` with env-driven factory
- Replace `_clients`/`_codes` dicts in `auth/server.py` with Redis-backed store
- Wire `EventLog` into `InternalServiceLayer` with env-driven backend selection
- Promote `redis>=5` to core dep in `pyproject.toml`
- Integration test pass against docker-compose stack

### Out of Scope / Non-Goals

- `InMemoryVectorStore` and `StubEmbedder` replacement (explicit user decision)
- `MessageBus` Redis Pub/Sub replacement (explicit user decision)
- New features or tools
- RS256 + JWKS migration (deferred as R032)

## Technical Constraints

- Tab indentation throughout all Python source (project-wide convention)
- `os.getenv` pattern for env-driven config — no `pydantic-settings` (user decision)
- FakeRedis fallback when `REDIS_URL` unset — zero test changes required
- `aiokafka` stays optional; guard import already present in `kafka_adapter.py`

## Integration Points

- Redis (`:6379`) — session store, OAuth state persistence
- Kafka (`:9092`) — EventLog backend
- docker-compose.yml — already defines all required services

## Testing Requirements

- Unit tests: all 32 existing tests must pass without docker (FakeRedis fallback)
- Integration tests: `pytest -m integration` must pass with docker-compose running
- New tests for auth Redis persistence (client survives restart) and EventLog wiring

## Acceptance Criteria

- S01: `REDIS_URL` set → real Redis client used; unset → FakeRedis; `pytest tests/` green
- S02: OAuth client registration persists across auth server restart when `REDIS_URL` set
- S03: Tool call with `KAFKA_BOOTSTRAP_SERVERS` set produces durable Kafka event
- S04: Full docker-compose stack, all tests pass

## Open Questions

- None — all scope questions resolved during discussion.
