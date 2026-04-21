# M008: Production-Grade Infrastructure Wiring

**Vision:** Replace every in-memory/fake default with a real, env-driven production implementation. The infra and protocols already exist — this milestone wires them into the application paths using os.getenv factory switches with FakeRedis/InProcessEventLog fallbacks for test isolation.

## Success Criteria

- Gateway uses real Redis when `REDIS_URL` is set; FakeRedis when unset
- OAuth client registrations and authorization codes survive server restarts
- Every `tools/call` produces a durable event via the configured EventLog backend
- `redis>=5` declared as a core dependency in `pyproject.toml`
- `pytest tests/` passes with no docker stack (FakeRedis/InProcess fallbacks)
- `pytest -m integration` passes with docker-compose running

## Key Risks / Unknowns

- Auth Redis TTL semantics — codes need short TTL (5–10 min); client registrations need long/no TTL
- EventLog async append in sync-looking dispatch chain — service layer is already `async def`, so clean

## Proof Strategy

- Auth Redis TTL → retire in S02 by proving code expires and registration persists across restart
- EventLog async wiring → retire in S03 by proving tool call produces Kafka event

## Verification Classes

- Contract verification: pytest unit tests (FakeRedis fallback, InProcessEventLog fallback)
- Integration verification: pytest -m integration against running docker-compose stack
- Operational verification: `python -m mcp_agent_factory.gateway.run` boots against real Redis without error
- UAT / human verification: none — all outcomes are mechanically verifiable

## Milestone Definition of Done

This milestone is complete only when all are true:

- No `FakeRedis()` or in-memory dict state remains in module-level production paths in `gateway/app.py` or `auth/server.py`
- Env-driven factory switches are in place for Redis and EventLog
- `redis>=5` is in `[project].dependencies` in `pyproject.toml`
- `pytest tests/` (no docker) passes — all 32+ existing tests green
- `pytest -m integration` (docker-compose up) passes
- `python -m mcp_agent_factory.gateway.run` boots against real Redis

## Requirement Coverage

- Covers: R027, R028, R029, R030, R031
- Partially covers: none
- Leaves for later: R032 (RS256 JWKS)
- Orphan risks: none

## Slices

- [x] **S01: Env-driven Redis wiring** `risk:medium` `depends:[]`
  > After this: `REDIS_URL=redis://localhost:6379 python -m mcp_agent_factory.gateway.run` starts and `/health` returns ok; existing 32 tests pass with no `REDIS_URL` set (FakeRedis fallback active).

- [x] **S02: Redis-backed OAuth state** `risk:medium` `depends:[S01]`
  > After this: Register an OAuth client, restart the auth server — the client registration is still there. Full PKCE flow completes against Redis-backed state.

- [x] **S03: EventLog gateway wiring** `risk:low` `depends:[S01]`
  > After this: With `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` set, a `tools/call` request produces a Kafka event; without it, `InProcessEventLog` is used and tests are unaffected.

- [x] **S04: Integration proof** `risk:low` `depends:[S02,S03]`
  > After this: `docker-compose up` + `pytest -m integration` passes; all 32+ existing unit tests also pass. The assembled system is proven against real infrastructure.

## Horizontal Checklist

- [x] Every active R027–R031 re-read against new code — still fully satisfied?
- [x] FakeRedis fallback verified in `pytest tests/` (no docker)
- [x] Auth boundary documented — Redis keys namespaced to avoid cross-tenant collisions
- [x] Graceful startup failure when `REDIS_URL` is set but Redis unreachable (fail fast, no silent fallback)

## Boundary Map

### S01 → S02

Produces:
- `gateway/app.py` — `_make_redis_client()` factory (`REDIS_URL` → `redis.asyncio`, else `FakeRedis`)
- `pyproject.toml` — `redis>=5` in core deps

Consumes:
- nothing (first slice)

### S01 → S03

Produces:
- `_make_redis_client()` factory (S03 uses same pattern for EventLog, not Redis directly)

Consumes:
- nothing (first slice)

### S02 → S04

Produces:
- `auth/server.py` — Redis-backed `_clients`/`_codes` with TTL on codes
- Tests for Redis auth persistence

Consumes from S01:
- `_make_redis_client()` factory (or equivalent `REDIS_URL` pattern)

### S03 → S04

Produces:
- `gateway/service_layer.py` — `InternalServiceLayer` with `EventLog` injection
- `_make_event_log()` factory (`KAFKA_BOOTSTRAP_SERVERS` → `KafkaEventLog`, else `InProcessEventLog`)

Consumes from S01:
- Env-driven pattern established in S01

### S04 → (milestone complete)

Produces:
- `tests/test_m008_integration.py` — integration test suite proving all wiring works against real infra

Consumes from S01, S02, S03:
- All env-driven factories
- Auth persistence
- EventLog wiring
