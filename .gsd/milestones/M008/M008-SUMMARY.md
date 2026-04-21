---
id: M008
provides:
  - Env-driven Redis factory in gateway with FakeRedis fallback
  - Redis-backed OAuth client registrations and authorization codes with TTL
  - EventLog injection into InternalServiceLayer with Kafka/InProcess factory
  - Integration test suite covering all wiring paths
key_decisions:
  - AUTH_REDIS_URL takes precedence over REDIS_URL for auth server, enabling independent scaling
  - Auth codes use 600s TTL via Redis native expiry; getdel makes exchange atomic and one-time-use
  - InternalServiceLayer accepts event_log as constructor arg for full testability
  - Kafka producer started/stopped in FastAPI lifespan to ensure clean shutdown
patterns_established:
  - os.getenv factory switch pattern: real backend when env set, fake/in-process when not
  - _set_auth_redis() injection point for per-test Redis isolation
  - @pytest.mark.integration to separate docker-requiring tests from unit suite
observability_surfaces:
  - Startup log when REDIS_URL set and pinged successfully
  - Fail-fast RuntimeError on startup if REDIS_URL set but Redis unreachable
  - gateway.tool_calls event appended after every successful tool dispatch
requirement_outcomes:
  - id: R027
    from_status: active
    to_status: validated
    proof: _make_redis_client() factory in gateway/app.py; 236 unit tests pass with FakeRedis fallback
  - id: R028
    from_status: active
    to_status: validated
    proof: auth/server.py Redis backend; client persistence and code TTL verified in test_m008_integration.py
  - id: R029
    from_status: active
    to_status: validated
    proof: InternalServiceLayer appends gateway.tool_calls; EventLog wiring tested
  - id: R030
    from_status: active
    to_status: validated
    proof: pyproject.toml line 10 — redis>=5 in core dependencies
  - id: R031
    from_status: active
    to_status: validated
    proof: tests/test_m008_integration.py with @pytest.mark.integration isolation
duration: 1 session
verification_result: passed
completed_at: 2026-04-21
---

# M008: Production-Grade Infrastructure Wiring

**Env-driven Redis and EventLog factory switches replace all module-level in-memory state, with FakeRedis/InProcess fallbacks keeping the full test suite green without docker.**

## What Happened

The milestone had four slices executed sequentially. S01 established the pattern: `_make_redis_client()` in `gateway/app.py` returns a real async Redis client when `REDIS_URL` is set (with a startup ping and fail-fast on connection failure), and `fakeredis.FakeRedis()` otherwise. `redis>=5` was added to core dependencies.

S02 applied the same pattern to `auth/server.py`, replacing module-level `_clients` and `_codes` dicts with a Redis backend. Client registrations have no TTL (they're durable); auth codes get a 600-second TTL. Code exchange uses `getdel` — atomic retrieval and deletion in one call, enforcing one-time-use. A `_set_auth_redis()` injection point allows tests to swap in a fresh `FakeRedis` per test, preserving isolation without monkeypatching.

S03 wired `InternalServiceLayer` to accept an `event_log` parameter and appended a `gateway.tool_calls` event after every successful tool dispatch. A `_make_event_log()` factory selects `KafkaEventLog` when `KAFKA_BOOTSTRAP_SERVERS` is set, else `InProcessEventLog`. The Kafka producer is started and stopped in the FastAPI lifespan context.

S04 wrote `tests/test_m008_integration.py` covering: FakeRedis auth round-trip, client persistence across fake restarts, full PKCE flow, one-time-use code enforcement, and EventLog wiring via the gateway. Real-infra tests are marked `@pytest.mark.integration` and skipped without docker.

## Cross-Slice Verification

- `pytest tests/ -q`: 236 passed, 11 skipped — confirmed 2026-04-21
- `grep "_make_redis_client\|REDIS_URL" src/mcp_agent_factory/gateway/app.py` — factory present with correct env check
- `grep "getdel\|AUTH_REDIS_URL" src/mcp_agent_factory/auth/server.py` — Redis backend with atomic code exchange
- `grep "redis>=" pyproject.toml` — `dependencies = ["redis>=5"]` at line 10
- `tests/test_m008_integration.py` exists and contains `@pytest.mark.integration` markers

## Requirement Changes

- R027: active → validated — `_make_redis_client()` factory + 236 green unit tests
- R028: active → validated — Redis-backed auth with TTL; persistence tests in integration suite
- R029: active → validated — EventLog injection; `gateway.tool_calls` events on every dispatch
- R030: active → validated — `redis>=5` in `pyproject.toml` core dependencies
- R031: active → validated — `tests/test_m008_integration.py` with `@pytest.mark.integration` isolation

## Decision Re-evaluation

| Decision | Original Rationale | Still Valid? | Action |
|----------|-------------------|-------------|--------|
| AUTH_REDIS_URL separate from REDIS_URL | Auth server may scale independently from gateway | Yes | Keep |
| FakeRedis fallback over skip-if-no-redis | Tests must run without docker | Yes | Keep |

## Forward Intelligence

### What the next milestone should know
- The `_set_auth_redis()` pattern is the correct way to inject test Redis — don't monkeypatch module globals
- `@pytest.mark.integration` requires `docker-compose up` with Redis on 6379 and Kafka on 9092
- `InternalServiceLayer(event_log=...)` is the injection point; passing `None` falls back to a no-op

### What's fragile
- `_make_redis_client()` is called at module import time — tests that import `gateway.app` without setting `REDIS_URL` get FakeRedis baked in for that process; changing `REDIS_URL` mid-process has no effect
- Auth code TTL is hardcoded at 600s — no config hook yet

### Authoritative diagnostics
- `pytest tests/ -q --tb=short` — first signal; 236 baseline; any regression appears here
- `tests/test_m008_integration.py` — integration test file; check markers and fixture setup if real-infra tests fail

### What assumptions changed
- Original plan assumed gateway and auth share one Redis — implemented with separate env vars (`REDIS_URL` for gateway, `AUTH_REDIS_URL` for auth) to allow independent scaling

## Files Created/Modified

- `src/mcp_agent_factory/gateway/app.py` — `_make_redis_client()` and `_make_event_log()` factories; lifespan startup validation
- `src/mcp_agent_factory/gateway/service_layer.py` — `InternalServiceLayer` accepts `event_log`; appends `gateway.tool_calls` event
- `src/mcp_agent_factory/auth/server.py` — Redis-backed client/code storage; `_set_auth_redis()` injection; `getdel` for atomic exchange
- `pyproject.toml` — `redis>=5` in core dependencies
- `tests/test_m008_integration.py` — integration test suite (FakeRedis unit + real-infra marked tests)
- `tests/test_auth.py` — updated to use `_set_auth_redis()` with FakeRedis fixtures
- `tests/test_integration.py` — updated fixtures for Redis injection
- `tests/test_m004_auth_pkce.py` — updated fixtures for Redis injection
